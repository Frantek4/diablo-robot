import asyncio
from typing import List
import aiohttp
import feedparser
from datetime import datetime, timedelta

from config.settings import settings
from models.influencer import InfluencerModel
from utils.date_format import to_local
from models.social_media import SocialMedia

class YouTube:
    domain = "https://www.youtube.com"

    def __init__(self, bot):
        self.bot = bot

    async def check_rss_notifications(self):
        youtube_influencers: List[InfluencerModel] = self.bot.influencer_dao.get_by_platform(SocialMedia.YOUTUBE)
        if not youtube_influencers:
            return

        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)

        async with aiohttp.ClientSession() as session:
            for influencer in youtube_influencers:
                try:
                    feed_url = f"{YouTube.domain}/feeds/videos.xml?channel_id={influencer['account_id']}"
                    async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue
                        feed = feedparser.parse(await response.text())

                    for entry in reversed(feed.entries[:3]):
                        video_url = entry.link
                        normalized_url = self.bot.news_dao.normalize_url(YouTube.domain, video_url)

                        if self.bot.news_dao.exists(normalized_url):
                            continue

                        try:
                            published_date = to_local(datetime.strptime(entry.published, '%Y-%m-%dT%H:%M:%S%z'))
                            if published_date < one_week_ago:
                                continue
                        except (ValueError, AttributeError) as e:
                            await self.bot.messager.log(f"No pude parsear la fecha del video {video_url}: {e}", level="WARNING")
                            continue

                        is_short = "/shorts/" in video_url
                        if is_short:
                            description = f"Nuevo video corto de {influencer['name']}"
                        else:
                            description = entry.summary[:400] + "..." if len(entry.summary) > 400 else entry.summary
                        image_url = entry.media_thumbnail[0]['url'] if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail else None

                        await self.bot.messager.news(
                            type=influencer['source'],
                            title=entry.title,
                            description=description,
                            url=video_url,
                            image_url=image_url,
                            publisher=f"YouTube • {influencer['name']}",
                            color="#FF0000"
                        )
                        self.bot.news_dao.insert(normalized_url)
                        await asyncio.sleep(1)

                except Exception as e:
                    await self.bot.messager.log(f"No pude revisar el canal '{influencer['name']}' de YouTube: {e}", level="ERROR", exc=e)

                await asyncio.sleep(2)
