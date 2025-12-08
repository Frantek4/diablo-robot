import asyncio
from datetime import datetime, timedelta

import aiohttp
from bs4 import BeautifulSoup

from config.settings import settings
from data_access.influencers import InfluencerDAO
from data_access.news import NewsDAO
from models.influencer import InfluencerModel
from models.social_media import SocialMedia

class InstagramScraper:
    def __init__(self, bot):
        self.bot = bot
        self.accounts_dao = InfluencerDAO()
        self.news_dao = NewsDAO()

    async def scrape_posts(self):
        instagram_accounts: list[InfluencerModel] = self.accounts_dao.get_by_platform(SocialMedia.INSTAGRAM)
        
        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        
        for account in instagram_accounts:
            try:
                posts = await self.get_recent_posts(f"https://www.instagram.com/{account['name']}/", one_week_ago)
                
                for post in posts:
                    
                    url = self.news_dao.normalize_url("https://www.instagram.com",post['url'])
                    if self.news_dao.exists(url):
                        continue

                    await self.bot.messager.news(
                        type=account['source'],
                        title=f"Publicación de {account['description']} en Instagram",
                        description=post['description'],
                        url=url,
                        image_url=post.get('image_url'),
                        publisher=f"{account['description']} en Instagram",
                        color="#E4405F"
                    )
                    self.news_dao.insert(url)
            except Exception as e:
                print(f"Error scraping {account['name']}: {e}")



    async def get_recent_posts(self, profile_url: str, since_date: datetime):
        async with aiohttp.ClientSession() as session:
            async with session.get(profile_url) as response:
                html = await response.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        posts = []
        
        # Buscar enlaces de publicaciones
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/p/' in href and href.startswith('/p/'):
                full_url = f"https://www.instagram.com{href}"
                
                # Obtener detalles de la publicación
                post_data = await self.get_post_details(session, full_url, since_date)
                if post_data:
                    posts.append(post_data)
                    
        return posts



    async def get_post_details(self, session, post_url, since_date):
        try:
            async with session.get(post_url) as response:
                html = await response.text()
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # Buscar la fecha de publicación
            time_element = soup.find('time')
            if time_element and time_element.get('datetime'):
                post_time = datetime.fromisoformat(time_element['datetime'].replace('Z', '+00:00'))
                if post_time < since_date:
                    return None  # Demasiado antiguo
            else:
                # Si no hay datetime, buscar texto como "hace X días"
                time_text_element = soup.find('time')
                if time_text_element:
                    time_text = time_text_element.get_text()
                    if 'hace' in time_text and ('día' in time_text or 'semana' in time_text or 'mes' in time_text):
                        # Considerar como antiguo si tiene más de una semana
                        return None
            
            # Extraer metadatos
            meta_desc = soup.find('meta', property='og:description')
            meta_image = soup.find('meta', property='og:image')
            
            return {
                'url': post_url,
                'description': meta_desc['content'] if meta_desc else '',
                'image_url': meta_image['content'] if meta_image else None
            }
        except:
            return None