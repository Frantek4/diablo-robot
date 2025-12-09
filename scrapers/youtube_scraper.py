import asyncio
from datetime import datetime, timedelta
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError, Page
from config.settings import settings
from data_access.influencers import InfluencerDAO
from data_access.news import NewsDAO
from models.influencer import InfluencerModel
from models.social_media import SocialMedia
from urllib.parse import urljoin, urlparse, urlunparse

class YouTubeSessionManager:
    """Gestiona el almacenamiento y renovación de sesiones de YouTube"""
    def __init__(self):
        self.session_file = Path("config/youtube_session.json")
        self.screenshots_dir = Path("assets/screenshots/youtube")
        self._ensure_session_dir()
        self.last_renewal = None
        self.session_max_age = timedelta(hours=24)  # YouTube sessions last longer

    def _ensure_session_dir(self):
        """Asegura que existan los directorios de configuración y screenshots"""
        self.session_file.parent.mkdir(exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)

    def get_stored_session(self) -> Optional[str]:
        """Obtiene la sesión almacenada si existe y es válida"""
        if not self.session_file.exists():
            return None
        try:
            with open(self.session_file, 'r') as f:
                session_data = json.load(f)
            self.last_renewal = datetime.fromisoformat(session_data['renewed_at'])
            return session_data['session_id']
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"YouTubeSessionManager: Error leyendo sesión almacenada: {e}")
            return None

    async def renew_session(self, page: Page) -> Optional[str]:
        """Renueva la sesión de YouTube (generalmente no requiere login para scraping básico)"""
        try:
            print("YouTubeSessionManager: Navegando a YouTube para establecer sesión...")
            await page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=30000)
            
            # Aceptar cookies si aparecen
            await self._handle_cookies(page)
            
            # Verificar que la página cargó correctamente
            if not await self._verify_page_loaded(page):
                print("YouTubeSessionManager: ❌ No se pudo cargar YouTube correctamente")
                screenshot_path = self.screenshots_dir / "youtube_load_failed.png"
                await page.screenshot(path=str(screenshot_path))
                return None
            
            # Extraer cookies de sesión
            session_id = await self._extract_session_cookie(page)
            if session_id:
                self._store_session(session_id)
                self.last_renewal = datetime.now()
                print("YouTubeSessionManager: ✅ Sesión establecida exitosamente")
                return session_id
            
            print("YouTubeSessionManager: ❌ No se pudo extraer session_id")
            return None
        except Exception as e:
            print(f"YouTubeSessionManager: Error renovando sesión: {e}")
            return None

    async def _handle_cookies(self, page: Page):
        """Maneja el banner de cookies de YouTube"""
        cookie_buttons = [
            'button:has-text("Accept all")',
            'button:has-text("Aceptar todo")',
            'button:has-text("I agree")',
            'button:has-text("Acepto")',
            'button[aria-label*="agree"]'
        ]
        for selector in cookie_buttons:
            try:
                button = page.locator(selector)
                if await button.count() > 0 and await button.is_visible():
                    await button.click(timeout=5000)
                    print("YouTubeSessionManager: Cookies aceptadas")
                    await page.wait_for_timeout(2000)
                    return
            except Exception as e:
                print(f"YouTubeSessionManager: Error manejando cookies: {e}")
                continue

    async def _verify_page_loaded(self, page: Page) -> bool:
        """Verifica que YouTube cargó correctamente"""
        try:
            # Esperar a que aparezcan elementos clave de YouTube
            await page.wait_for_selector('ytd-masthead, #header, #guide-button', timeout=20000)
            
            # Verificar que hay contenido en la página
            page_content = await page.evaluate('''() => {
                return {
                    hasHeader: !!document.querySelector('#header, ytd-masthead'),
                    hasSearch: !!document.querySelector('input#search'),
                    hasNavigation: !!document.querySelector('#guide-button, ytd-guide-renderer'),
                    url: window.location.href
                };
            }''')
            
            print(f"YouTubeSessionManager: Verificación de carga - URL: {page_content['url']}")
            print(f"YouTubeSessionManager: Elementos encontrados - Header: {page_content['hasHeader']}, Search: {page_content['hasSearch']}, Navigation: {page_content['hasNavigation']}")
            
            return page_content['hasHeader'] and (page_content['hasSearch'] or page_content['hasNavigation'])
        except Exception as e:
            print(f"YouTubeSessionManager: Error verificando carga de página: {e}")
            return False

    async def _extract_session_cookie(self, page: Page) -> Optional[str]:
        """Extrae el session_id de las cookies de YouTube"""
        try:
            cookies = await page.context.cookies()
            print(f"YouTubeSessionManager: Cookies encontradas: {len(cookies)}")
            
            # YouTube usa varias cookies para la sesión
            session_cookies = []
            for cookie in cookies:
                if cookie["name"] in ["SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO"]:
                    session_cookies.append(cookie)
            
            if session_cookies:
                # Usamos la primera cookie como identificador de sesión
                session_id = session_cookies[0]["value"]
                print(f"YouTubeSessionManager: ✅ Session ID extraído: {session_id[:20]}...")
                return session_id
            
            print("YouTubeSessionManager: ❌ No se encontraron cookies de sesión relevantes")
            return None
        except Exception as e:
            print(f"YouTubeSessionManager: Error extrayendo session cookie: {e}")
            return None

    def _store_session(self, session_id: str):
        """Almacena la sesión en archivo"""
        session_data = {
            'session_id': session_id,
            'renewed_at': datetime.now().isoformat(),
            'user_agent': settings.USER_AGENT
        }
        try:
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            print(f"YouTubeSessionManager: Sesión almacenada en {self.session_file}")
        except Exception as e:
            print(f"YouTubeSessionManager: Error guardando sesión: {e}")

