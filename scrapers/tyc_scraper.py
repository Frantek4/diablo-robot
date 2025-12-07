import requests
from bs4 import BeautifulSoup
from tinydb import TinyDB, Query
import re

class TycSportsScraper:
    def __init__(self, bot):
        self.bot = bot
        self.db = TinyDB('database.json')
        self.news_table = self.db.table('news')
        self.News = Query()
        self.url = "https://www.tycsports.com/independiente.html"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        try:
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            news_items = self._extract_news_items(soup)
            new_news = self._filter_new_news(news_items)
            
            for item in new_news:
                # Limpiar título: eliminar " - TyC Sports" al final
                clean_title = re.sub(r'\s*-\s*TyC Sports\s*$', '', item['title'], flags=re.IGNORECASE)
                
                await self.bot.messager.news(
                    title=clean_title,
                    description=item['description'],
                    url=item['url'],
                    image_url=item['image_url'],
                    publisher="TyC Sports"
                )
                self.news_table.insert({'url': item['url']})
                
            return len(new_news)
        except Exception as e:
            await self.bot.messager.log(f"Error al scrapear TyC Sports: {str(e)}")
            return 0

    def _extract_news_items(self, soup):
        items = []
        
        # Buscar en la sección principal de noticias
        news_section = soup.find('div', class_=lambda x: x and 'teamInfo' in x.lower() if x else False)
        if not news_section:
            news_section = soup
            
        # Buscar artículos y tarjetas de noticias
        articles = news_section.find_all(['article', 'div'], class_=lambda x: x and ('card' in x.lower() or 'nota' in x.lower() or 'content' in x.lower()) if x else False)
        
        for article in articles:
            link_tag = article.find('a', href=True)
            if not link_tag or ('/independiente/' not in link_tag['href'] and '/san-lorenzo/' not in link_tag['href']):
                continue
                
            if 'reels' in link_tag['href'].lower():
                continue
                
            url = self._normalize_url(link_tag['href'])
            if not url:
                continue
                
            # Extraer título
            title_tag = article.find(['h2', 'h3', 'h4', 'div'], class_=lambda x: x and ('title' in x.lower() or 'headline' in x.lower() or 'titulo' in x.lower()) if x else False)
            title = title_tag.get_text(strip=True) if title_tag else ""
            
            # Extraer descripción
            desc_tag = article.find(['p', 'div'], class_=lambda x: x and ('summary' in x.lower() or 'bajada' in x.lower() or 'description' in x.lower() or 'resumen' in x.lower()) if x else False)
            description = desc_tag.get_text(strip=True) if desc_tag else ""
            
            # Extraer imagen
            img_tag = article.find('img', src=True)
            if not img_tag:
                img_tag = article.find('img', {'data-src': True})
            image_url = img_tag['src'] if img_tag and img_tag.get('src') else (img_tag['data-src'] if img_tag and img_tag.get('data-src') else None)
            
            if image_url and not image_url.startswith('http'):
                image_url = f"https://www.tycsports.com{image_url}"
                
            items.append({
                'url': url,
                'title': title,
                'description': description,
                'image_url': image_url
            })
            
        return items

    def _normalize_url(self, url):
        url = url.strip()
        if 'reels' in url.lower():
            return None
            
        if not url.startswith('http'):
            if url.startswith('//'):
                url = 'https:' + url
            elif url.startswith('/'):
                url = f"https://www.tycsports.com{url}"
            else:
                url = f"https://www.tycsports.com/{url}"
        return url if '/independiente/' in url or '/san-lorenzo/' in url else None

    def _filter_new_news(self, items):
        new_items = []
        for item in items:
            if item['url'] and not self.news_table.search(self.News.url == item['url']):
                new_items.append(item)
        return new_items