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
        self.url = "https://www.ole.com.ar/independiente"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        try:
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            news = self._extract_news(soup)

            for item in news:
                url = self.news_dao.normalize_url("https://www.ole.com.ar", item['url'])
                if self.news_dao.exists(url):
                    continue
                
                # Limpiar descripción: eliminar " Mirá." al final
                clean_description = re.sub(r'\s*Mirá\.\s*$', '', item['description'], flags=re.IGNORECASE | re.UNICODE)
                
                await self.bot.messager.news(
                    type=NewsSource.PRESS,
                    title=item['title'],
                    description=clean_description,
                    url=url,
                    image_url=item['image_url'],
                    publisher="Olé",
                    color="#A6CE39"
                )
                self.news_dao.insert(url)
                
            return len(news)
        except Exception as e:
            await self.bot.messager.log(f"Error al scrapear Olé: {str(e)}")
            return 0

    def _extract_news(self, soup):
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
                     if '/independiente/' in item.get('url', ''):
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
                                image_url = self.news_dao.normalize_url("https://www.ole.com.ar", image_url)
                            
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