class YouTubeScraper:
    def __init__(self, bot):
        self.bot = bot
        self.accounts_dao = InfluencerDAO()
        self.news_dao = NewsDAO()
        self.base_url = "https://www.youtube.com"
        self.session_manager = YouTubeSessionManager()
        self.navigation_timeout = 30000
        self.interaction_timeout = 20000
        self.current_session_id = None

    async def ensure_valid_session(self, page: Page) -> bool:
        """Verifica y asegura que haya una sesión válida para YouTube"""
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"YouTubeScraper: Intento de verificación de sesión #{attempt}")
                
                if not self.current_session_id:
                    self.current_session_id = self.session_manager.get_stored_session()
                
                if self.current_session_id:
                    print("YouTubeScraper: Intentando usar sesión almacenada...")
                    await self._set_session_cookies(page, self.current_session_id)
                    await page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                    await page.wait_for_timeout(3000)
                    
                    if await self._is_session_valid(page):
                        print("YouTubeScraper: ✅ Sesión válida detectada (almacenada)")
                        return True
                
                print("YouTubeScraper: Estableciendo nueva sesión...")
                new_session_id = await self.session_manager.renew_session(page)
                if new_session_id:
                    self.current_session_id = new_session_id
                    await self._set_session_cookies(page, new_session_id)
                    await page.goto(self.base_url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                    await page.wait_for_timeout(3000)
                    
                    if await self._is_session_valid(page):
                        print("YouTubeScraper: ✅ Sesión establecida y verificada exitosamente")
                        return True
                
                print(f"YouTubeScraper: ❌ Intento #{attempt} fallido")
                if attempt < max_attempts:
                    await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"YouTubeScraper: Error en intento #{attempt}: {e}")
                screenshot_path = self.session_manager.screenshots_dir / f"session_error_{attempt}.png"
                try:
                    await page.screenshot(path=str(screenshot_path))
                    print(f"YouTubeScraper: Screenshot de error de sesión guardado en: {screenshot_path}")
                except:
                    print("YouTubeScraper: No se pudo tomar screenshot del error de sesión")
        
        print("YouTubeScraper: ❌ Todos los intentos de obtener sesión válida fallaron")
        return False

    async def _set_session_cookies(self, page: Page, session_id: str):
        """Establece cookies de sesión con mayor realismo"""
        try:
            await page.context.clear_cookies()
            cookies = [
                {
                    'name': 'SID',
                    'value': session_id,
                    'domain': '.youtube.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': False,
                    'sameSite': 'None'
                },
                {
                    'name': 'HSID',
                    'value': 'ABC123XYZ',
                    'domain': '.youtube.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': False,
                    'sameSite': 'None'
                },
                {
                    'name': 'SSID',
                    'value': 'DEF456UVW',
                    'domain': '.youtube.com',
                    'path': '/',
                    'secure': True,
                    'httpOnly': False,
                    'sameSite': 'None'
                }
            ]
            await page.context.add_cookies(cookies)
            print("YouTubeScraper: Cookies de sesión establecidas")
        except Exception as e:
            print(f"YouTubeScraper: Error estableciendo cookies: {e}")
            raise

    async def _is_session_valid(self, page: Page) -> bool:
        """Verifica si la sesión actual es válida para YouTube"""
        try:
            current_url = page.url.lower().strip()
            print(f"YouTubeScraper: Verificando validez de sesión en URL: {current_url}")
            
            # Verificar que estamos en YouTube
            if "youtube.com" not in current_url:
                print("YouTubeScraper: No estamos en YouTube - sesión inválida")
                return False
            
            # Verificar elementos clave de YouTube
            is_valid = await page.evaluate('''() => {
                const hasHeader = !!document.querySelector('#header, ytd-masthead');
                const hasSearch = !!document.querySelector('input#search');
                const hasNavigation = !!document.querySelector('#guide-button, ytd-guide-renderer');
                const hasContent = !!document.querySelector('ytd-rich-grid-renderer, ytd-section-list-renderer');
                const hasError = !!document.querySelector('ytd-error-renderer, #error-page');
                
                return hasHeader && (hasSearch || hasNavigation) && hasContent && !hasError;
            }''')
            
            print(f"YouTubeScraper: Resultado de verificación: {'válida' if is_valid else 'inválida'}")
            return is_valid
        except Exception as e:
            print(f"YouTubeScraper: Error verificando validez de sesión: {e}")
            return False

    async def scrape_videos(self):
        """Scrapea videos de canales de YouTube usando contexto persistente"""
        print("YouTubeScraper: Iniciando scraping de videos")
        youtube_accounts: List[InfluencerModel] = self.accounts_dao.get_by_platform(SocialMedia.YOUTUBE)
        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        
        print(f"YouTubeScraper: Cuentas obtenidas de la base de datos: {len(youtube_accounts) if youtube_accounts else 0}")
        if not youtube_accounts:
            print("YouTubeScraper: ⚠️ ADVERTENCIA: No hay cuentas de YouTube para procesar")
            print("YouTubeScraper: Verifica que existan cuentas en la base de datos con plataforma YOUTUBE")
            return
        
        print("YouTubeScraper: Cuentas a procesar:")
        for account in youtube_accounts:
            print(f"- {account['name']} ({account['description']})")
        
        browser_context = self.bot.playwright
        try:
            temp_page = await browser_context.new_page()
            try:
                print("YouTubeScraper: Verificando sesión antes de comenzar el scraping...")
                if not await self.ensure_valid_session(temp_page):
                    print("❌ YouTubeScraper: No se pudo obtener sesión válida, abortando scraping")
                    print("""
=== DIAGNÓSTICO DE FALLO DE SESIÓN ===
Archivos de debug generados en assets/screenshots/youtube/:
- youtube_load_failed.png
- session_error_*.png
- channel_not_found_*.png
- no_videos_found_*.png
Verifica las capturas para identificar el problema visualmente
=====================================
""")
                    return
            finally:
                await temp_page.close()
            
            print(f"YouTubeScraper: ✅ Sesión válida establecida. Procesando {len(youtube_accounts)} cuentas")
            
            # Procesar cada cuenta
            for i, account in enumerate(youtube_accounts):
                print(f"YouTubeScraper: Procesando cuenta {i+1}/{len(youtube_accounts)}: {account['name']}")
                try:
                    await self._scrape_channel(account, one_week_ago, browser_context)
                    await asyncio.sleep(3)  # Pausa entre cuentas
                except Exception as e:
                    print(f"YouTubeScraper: ❌ Error procesando cuenta {account['name']}: {e}")
                    import traceback
                    print(f"Detalles del error:\n{traceback.format_exc()}")
                    screenshot_path = self.session_manager.screenshots_dir / f"account_error_{account['name']}.png"
                    try:
                        error_page = await browser_context.new_page()
                        await error_page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                        await error_page.screenshot(path=str(screenshot_path))
                        await error_page.close()
                        print(f"YouTubeScraper: Screenshot de error guardado en: {screenshot_path}")
                    except Exception as screenshot_error:
                        print(f"YouTubeScraper: Error guardando screenshot de error: {screenshot_error}")
            
            print("YouTubeScraper: ✅ Proceso de scraping completado exitosamente")
        except Exception as e:
            print(f"YouTubeScraper: ❌ Error general en scrape_videos: {e}")
            import traceback
            print(f"Detalles del error:\n{traceback.format_exc()}")
        finally:
            print("YouTubeScraper: Finalizando proceso de scraping")

    async def _scrape_channel(self, account: InfluencerModel, since_date: datetime, browser_context):
        """Scrapea un canal de YouTube para obtener videos recientes"""
        print(f"YouTubeScraper: Procesando canal: {account['name']}")
        page = await browser_context.new_page()
        
        try:
            # Navegar al canal
            channel_url = f"{self.base_url}/@{account['name'].strip()}/videos"
            print(f"YouTubeScraper: Navegando al canal: {channel_url}")
            await page.goto(channel_url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
            
            # Verificar que el canal existe
            channel_title = await page.title()
            print(f"YouTubeScraper: Título de la página del canal: {channel_title}")
            
            if "404 Not Found" in channel_title or "Not Found" in channel_title or "No encontrado" in channel_title:
                print(f"YouTubeScraper: Canal no encontrado: {account['name']}")
                screenshot_path = self.session_manager.screenshots_dir / f"channel_not_found_{account['name']}.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"YouTubeScraper: Screenshot guardado en: {screenshot_path}")
                return
            
            # Esperar a que la página del canal se cargue completamente
            await page.wait_for_timeout(5000)
            
            # Tomar screenshot del canal para debug
            screenshot_path = self.session_manager.screenshots_dir / f"channel_{account['name']}.png"
            await page.screenshot(path=str(screenshot_path))
            print(f"YouTubeScraper: Screenshot del canal guardado en: {screenshot_path}")
            
            # Obtener los videos del canal (solo los primeros visibles)
            videos = await self._get_channel_videos(page, account, since_date)
            print(f"YouTubeScraper: Encontrados {len(videos)} videos relevantes en {account['name']}")
            
            # Procesar cada video
            for i, video in enumerate(videos):
                print(f"YouTubeScraper: Procesando video {i+1}/{len(videos)}: {video['url']}")
                try:
                    await self._process_video(video, account, since_date)
                    await asyncio.sleep(2)  # Pausa entre videos
                except Exception as e:
                    print(f"YouTubeScraper: Error procesando video {video['url']}: {e}")
                    import traceback
                    print(f"Detalles del error:\n{traceback.format_exc()}")
            
            print(f"YouTubeScraper: ✅ Procesados {len(videos)} videos de {account['name']}")
            
        except Exception as e:
            print(f"YouTubeScraper: Error procesando {account['name']}: {e}")
            import traceback
            print(f"Detalles del error:\n{traceback.format_exc()}")
            screenshot_path = self.session_manager.screenshots_dir / f"channel_error_{account['name']}.png"
            try:
                await page.screenshot(path=str(screenshot_path))
                print(f"YouTubeScraper: Screenshot de error de canal guardado en: {screenshot_path}")
            except Exception as screenshot_error:
                print(f"YouTubeScraper: Error guardando screenshot de error de canal: {screenshot_error}")
        finally:
            await page.close()

    async def _get_channel_videos(self, page: Page, account: InfluencerModel, since_date: datetime) -> List[Dict]:
        """Obtiene los videos visibles iniciales de un canal de YouTube (sin scrolling)"""
        videos = []
        processed_urls = set()
        
        try:
            print("YouTubeScraper: Obteniendo videos visibles del canal...")
            
            # Seleccionar los elementos de video sin hacer scrolling
            video_selectors = [
                'ytd-rich-item-renderer',
                'ytd-grid-video-renderer',
                'ytd-video-renderer'
            ]
            
            video_elements = []
            for selector in video_selectors:
                try:
                    elements = await page.locator(selector).all()
                    if elements:
                        video_elements = elements
                        print(f"YouTubeScraper: ✅ Encontrados {len(video_elements)} elementos de video con selector: {selector}")
                        break
                except Exception as e:
                    print(f"YouTubeScraper: Selector '{selector}' falló: {e}")
                    continue
            
            if not video_elements:
                print(f"YouTubeScraper: ❌ No se encontraron elementos de video para {account['name']}")
                screenshot_path = self.session_manager.screenshots_dir / f"no_videos_found_{account['name']}.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"YouTubeScraper: Screenshot sin videos guardado en: {screenshot_path}")
                return []
            
            print(f"YouTubeScraper: Encontrados {len(video_elements)} elementos de video, extrayendo detalles...")
            
            # Procesar cada elemento de video (máximo 10 para evitar sobrecarga)
            for element in video_elements[:10]:  # Límite máximo de 10 videos
                try:
                    video_data = await self._extract_video_data(element, page)
                    if not video_data:
                        continue
                    
                    # Verificar si ya procesamos este video
                    if video_data['url'] in processed_urls:
                        continue
                    
                    # Verificar fecha
                    if video_data['published_at'] < since_date:
                        print(f"YouTubeScraper: Video antiguo detectado ({video_data['published_at']}), ignorando")
                        continue
                    
                    videos.append(video_data)
                    processed_urls.add(video_data['url'])
                    
                except Exception as e:
                    print(f"YouTubeScraper: Error extrayendo datos de video: {e}")
                    continue
            
            return videos
            
        except Exception as e:
            print(f"YouTubeScraper: Error obteniendo videos del canal: {e}")
            import traceback
            print(f"Detalles del error:\n{traceback.format_exc()}")
            return []

    async def _extract_video_data(self, element, page: Page) -> Optional[Dict]:
        """Extrae los datos de un elemento de video"""
        try:
            # Obtener URL del video
            url_element = element.locator('a#video-title, a#thumbnail')
            if await url_element.count() == 0:
                return None
            
            href = await url_element.get_attribute('href')
            if not href or '/watch?v=' not in href:
                return None
            
            video_url = f"https://www.youtube.com{href}"
            
            # Obtener título
            title_element = element.locator('#video-title')
            title = await title_element.text_content() if await title_element.count() > 0 else "Sin título"
            title = title.strip()
            
            # Obtener fecha de publicación
            date_element = element.locator('#metadata-line span')
            date_text = await date_element.text_content() if await date_element.count() > 0 else ""
            
            published_at = self._parse_youtube_date(date_text)
            
            # Obtener miniatura
            thumbnail_element = element.locator('img#img')
            thumbnail_url = await thumbnail_element.get_attribute('src') if await thumbnail_element.count() > 0 else ""
            
            # Obtener vistas (si está disponible)
            views_element = element.locator('#metadata-line span:nth-child(2)')
            views_text = await views_element.text_content() if await views_element.count() > 0 else ""
            
            return {
                'url': video_url,
                'title': title,
                'published_at': published_at,
                'thumbnail_url': thumbnail_url,
                'views': views_text.strip() if views_text else "",
                'description': f"Nuevo video de {title}"
            }
        except Exception as e:
            print(f"YouTubeScraper: Error extrayendo datos de video: {e}")
            return None

    def _parse_youtube_date(self, date_text: str) -> datetime:
        """Parsea la fecha de YouTube a objeto datetime"""
        try:
            now = datetime.now(settings.TIMEZONE)
            
            if not date_text:
                return now - timedelta(days=7)  # Fecha por defecto
            
            date_text = date_text.lower().strip()
            
            # Formatos comunes de YouTube
            if "streamed" in date_text or "transmitido" in date_text:
                date_text = date_text.replace("streamed", "").replace("transmitido", "").strip()
            
            if "ago" in date_text or "atrás" in date_text:
                # "2 days ago", "1 week ago", etc.
                if "hour" in date_text or "hora" in date_text:
                    hours = int(re.search(r'\d+', date_text).group())
                    return now - timedelta(hours=hours)
                elif "day" in date_text or "día" in date_text:
                    days = int(re.search(r'\d+', date_text).group())
                    return now - timedelta(days=days)
                elif "week" in date_text or "semana" in date_text:
                    weeks = int(re.search(r'\d+', date_text).group())
                    return now - timedelta(weeks=weeks)
                elif "month" in date_text or "mes" in date_text:
                    months = int(re.search(r'\d+', date_text).group())
                    return now - timedelta(days=months*30)
                elif "year" in date_text or "año" in date_text:
                    years = int(re.search(r'\d+', date_text).group())
                    return now - timedelta(days=years*365)
            
            # Intentar parsear como fecha normal
            try:
                return datetime.strptime(date_text, '%Y-%m-%d').replace(tzinfo=settings.TIMEZONE)
            except ValueError:
                try:
                    return datetime.strptime(date_text, '%b %d, %Y').replace(tzinfo=settings.TIMEZONE)
                except ValueError:
                    return now - timedelta(days=1)  # Fecha por defecto
            
        except Exception as e:
            print(f"YouTubeScraper: Error parseando fecha '{date_text}': {e}")
            return datetime.now(settings.TIMEZONE) - timedelta(days=1)

    async def _process_video(self, video_data: Dict, account: InfluencerModel, since_date: datetime):
        """Procesa un video individual"""
        if self.news_dao.exists(video_data['url']):
            print(f"YouTubeScraper: Video ya procesado: {video_data['url']}")
            return
        
        try:
            # Crear título y descripción
            title = f"📹 Nuevo video de {account['description']} en YouTube"
            description = video_data['title']
            
            if len(description) > 500:
                description = description[:497] + '...'
            
            print(f"YouTubeScraper: Enviando notificación para: {video_data['url']}")
            print(f"YouTubeScraper: Título: {title}")
            print(f"YouTubeScraper: Descripción: {description[:100]}...")
            
            await self.bot.messager.news(
                type=account['source'],
                title=title,
                description=description,
                url=video_data['url'],
                image_url=video_data.get('thumbnail_url', ''),
                publisher=f"{account['description']} en YouTube",
                color="#FF0000"  # YouTube color
            )
            
            self.news_dao.insert(video_data['url'])
            print(f"YouTubeScraper: ✅ Video procesado: {video_data['url']}")
            
        except Exception as e:
            print(f"YouTubeScraper: Error notificando video {video_data['url']}: {e}")
            import traceback
            print(f"Detalles del error:\n{traceback.format_exc()}")