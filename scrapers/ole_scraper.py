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
                await self.bot.messager.news(url)
                self.news_table.insert({'url': url})
                
            return len(new_news)
        except Exception as e:
            await self.bot.messager.log(f"Error al scrapear Ole: {str(e)}")
            return 0

    def _extract_news_urls(self, soup):
        urls = []
        cards = soup.find_all('div', class_='card')
        
        for card in cards[:9]:
            link_tag = card.find('a', href=True)
            if link_tag and '/independiente/' in link_tag['href']:
                full_url = link_tag['href'] if link_tag['href'].startswith('http') else f"https://www.ole.com.ar{link_tag['href']}"
                if full_url not in urls:
                    urls.append(full_url)
        
        return urls

    def _filter_new_news(self, urls):
        new_urls = []
        for url in urls:
            if not self.news_table.search(self.News.url == url):
                new_urls.append(url)
        return new_urls