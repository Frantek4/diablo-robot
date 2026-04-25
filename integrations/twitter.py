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


class Twitter:
    def __init__(self, bot):
        self.bot = bot
        self.rss_bridge_url = settings.TWITTER_RSS_BRIDGE_URL

    async def check_rss_notifications(self):
        influencers: List[InfluencerModel] = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)
        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        async with aiohttp.ClientSession() as session:
            for influencer in influencers:
                try:
                    await self._process_influencer(session, influencer, one_week_ago, headers)
                except Exception as e:
                    name = influencer.get("name", "unknown") if isinstance(influencer, dict) else str(influencer)
                    await self.bot.messager.log(f"No pude procesar el feed de Twitter de {name}: {e}", level="ERROR", exc=e)
                await asyncio.sleep(2)

    async def _process_influencer(self, session, influencer, one_week_ago, headers):
        name = influencer["name"]
        feed_url = f"{self.rss_bridge_url}/{name}/rss"

        async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                await self.bot.messager.log(f"No pude obtener el RSS de {name} en Twitter (HTTP {response.status}).", level="WARNING")
                return

            content = (await response.read()).decode("utf-8", errors="replace")
            feed = feedparser.parse(content)

        if not feed.entries:
            return

        for entry in feed.entries[:5]:
            parsed = parse_entry(entry, influencer)
            if not parsed:
                tweet_url = entry.get("link", "")
                if tweet_url:
                    await self.bot.messager.log(f"No pude parsear la URL del tweet de {name}: {tweet_url}", level="WARNING")
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