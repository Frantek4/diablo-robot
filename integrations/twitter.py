import asyncio
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import List
from urllib.parse import unquote

import aiohttp
import feedparser

from config.settings import settings
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

# Espera fija entre feed y feed: la instancia es mía, pero el rate limit de X lo paga igual la sesión
_FEED_DELAY = 60


def instance_url() -> str | None:
    """La instancia propia de Nitter. Si no le puse esquema asumo http: corre en la misma máquina."""
    raw = (settings.NITTER_HOST_URL or "").strip().rstrip("/")
    if not raw:
        return None
    return raw if raw.startswith(("http://", "https://")) else f"http://{raw}"


def nitter_error_reason(body: str) -> str | None:
    """Saca el motivo que Nitter escribe en su pantalla de error, para no loguear un HTTP pelado."""
    match = re.search(r'error-panel"?>\s*<span>(.*?)</span>', body, re.DOTALL)
    if not match:
        return None
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', match.group(1))).strip() or None


def entries_have_tweets(entries, account: str) -> bool:
    """Los items tienen que linkear a tweets de la cuenta: un 200 con un RSS sin tweets no me sirve."""
    pattern = re.compile(rf'/{re.escape(account)}/status/\d+', re.IGNORECASE)
    return any(pattern.search(entry.get("link", "")) for entry in entries)


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


class InstanceDown(Exception):
    """La instancia no sirve ahora mismo: es problema de Nitter, no de la cuenta que estaba leyendo."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Twitter:
    def __init__(self, bot):
        self.bot = bot

    async def check_rss_notifications(self, influencers: List[InfluencerModel] | None = None) -> int:
        """Devuelve cuántas cuentas quedaron consumidas.

        Si la instancia se cae corto el scaneo: sin ella no hay Twitter, y las cuentas que no llegué a
        leer no cuentan, así el scheduler las reintenta en la vuelta siguiente en vez de saltearlas.
        """
        base_url = instance_url()
        if not base_url:
            return 0

        if influencers is None:
            influencers = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)
        if not influencers:
            return 0

        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        failures: list[str] = []
        consumed = 0

        async with aiohttp.ClientSession() as session:
            for index, influencer in enumerate(influencers):
                try:
                    reason = await self._process_influencer(session, base_url, influencer, one_week_ago)
                except InstanceDown as e:
                    await self.bot.messager.log(
                        f"Mi instancia de Nitter no está sirviendo feeds ({e.reason}). Corto el scaneo de "
                        f"Twitter y sigo en la próxima vuelta. Si insiste, mirá el contenedor en el Pi.",
                        level="ERROR",
                    )
                    break

                consumed = index + 1
                if reason:
                    failures.append(f"@{influencer['name']} ({reason})")

                if index + 1 < len(influencers):
                    await asyncio.sleep(_FEED_DELAY)

        if failures:
            await self.bot.messager.log(
                f"No pude leer {len(failures)} feed(s) de Twitter: {', '.join(failures)}.",
                level="WARNING",
            )
        return consumed

    async def _process_influencer(self, session, base_url, influencer, one_week_ago) -> str | None:
        """Devuelve el motivo de la falla de la cuenta, o None si salió bien. Si falla la instancia, tira InstanceDown."""
        name = influencer["name"]
        headers = {"User-Agent": settings.USER_AGENT}

        try:
            async with session.get(
                f"{base_url}/{name}/rss", headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                content = (await response.read()).decode("utf-8", errors="replace")
                status = response.status
        except asyncio.TimeoutError:
            raise InstanceDown("timeout")
        except aiohttp.ClientError as e:
            raise InstanceDown(type(e).__name__)

        if status == 404:
            # Esto es de la cuenta, no de la instancia: no corto el scaneo por una cuenta que no existe más
            return "cuenta no encontrada"

        if status != 200:
            reason = nitter_error_reason(content)
            raise InstanceDown(f"HTTP {status}: {reason}" if reason else f"HTTP {status}")

        feed = feedparser.parse(content)

        if feed.bozo and not feed.entries:
            raise InstanceDown("RSS roto")

        if feed.entries and not entries_have_tweets(feed.entries, name):
            # 200 con un RSS válido que no trae tweets: la sesión se quemó o Nitter está devolviendo un cartel
            raise InstanceDown(nitter_error_reason(content) or "contesta pero no devuelve tweets")

        if not feed.entries:
            return "feed vacío"

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

        return None
