import requests
from bs4 import BeautifulSoup
import re
import json

from data_access.news import NewsDAO
from models.news_source import NewsSource

class OleScraper:
    def __init__(self, bot):
        self.bot = bot
        self.news_dao = NewsDAO()
        self.domain = "https://www.ole.com.ar"
        self.urls = ["independiente","seleccion","mundial","futbol-primera"]
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        for url in self.urls:
            try:
                response = requests.get(self.domain + "/" + url, headers=self.headers, timeout=10)
                response.encoding = 'utf-8'
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                news = self._extract_news(url, soup)

                for item in news:
                    news_url = self.news_dao.normalize_url(self.domain, item['url'])
                    if self.news_dao.exists(news_url):
                        continue
                    
                    clean_description = re.sub(r'\s*Mirá\.\s*$', '', item['description'], flags=re.IGNORECASE | re.UNICODE)
                    
                    await self.bot.messager.news(
                        type=NewsSource.PRESS,
                        title=item['title'],
                        description=clean_description,
                        url=news_url,
                        image_url=item['image_url'],
                        publisher= f"Olé • {url}",
                        color="#A6CE39"
                    )
                    self.news_dao.insert(news_url)
                    
            except Exception as e:
                await self.bot.messager.log(f"Error al scrapear Olé ({url}): {str(e)}")
        

    def _extract_news(self, original_url, soup):
        items = []
        
        # Buscar el script __NEXT_DATA__
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        if next_data_script:
            try:
                next_data = json.loads(next_data_script.string)
                # Extraer noticias del JSON de Next.js
                page_props = next_data.get('props', {}).get('pageProps', {})
                
                # Buscar recursivamente todos los objetos con type 'lilanews'
                all_news_data = self._find_all_lilanews(page_props)
                
                for item in all_news_data:
                     # Verificar que sea una noticia de independiente
                     if '/' + original_url + '/' in item.get('url', ''):
                        url = item.get('url', '')
                        if url:
                            # Extraer título
                            title = item.get('title', '')
                            # Extraer summary (descripción) y convertir HTML a texto
                            summary_html = item.get('summary', '')
                            description = BeautifulSoup(summary_html, 'html.parser').get_text(strip=True) if summary_html else ""
                            
                            # Extraer imagen - SIMPLIFICADO
                            image_url = self._extract_image_url(item)
                            if image_url:
                                image_url = self.news_dao.normalize_url(self.domain, image_url)
                            
                            items.append({
                                'url': url,
                                'title': title,
                                'description': description,
                                'image_url': image_url
                            })

            except (json.JSONDecodeError, TypeError):
                print("OleScraper: No se pudo parsear __NEXT_DATA__")

        return items

    def _find_all_lilanews(self, obj):
        """Busca recursivamente todos los objetos con type 'lilanews'."""
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
        """Extrae la URL de la imagen principal."""
        image_url = None
        # Buscar en 'images' en lugar de 'clippings'
        images = item.get('images', [])
        if images:
            # Tomar la primera imagen de la lista
            first_image = images[0]
            # Buscar 'clippings' dentro de la primera imagen
            clippings = first_image.get('clippings', [])
            if clippings:
                # Buscar clipping con id 'Listado Destacada'
                destacada_clip = next((clip for clip in clippings if clip.get('_id') == 'Listado Destacada'), None)
                if destacada_clip:
                    image_url = destacada_clip.get('url')
                else:
                    # Si no se encuentra, tomar el primer clipping
                    image_url = clippings[0].get('url')
        return image_url