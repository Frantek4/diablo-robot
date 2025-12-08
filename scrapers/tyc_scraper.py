import requests
from bs4 import BeautifulSoup
import re
import json

from data_access.news import NewsDAO
from models.news_source import NewsSource

class TycSportsScraper:
    def __init__(self, bot):
        self.bot = bot
        self.news_dao = NewsDAO()
        self.url = "https://www.tycsports.com/independiente.html"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    async def scrape_news(self):
        try:
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.encoding = 'utf-8'
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            # Extraer solo los enlaces de noticias de la página principal
            news_links = self._extract_news_links(soup)
            
            for link_data in news_links:
                url = link_data['url']
                if self.news_dao.exists(url):
                    continue

                # Obtener detalles desde la página de la noticia individual
                detail_data = self._get_article_details(url)
                
                if not detail_data['title']: # Si no se pudo obtener título, omitir
                    continue

                # Limpiar título: eliminar " - TyC Sports" al final
                clean_title = re.sub(r'\s*[-–]\s*TyC Sports\s*$', '', detail_data['title'], flags=re.IGNORECASE | re.UNICODE)
                
                await self.bot.messager.news(
                    type=NewsSource.PRESS,
                    title=clean_title,
                    description=detail_data['description'],
                    url=url,
                    image_url=detail_data['image_url'],
                    publisher="TyC Sports",
                    color="#0F1A87"
                )
                self.news_dao.insert(url)
                
            return len(news_links)
        except Exception as e:
            await self.bot.messager.log(f"Error al scrapear TyC Sports: {str(e)}")
            return 0

    def _extract_news_links(self, soup):
        links = []
        
        # Buscar enlaces de noticias en la página principal
        # Buscar enlaces que contengan '/independiente/' en la URL
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/independiente/' in href and '/independiente/' != href.strip('/') and 'reels' not in href.lower():
                url = self.news_dao.normalize_url("https://www.tycsports.com", href)
                if url:
                    links.append({'url': url})
                
        return links

    def _get_article_details(self, article_url):
        try:
            response = requests.get(article_url, headers=self.headers, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extraer el título desde la etiqueta <title> o <h1>
            title = ""
            title_tag = soup.find('title')
            if title_tag:
                # Limpiar el título de la pestaña quitando el "- TyC Sports" temporalmente solo para obtener el texto base
                raw_title = title_tag.get_text(strip=True)
                # Usar la misma lógica de limpieza que al final para obtener solo el título real
                cleaned_for_extraction = re.sub(r'\s*[-–]\s*TyC Sports\s*$', '', raw_title, flags=re.IGNORECASE | re.UNICODE)
                title = cleaned_for_extraction.strip()
            else:
                # Fallback: buscar h1
                h1_tag = soup.find('h1')
                if h1_tag:
                    title = h1_tag.get_text(strip=True)
            
            # Extraer la descripción desde el meta tag 'description'
            description = ""
            desc_meta = soup.find('meta', attrs={'name': 'description'})
            if desc_meta:
                description = desc_meta.get('content', '').strip()
            else:
                # Fallback: buscar h2 o p si no hay meta description
                subtitle_tag = soup.find('h2', class_=lambda x: x and 'headline' not in x.lower())
                if subtitle_tag:
                    description = subtitle_tag.get_text(strip=True)
                else:
                    first_paragraph = soup.find('p', class_=lambda x: x and 'bajada' in x.lower() if x else False)
                    if not first_paragraph:
                        first_paragraph = soup.find('p')
                    if first_paragraph:
                        description = first_paragraph.get_text(strip=True)
            
            # Extraer imagen principal
            image_url = None
            # Priorizar og:image
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                og_img_url = og_image['content']
                if not og_img_url.startswith('data:image'):
                    image_url = self.news_dao.normalize_url("https://www.tycsports.com", og_img_url)
            
            # Si og:image falla, intentar con JSON-LD
            if not image_url:
                schema_article = soup.find('script', type='application/ld+json')
                if schema_article:
                    try:
                        schema_data = json.loads(schema_article.string)
                        if schema_data.get('@type') == 'NewsArticle':
                            images = schema_data.get('image', [])
                            if isinstance(images, list) and len(images) > 0:
                                # Tomar la primera imagen del array
                                img_obj = images[0]
                                if isinstance(img_obj, dict):
                                    img_url = img_obj.get('url')
                                else:
                                    img_url = img_obj # Si es directamente un string
                                if img_url and not img_url.startswith('data:image'):
                                    image_url = self.news_dao.normalize_url("https://www.tycsports.com", img_url)
                    except (json.JSONDecodeError, TypeError):
                        pass # Si no se puede parsear el JSON, ignora

            # Si og:image y JSON-LD fallan, intentar con la imagen principal (mainImg)
            if not image_url:
                img_tag = soup.find('img', class_='mainImg')
                if img_tag:
                    # Priorizar data-src para lazy loading
                    src_value = img_tag.get('data-src') or img_tag.get('src')
                    if src_value and not src_value.startswith('data:image'):
                        image_url = self.news_dao.normalize_url("https://www.tycsports.com", src_value)
            
            return {
                'title': title,
                'description': description,
                'image_url': image_url
            }
        except Exception as e:
            print(f"Error obteniendo detalles de {article_url}: {e}")
            return {'title': '', 'description': '', 'image_url': None}