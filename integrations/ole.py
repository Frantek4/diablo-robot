import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import json

from models.news_source import NewsSource


class OleScraper:
    def __init__(self, bot):
        self.bot = bot
        self.domain = "https://www.ole.com.ar"
        self.urls = [
            "independiente",
            "seleccion",
            "mundial",
            #"futbol-primera"
        ]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        async with aiohttp.ClientSession() as session:
            for url in self.urls:
                try:
                    await asyncio.sleep(15)
                    async with session.get(f"{self.domain}/{url}", headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        response.raise_for_status()
                        html = await response.text()
                    
                    soup = BeautifulSoup(html, 'lxml')
                    news = await self._extract_news(url, soup)

                    for item in news:
                        news_url = self.bot.news_dao.normalize_url(self.domain, item['url'])
                        if self.bot.news_dao.exists(news_url):
                            continue
                        
                        clean_description = re.sub(r'\s*Mirá\.\s*$', '', item['description'], flags=re.IGNORECASE | re.UNICODE)
                        
                        await self.bot.messager.news(
                            type=NewsSource.PRESS,
                            title=item['title'],
                            description=clean_description,
                            url=news_url,
                            image_url=item['image_url'],
                            publisher=f"Olé • {url}",
                            color="#A6CE39"
                        )
                        self.bot.news_dao.insert(news_url)
                        
                except Exception as e:
                    await self.bot.messager.log(f"No pude scrapear Olé ({url}): {e}", level="ERROR", exc=e)

    async def _extract_news(self, original_url, soup):
        items = []
        
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        if next_data_script:
            try:
                next_data = json.loads(next_data_script.string)
                page_props = next_data.get('props', {}).get('pageProps', {})
                
                all_news_data = self._find_all_lilanews(page_props)
                
                for item in all_news_data:
                     if '/' + original_url + '/' in item.get('url', ''):
                        url = item.get('url', '')
                        if url:
                            title = item.get('title', '')
                            summary_html = item.get('summary', '')
                            description = BeautifulSoup(summary_html, 'html.parser').get_text(strip=True) if summary_html else ""
                            
                            image_url = self._extract_image_url(item)
                            if image_url:
                                image_url = self.bot.news_dao.normalize_url(self.domain, image_url)
                            
                            items.append({
                                'url': url,
                                'title': title,
                                'description': description,
                                'image_url': image_url
                            })

            except (json.JSONDecodeError, TypeError):
                await self.bot.messager.log(f"No pude parsear __NEXT_DATA__ de Olé para '{original_url}'.", level="WARNING")

        return items

    def _find_all_lilanews(self, obj):
        results = []
        if isinstance(obj, dict):
            if obj.get('type') == 'lilanews':
                results.append(obj)
            for value in obj.values():
                results.extend(self._find_all_lilanews(value))
        elif isinstance(obj, list):
            for item in obj:
                results.extend(self._find_all_lilanews(item))
        return results

    def _extract_image_url(self, item):
        images = item.get('images', [])
        if not images:
            return None
        clippings = images[0].get('clippings', [])
        if not clippings:
            return None
        destacada = next((c for c in clippings if c.get('_id') == 'Listado Destacada'), None)
        return (destacada or clippings[0]).get('url')