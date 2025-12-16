import asyncio
from typing import List
import aiohttp
import feedparser
from datetime import datetime, timedelta

import pytz
from config.settings import settings
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

class YouTube:
    domain = "https://www.youtube.com"
    def __init__(self, bot):
        self.bot = bot
    
    async def check_rss_notifications(self):
        """Check RSS feeds for new YouTube videos from registered influencers"""
        youtube_influencers : List[InfluencerModel] = self.bot.influencer_dao.get_by_platform(SocialMedia.YOUTUBE)
        
        if not youtube_influencers:
            return

        async with aiohttp.ClientSession() as session:
            for influencer in youtube_influencers:
                try:
                    feed_url = f"{YouTube.domain}/feeds/videos.xml?channel_id={influencer['id']}"
                    async with session.get(feed_url, timeout=10) as response:
                        if response.status != 200:
                            continue
                        
                        feed_content = await response.text()
                        feed = feedparser.parse(feed_content)
                        
                        if not feed.entries:
                            continue
                        
                        # Calculate one week ago threshold
                        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
                        
                        # Process entries (newest first)
                        for entry in feed.entries[:3]:  # Check last 3 videos
                            video_url = entry.link
                            normalized_url = self.bot.news_dao.normalize_url(YouTube.domain, video_url)
                            
                            # Skip if already notified
                            if self.bot.news_dao.exists(normalized_url):
                                continue
                            
                            # Parse published date and skip if older than one week
                            try:
                                published_date = datetime.strptime(entry.published, '%Y-%m-%dT%H:%M:%S%z')
                                published_date = published_date.replace(tzinfo=pytz.UTC)
                                
                                if published_date < one_week_ago:
                                    continue
                            except (ValueError, AttributeError) as e:
                                await self.bot.messager.log(f"Error parsing date for {video_url}: {str(e)}")
                                continue
                            
                            # Prepare embed data
                            title = entry.title
                            description = entry.summary[:400] + "..." if len(entry.summary) > 400 else entry.summary
                            image_url = entry.media_thumbnail[0]['url'] if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail else None
                            publisher = f"YouTube • {influencer['name']}"
                            
                            # Send notification
                            await self.bot.messager.news(
                                type=influencer['source'],
                                title=title,
                                description=description,
                                url=video_url,
                                image_url=image_url,
                                publisher=publisher,
                                color="#FF0000"  # YouTube red
                            )
                            # Mark as processed
                            self.bot.news_dao.insert(normalized_url)
                            
                            # Small delay between videos
                            await asyncio.sleep(1)
                
                except Exception as e:
                    await self.bot.messager.log(f"Error observando canal de Youtube {influencer.name}: {str(e)}")
                    continue
                
                # Delay between channel checks
                await asyncio.sleep(2)