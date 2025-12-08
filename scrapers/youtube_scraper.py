import aiohttp
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config.settings import settings
from data_access.influencers import InfluencerDAO
from data_access.news import NewsDAO
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

class YoutubeScraper:
    def __init__(self, bot):
        self.bot = bot
        self.accounts_dao = InfluencerDAO()
        self.news_dao = NewsDAO()

    async def scrape_videos(self):
        youtube_accounts: list[InfluencerModel] = self.accounts_dao.get_by_platform(SocialMedia.YOUTUBE)
        
        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        
        for account in youtube_accounts:
            try:
                channel_url = f"https://www.youtube.com/@{account['name']}"
                videos = await self.get_recent_videos(channel_url, one_week_ago)
                
                for video in videos:
                    url = self.news_dao.normalize_url(video['url'])
                    
                    if self.news_dao.exists(url):
                        continue

                    await self.bot.messager.news(
                        type=account.source,
                        title=video['title'],
                        description=video['description'],
                        url=url,
                        image_url=video.get('image_url'),
                        publisher=f"{account.description} en YouTube",
                        color="#FF0000"  # Rojo de YouTube
                    )
                    self.news_dao.insert(url)
            except Exception as e:
                print(f"Error scraping {account['name']}: {e}")

    async def get_recent_videos(self, channel_url: str, since_date: datetime):
        async with aiohttp.ClientSession() as session:
            async with session.get(channel_url + "/videos") as response:
                html = await response.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        posts = []
        
        # Buscar enlaces de videos
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/watch?v=' in href and href.startswith('/watch'):
                full_url = f"https://www.youtube.com{href}"
                
                post_data = await self.get_video_details(session, full_url, since_date)
                if post_data:
                    posts.append(post_data)
                    
        return posts

    async def get_video_details(self, session, post_url, since_date):
        try:
            async with session.get(post_url) as response:
                html = await response.text()
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # Buscar la fecha de publicación
            time_element = soup.find('yt-formatted-string', {'class': 'date'})
            if not time_element:
                time_element = soup.find('span', class_='date-text')
                
            if time_element:
                time_text = time_element.get_text()
                if 'day' in time_text or 'week' in time_text or 'month' in time_text:
                    # Verificar si es más antiguo que una semana
                    if 'week' in time_text and '1' not in time_text.split()[0]:
                        return None  # Más de una semana
                    elif 'month' in time_text or 'year' in time_text:
                        return None  # Demasiado antiguo
                elif time_element.get('datetime'):
                    post_time = datetime.fromisoformat(time_element['datetime'])
                    if post_time < since_date:
                        return None  # Demasiado antiguo
            
            # Extraer metadatos
            meta_desc = soup.find('meta', property='og:description')
            meta_image = soup.find('meta', property='og:image')
            meta_title = soup.find('meta', property='og:title')
            
            return {
                'url': post_url,
                'title': meta_title['content'] if meta_title else 'YouTube Video',
                'description': meta_desc['content'] if meta_desc else '',
                'image_url': meta_image['content'] if meta_image else None
            }
        except:
            return None