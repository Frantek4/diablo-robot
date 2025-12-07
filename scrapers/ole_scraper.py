import requests
from bs4 import BeautifulSoup
from tinydb import TinyDB, Query
import os

class OleScraper:
    def __init__(self, bot):
        self.bot = bot
        self.db = TinyDB('database.json')
        self.news_table = self.db.table('news')
        self.News = Query()
        self.url = "https://www.ole.com.ar/independiente"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        try:
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            news_urls = self._extract_news_urls(soup)
            new_news = self._filter_new_news(news_urls)
            
            for url in new_news:
                await self.bot.messager.news(url,"Olé")
                self.news_table.insert({'url': url})
                
            return len(new_news)
        except Exception as e:
            await self.bot.messager.log(f"Error al scrapear Olé: {str(e)}")
            return 0

    def _extract_news_urls(self, soup):
        urls = []
        
        # Buscar en diferentes secciones donde podrían estar las noticias
        # 1. Buscar en artículos con clases específicas que contengan noticias de Independiente
        articles = soup.find_all('article', class_=lambda x: x and 'nota' in x.lower() if x else False)
        
        for article in articles:
            link_tag = article.find('a', href=True)
            if link_tag and '/independiente/' in link_tag['href']:
                full_url = self._normalize_url(link_tag['href'])
                if full_url and full_url not in urls:
                    urls.append(full_url)
        
        # 2. Buscar en listas de noticias
        news_lists = soup.find_all(['ul', 'div'], class_=lambda x: x and ('list' in x.lower() or 'noticias' in x.lower() or 'content' in x.lower()) if x else False)
        
        for news_list in news_lists:
            for link_tag in news_list.find_all('a', href=True):
                if '/independiente/' in link_tag['href'] and not any(x in link_tag['href'] for x in ['/agenda-deportiva', '/estadisticas', '/autores', '/tags']):
                    full_url = self._normalize_url(link_tag['href'])
                    if full_url and full_url not in urls:
                        urls.append(full_url)
        
        # 3. Buscar en tarjetas/notas destacadas
        cards = soup.find_all('div', class_=lambda x: x and ('card' in x.lower() or 'nota' in x.lower()) if x else False)
        
        for card in cards:
            link_tag = card.find('a', href=True)
            if link_tag and '/independiente/' in link_tag['href']:
                full_url = self._normalize_url(link_tag['href'])
                if full_url and full_url not in urls:
                    urls.append(full_url)
        
        # 4. Buscar en secciones específicas del JSON-LD o data-attributes
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            if '"independiente"' in script.text.lower():
                # Extraer URLs de posibles estructuras de datos
                import json
                try:
                    data = json.loads(script.text)
                    if isinstance(data, dict) and 'itemListElement' in data:
                        for item in data['itemListElement']:
                            if 'url' in item and '/independiente/' in item['url']:
                                full_url = self._normalize_url(item['url'])
                                if full_url and full_url not in urls:
                                    urls.append(full_url)
                except:
                    pass
        
        return urls

    def _normalize_url(self, url):
        if not url.startswith('http'):
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = f"https://www.ole.com.ar{url}"
            else:
                url = f"https://www.ole.com.ar/{url}"
        return url if '/independiente/' in url else None

    def _filter_new_news(self, urls):
        new_urls = []
        for url in urls:
            if url and not self.news_table.search(self.News.url == url):
                new_urls.append(url)
        return new_urls