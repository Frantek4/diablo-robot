import asyncio
import re
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import List
from urllib.parse import unquote

import aiohttp
import feedparser

from config.settings import settings
from integrations import nitter_mirrors
from integrations.nitter_mirrors import nitter_error_reason
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

# Espera fija entre feed y feed: a Nitter le molesta el ritmo, no el patrón
_FEED_DELAY = 60


def nitter_pic_to_twimg(url: str) -> str:
    match = re.match(r'https?://[^/]+/pic/(.+)', url)
    if not match:
        return url
    path = unquote(match.group(1))
    if path.startswith(("pbs.twimg.com/", "video.twimg.com/")):
        return f"https://{path}"
    return f"https://pbs.twimg.com/{path}"


class NitterHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.quote_text = None
        self.quote_author = None
        self._in_blockquote = False
        self._in_bold = False
        self._in_paragraph = False
        self._paragraph_buffer = []
        self._bold_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "blockquote":
            self._in_blockquote = True
        elif tag == "b":
            self._in_bold = True
        elif tag == "p":
            self._in_paragraph = True
            self._paragraph_buffer = []
        elif tag == "img":
            src = attrs.get("src", "")
            if src:
                self.images.append({"src": nitter_pic_to_twimg(src), "in_quote": self._in_blockquote})

    def handle_endtag(self, tag):
        if tag == "blockquote":
            self._in_blockquote = False
        elif tag == "b":
            if self._in_blockquote and self.quote_author is None:
                self.quote_author = "".join(self._bold_buffer).strip()
            self._in_bold = False
            self._bold_buffer = []
        elif tag == "p":
            text = "".join(self._paragraph_buffer).strip()
            if self._in_blockquote and text and self.quote_text is None:
                self.quote_text = text
            self._in_paragraph = False
            self._paragraph_buffer = []

    def handle_data(self, data):
        if self._in_bold:
            self._bold_buffer.append(data)
        if self._in_paragraph:
            self._paragraph_buffer.append(data)

    @property
    def main_image(self):
        non_quote = [img["src"] for img in self.images if not img["in_quote"]]
        return non_quote[0] if non_quote else None

    @property
    def quote_image(self):
        in_quote = [img["src"] for img in self.images if img["in_quote"]]
        return in_quote[0] if in_quote else None


def nitter_to_x_url(nitter_url: str) -> str | None:
    match = re.search(r'/(\w+)/status/(\d+)', nitter_url)
    if not match:
        return None
    return f"https://x.com/{match.group(1)}/status/{match.group(2)}"


def parse_entry(entry: dict, influencer: dict) -> dict | None:
    tweet_url = entry.get("link", "")
    normalized_url = nitter_to_x_url(tweet_url)
    if not normalized_url:
        return None

    published_parsed = entry.get("published_parsed")
    if published_parsed:
        published_date = datetime(*published_parsed[:6], tzinfo=settings.TIMEZONE)
    else:
        published_date = datetime.now(settings.TIMEZONE)

    html_description = entry.get("description", "")
    parser = NitterHTMLParser()
    parser.feed(html_description)

    tweet_text = entry.get("title", "")
    if len(tweet_text) > 400:
        tweet_text = tweet_text[:400] + "..."

    description_parts = [tweet_text]
    if parser.quote_author and parser.quote_text:
        quote_preview = parser.quote_text[:200] + "..." if len(parser.quote_text) > 200 else parser.quote_text
        description_parts.append(f"\n> **{parser.quote_author}**\n> {quote_preview}")

    return {
        "url": normalized_url,
        "published_date": published_date,
        "title": f"{influencer['description']} en Twitter",
        "description": "\n".join(description_parts),
        "image_url": parser.main_image or parser.quote_image,
        "publisher": f"Twitter • {influencer['name']}",
        "source": influencer.get("source", "TWITTER"),
    }


