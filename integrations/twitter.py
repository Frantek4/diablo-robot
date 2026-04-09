import asyncio
from typing import List
import aiohttp
import feedparser
from datetime import datetime, timedelta

from config.settings import settings
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

class Twitter:
    def __init__(self, bot):
        self.bot = bot
        self.rss_bridge_url = settings.TWITTER_RSS_BRIDGE_URL

    async def check_rss_notifications(self):
        """Check RSS feeds for new tweets from registered influencers"""
        twitter_influencers: List[InfluencerModel] = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)

        if not twitter_influencers:
            return

        async with aiohttp.ClientSession() as session:
            for influencer in twitter_influencers:
                try:
                    feed_url = f"{self.rss_bridge_url}/{influencer['name']}/rss"
                    async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status != 200:
                            continue

                        feed_content = await response.text()
                        feed = feedparser.parse(feed_content)

                        if not feed.entries:
                            continue

                        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)

                        for entry in feed.entries[:5]:
                            tweet_url = entry.link
                            normalized_url = self.bot.news_dao.normalize_url("https://x.com", tweet_url)

                            if self.bot.news_dao.exists(normalized_url):
                                continue

                            try:
                                published_date = datetime(*entry.published_parsed[:6], tzinfo=settings.TIMEZONE)
                                if published_date < one_week_ago:
                                    continue
                            except (ValueError, AttributeError, TypeError) as e:
                                await self.bot.messager.log(f"Error parsing date for {tweet_url}: {str(e)}")
                                continue

                            title = f"@{influencer['name']}"
                            description = entry.title if hasattr(entry, 'title') else ""
                            if len(description) > 400:
                                description = description[:400] + "..."

                            image_url = None
                            if hasattr(entry, 'media_content') and entry.media_content:
                                image_url = entry.media_content[0].get('url')
                            elif hasattr(entry, 'links'):
                                for link in entry.links:
                                    if link.get('type', '').startswith('image/'):
                                        image_url = link.get('href')
                                        break

                            await self.bot.messager.news(
                                type=influencer['source'],
                                title=title,
                                description=description,
                                url=normalized_url,
                                image_url=image_url,
                                publisher=f"Twitter/X • {influencer['name']}",
                                color="#000000"
                            )
                            self.bot.news_dao.insert(normalized_url)

                            await asyncio.sleep(1)

                except Exception as e:
                    await self.bot.messager.log(f"Error observando cuenta de Twitter {influencer['name']}: {str(e)}")
                    continue

                await asyncio.sleep(2)
