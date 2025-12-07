import requests
from bs4 import BeautifulSoup
from tinydb import TinyDB, Query

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
            news_urls = self._extract_news_urls(soup)
            new_news = self._filter_new_news(news_urls)
            
            for url in new_news:
                await self.bot.messager.news(url,"TyC Sports")
                self.news_table.insert({'url': url})
                
            return len(new_news)
        except Exception as e:
            await self.bot.messager.log(f"Error al scrapear TyC Sports: {str(e)}")
            return 0

    def _extract_news_urls(self, soup):
        urls = []
        
        # 1. Buscar en artículos principales
        articles = soup.find_all('article', class_=lambda x: x and ('nota' in x.lower() or 'article' in x.lower()) if x else False)
        
        for article in articles:
            link_tag = article.find('a', href=True)
            if link_tag and ('/independiente/' in link_tag['href'] or '/san-lorenzo/' in link_tag['href']):
                full_url = self._normalize_url(link_tag['href'])
                if full_url and full_url not in urls:
                    urls.append(full_url)
        
        # 2. Buscar en tarjetas de noticias
        cards = soup.find_all('div', class_=lambda x: x and ('card' in x.lower() or 'content' in x.lower()) if x else False)
        
        for card in cards:
            link_tag = card.find('a', href=True)
            if link_tag and '/independiente/' in link_tag['href']:
                full_url = self._normalize_url(link_tag['href'])
                if full_url and full_url not in urls:
                    urls.append(full_url)
        
        # 3. Buscar en listas de noticias
        news_items = soup.find_all(['li', 'div'], class_=lambda x: x and ('item' in x.lower() or 'noticia' in x.lower() or 'news' in x.lower()) if x else False)
        
        for item in news_items:
            link_tag = item.find('a', href=True)
            if link_tag and '/independiente/' in link_tag['href']:
                full_url = self._normalize_url(link_tag['href'])
                if full_url and full_url not in urls:
                    urls.append(full_url)
        
        # 4. Buscar en el menú o secciones destacadas
        nav_items = soup.find_all('a', href=True)
        for link_tag in nav_items:
            if '/independiente/' in link_tag['href'] and '/noticia/' in link_tag['href']:
                full_url = self._normalize_url(link_tag['href'])
                if full_url and full_url not in urls:
                    urls.append(full_url)
        
        return urls

    def _normalize_url(self, url):
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

    def _filter_new_news(self, urls):
        new_urls = []
        for url in urls:
            if url and not self.news_table.search(self.News.url == url):
                new_urls.append(url)
        return new_urls