class MirrorDown(Exception):
    """El mirror no sirve ahora mismo: es problema de la instancia, no de la cuenta que estaba leyendo."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Twitter:
    def __init__(self, bot):
        self.bot = bot
        self.mirror_dao = bot.nitter_mirror_dao
        # Queda en True cuando probé todos los mirrors del repositorio y no anduvo ninguno
        self.out_of_mirrors = False

    async def check_rss_notifications(self, influencers: List[InfluencerModel] | None = None) -> int:
        """Devuelve cuántas cuentas quedaron consumidas.

        Cuando un mirror se cae en el medio (429, 403, el /rss apagado) lo bajo del repositorio y sigo la
        misma cuenta con el siguiente. Las que no llegué a leer no cuentan, así el scheduler las reintenta
        en la vuelta siguiente en vez de saltearlas hasta que el cursor dé toda la vuelta.
        """
        if influencers is None:
            influencers = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)
        if not influencers:
            return 0

        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        failures: list[str] = []
        retired: list[str] = []
        consumed = 0
        self.out_of_mirrors = False

        pending_mirrors = await self._mirror_queue()
        mirror = pending_mirrors.pop(0) if pending_mirrors else None

        async with aiohttp.ClientSession() as session:
            index = 0
            while index < len(influencers):
                if mirror is None:
                    self.out_of_mirrors = True
                    break

                influencer = influencers[index]
                name = influencer["name"]

                try:
                    reason, latency_ms = await self._process_influencer(
                        session, mirror.url, influencer, one_week_ago
                    )
                except MirrorDown as e:
                    self.mirror_dao.save_result(mirror.url, is_online=False, reason=e.reason)
                    retired.append(f"{mirror.host} ({e.reason})")
                    mirror = pending_mirrors.pop(0) if pending_mirrors else None
                    continue

                self.mirror_dao.save_result(mirror.url, is_online=True, latency_ms=latency_ms)

                consumed = index + 1
                if reason:
                    failures.append(f"@{name} ({reason})")

                index += 1
                if index < len(influencers):
                    await asyncio.sleep(_FEED_DELAY)

        # Si me quedé sin ninguno, el aviso lo da report_pool_state con un [CRÍTICO]: no lo repito acá
        if retired and not self.out_of_mirrors:
            await self.bot.messager.log(
                f"Se me cayeron {len(retired)} mirror(s) de Nitter en el medio del scaneo: {', '.join(retired)}. "
                f"Seguí con {mirror.host}.",
                level="WARNING",
            )

        if failures:
            await self.bot.messager.log(
                f"No pude leer {len(failures)} feed(s) de Twitter: {', '.join(failures)}.",
                level="WARNING",
            )
        return consumed

    async def _mirror_queue(self) -> list:
        """Los mirrors que puedo usar ahora, mejor primero: los que sé que andan y los que nunca probé.

        A los caídos no los toco acá: los reintenta el chequeo de mirrors con su backoff, así no salgo a
        golpear ocho instancias muertas cada vez que scaneo. Si el repositorio está vacío lo siembro.
        """
        mirrors = self.mirror_dao.get_ranked()
        if not mirrors:
            await nitter_mirrors.seed_catalog(self.bot)
            mirrors = self.mirror_dao.get_ranked()
        return [mirror for mirror in mirrors if mirror.is_online or mirror.is_online is None]

    async def _process_influencer(self, session, mirror_url, influencer, one_week_ago) -> tuple[str | None, float | None]:
        """Devuelve (motivo de la falla de la cuenta o None, latencia del feed). Si el mirror falla, tira MirrorDown."""
        name = influencer["name"]
        feed_url = f"{mirror_url}/{name}/rss"
        headers = {"User-Agent": settings.USER_AGENT}
        started = time.perf_counter()

        try:
            async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                content = (await response.read()).decode("utf-8", errors="replace")
                latency_ms = (time.perf_counter() - started) * 1000
                status = response.status
        except asyncio.TimeoutError:
            raise MirrorDown("timeout")
        except aiohttp.ClientError as e:
            raise MirrorDown(type(e).__name__)

        if status == 404:
            # Esto es de la cuenta, no del mirror: no lo bajo por una cuenta que no existe más
            return "cuenta no encontrada", latency_ms

        if status != 200:
            reason = nitter_error_reason(content)
            raise MirrorDown(f"HTTP {status}: {reason}" if reason else f"HTTP {status}")

        feed = feedparser.parse(content)

        if feed.bozo and not feed.entries:
            raise MirrorDown("RSS roto")

        if feed.entries and not nitter_mirrors.entries_have_tweets(feed.entries, name):
            # Contesta 200 con un RSS válido que no trae tweets (whitelist, cartel de error): inservible igual
            raise MirrorDown(nitter_error_reason(content) or "contesta pero no devuelve tweets")

        if not feed.entries:
            return "feed vacío", latency_ms

        for entry in reversed(feed.entries):
            parsed = parse_entry(entry, influencer)
            if not parsed:
                continue

            if parsed["published_date"] < one_week_ago:
                continue

            if self.bot.news_dao.exists(parsed["url"]):
                continue

            await self.bot.messager.news(
                type=parsed["source"],
                title=parsed["title"],
                description=parsed["description"],
                url=parsed["url"],
                image_url=parsed["image_url"],
                publisher=parsed["publisher"],
                color="#00acee",
            )
            self.bot.news_dao.insert(parsed["url"])
            await asyncio.sleep(1)

        return None, latency_ms
