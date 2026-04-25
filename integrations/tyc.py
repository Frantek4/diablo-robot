import aiohttp
from bs4 import BeautifulSoup
import re
import json

from models.news_source import NewsSource

class TycSportsScraper:
    def __init__(self, bot):
        self.bot = bot
        self.domain = "https://www.tycsports.com"
        self.urls = [
            "independiente",
            "seleccion-argentina",
            #"liga-profesional-de-futbol"
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        async with aiohttp.ClientSession() as session:
            for url in self.urls:
                try:
                    full_url = f"{self.domain}/{url}.html"
                    async with session.get(full_url, headers=self.headers, timeout=10) as response:
                        response.raise_for_status()
                        html = await response.text()
                
                    soup = BeautifulSoup(html, 'lxml')
                    news_links = self._extract_news_links(url, soup)
                    
                    for link_data in news_links:
                        news_url = link_data['url']
                        if self.bot.news_dao.exists(news_url):
                            continue

                        detail_data = await self._get_article_details(news_url, session)
                        
                        if not detail_data['title']:
                            continue

                        clean_title = re.sub(r'\s*[-–]\s*TyC Sports\s*$', '', detail_data['title'], flags=re.IGNORECASE | re.UNICODE)
                        
                        await self.bot.messager.news(
                            type=NewsSource.PRESS,
                            title=clean_title,
                            description=detail_data['description'],
                            url=news_url,
                            image_url=detail_data['image_url'],
                            publisher= f"TyC Sports • {url}",
                            color="#0F1A87"
                        )
                        self.bot.news_dao.insert(news_url)
                        
                except Exception as e:
                    await self.bot.messager.log(f"No pude scrapear TyC Sports ({url}): {e}", level="ERROR", exc=e)

    def _extract_news_links(self, origin_url, soup):
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/' + origin_url + '/' in href and '/' + origin_url + '/' != href.strip('/') and 'reels' not in href.lower():
                url = self.bot.news_dao.normalize_url(self.domain, href)
                if url:
                    links.append({'url': url})
                
        return links

    async def _get_article_details(self, article_url, session: aiohttp.ClientSession):
        try:
            async with session.get(article_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                html = await response.text()

            soup = BeautifulSoup(html, 'lxml')

            title = ""
            title_tag = soup.find('title')
            if title_tag:
                title = re.sub(r'\s*[-–]\s*TyC Sports\s*$', '', title_tag.get_text(strip=True), flags=re.IGNORECASE | re.UNICODE).strip()
            else:
                h1_tag = soup.find('h1')
                if h1_tag:
                    title = h1_tag.get_text(strip=True)

            description = ""
            desc_meta = soup.find('meta', attrs={'name': 'description'})
            if desc_meta:
                description = desc_meta.get('content', '').strip()
            else:
                subtitle_tag = soup.find('h2', class_=lambda x: x and 'headline' not in x.lower())
                if subtitle_tag:
                    description = subtitle_tag.get_text(strip=True)
                else:
                    first_paragraph = soup.find('p', class_=lambda x: x and 'bajada' in x.lower() if x else False)
                    if not first_paragraph:
                        first_paragraph = soup.find('p')
                    if first_paragraph:
                        description = first_paragraph.get_text(strip=True)

            image_url = None
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content') and not og_image['content'].startswith('data:image'):
                image_url = self.bot.news_dao.normalize_url(self.domain, og_image['content'])

            if not image_url:
                schema_article = soup.find('script', type='application/ld+json')
                if schema_article:
                    try:
                        schema_data = json.loads(schema_article.string)
                        if schema_data.get('@type') == 'NewsArticle':
                            images = schema_data.get('image', [])
                            if isinstance(images, list) and images:
                                img_obj = images[0]
                                img_url = img_obj.get('url') if isinstance(img_obj, dict) else img_obj
                                if img_url and not img_url.startswith('data:image'):
                                    image_url = self.bot.news_dao.normalize_url(self.domain, img_url)
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not image_url:
                img_tag = soup.find('img', class_='mainImg')
                if img_tag:
                    src_value = img_tag.get('data-src') or img_tag.get('src')
                    if src_value and not src_value.startswith('data:image'):
                        image_url = self.bot.news_dao.normalize_url(self.domain, src_value)

            return {'title': title, 'description': description, 'image_url': image_url}
        except Exception as e:
            await self.bot.messager.log(f"No pude obtener los detalles de {article_url} en TyC Sports: {e}", level="ERROR", exc=e)
            return {'title': '', 'description': '', 'image_url': None}