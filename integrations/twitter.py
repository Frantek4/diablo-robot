import asyncio
import logging
from typing import List
import aiohttp
import feedparser
import re
from datetime import datetime, timedelta

from config.settings import settings
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

logger = logging.getLogger(__name__)

class Twitter:
    def __init__(self, bot):
        self.bot = bot
        self.rss_bridge_url = settings.TWITTER_RSS_BRIDGE_URL

    async def check_rss_notifications(self):
        """Check RSS feeds for new tweets from registered influencers"""
        twitter_influencers: List[InfluencerModel] = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        async with aiohttp.ClientSession() as session:
            for influencer in twitter_influencers:
                try:
                    influencer_name = influencer.name
                    
                    feed_url = f"{self.rss_bridge_url}/{influencer_name}/rss"
                    logger.info(f"Fetching Twitter RSS: {feed_url}")
                    
                    async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to fetch {feed_url}: status {response.status}")
                            continue
                        
                        # Usar response.read() para obtener el contenido como bytes, luego decodificar
                        feed_content_bytes = await response.read()
                        feed_content = feed_content_bytes.decode('utf-8', errors='replace')
                        
                        logger.debug(f"Raw response length: {len(feed_content)} bytes")
                        feed = feedparser.parse(feed_content)

                        logger.info(f"Successfully fetched RSS feed for {influencer_name}: {len(feed.entries)} entries found")

                        if not feed.entries:
                            logger.info(f"No entries found for {influencer_name}")
                            continue

                        logger.info(f"Found {len(feed.entries)} entries for {influencer_name}")
                        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)

                        for entry in feed.entries[:5]:
                            tweet_url = entry.get('link', '')
                            if not tweet_url:
                                continue
                            
                            # Extraer tweet ID y username de la URL de Nitter
                            # URL: https://nitter.net/elonmusk/status/2046609562778673232#m
                            status_match = re.search(r'/(\w+)/status/(\d+)', tweet_url)
                            if status_match:
                                tweet_username = status_match.group(1)
                                tweet_id = status_match.group(2)
                                # URL limpia a x.com
                                normalized_url = f"https://x.com/{tweet_username}/status/{tweet_id}"
                            else:
                                logger.warning(f"Could not parse tweet URL: {tweet_url}")
                                continue

                            if self.bot.news_dao.exists(normalized_url):
                                logger.debug(f"Tweet already exists: {normalized_url}")
                                continue

                            try:
                                published_parsed = entry.get('published_parsed')
                                if published_parsed:
                                    published_date = datetime(*published_parsed[:6], tzinfo=settings.TIMEZONE)
                                else:
                                    published_date = datetime.now(settings.TIMEZONE)
                                    logger.warning(f"No published_parsed for {tweet_url}, using now")
                                    
                                if published_date < one_week_ago:
                                    logger.debug(f"Tweet too old: {published_date}")
                                    continue
                            except (ValueError, AttributeError, TypeError) as e:
                                logger.error(f"Error parsing date for {tweet_url}: {str(e)}")
                                continue

                            title = f"@{influencer_name}"
                            description = entry.get('title', '')
                            if len(description) > 400:
                                description = description[:400] + "..."

                            # Extraer imagen del HTML de la descripción
                            image_url = None
                            html_description = entry.get('description', '')
                            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_description)
                            if img_match:
                                image_url = img_match.group(1)
                                logger.debug(f"Found image: {image_url}")

                            logger.info(f"Publishing tweet from {influencer_name}: {title}")
                            await self.bot.messager.news(
                                type=influencer.get('source', 'TWITTER'),
                                title=title,
                                description=description,
                                url=normalized_url,
                                image_url=image_url,
                                publisher=f"Twitter/X • {influencer_name}",
                                color="#000000"
                            )
                            self.bot.news_dao.insert(normalized_url)

                            await asyncio.sleep(1)

                except Exception as e:
                    influencer_name = influencer.get('name', 'unknown') if isinstance(influencer, dict) else str(influencer)
                    logger.error(f"Error checking Twitter {influencer_name}: {str(e)}", exc_info=True)
                    continue

                await asyncio.sleep(2)
