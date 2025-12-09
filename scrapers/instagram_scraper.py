import asyncio
import re
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from playwright.async_api import Page, BrowserContext
from utils.session_manager import SessionManager
from utils.anti_detection import HumanEmulation

# Importar tus DAOs y modelos
from models.influencer import InfluencerModel, SocialMedia
from data_access.influencers import InfluencerDAO
from data_access.news import NewsDAO
from config.settings import settings

class InstagramScraper:
    """Scraper de Instagram que trabaja exclusivamente en el feed principal"""
    
    def __init__(self, bot: Any):
        self.bot = bot
        self.accounts_dao = InfluencerDAO()
        self.news_dao = NewsDAO()
        self.base_url = "https://www.instagram.com/"
        self.username = settings.IG_USERNAME
        self.password = settings.IG_PASSWORD
        self.session_manager = SessionManager()
        self.navigation_timeout = 30000
        self.interaction_timeout = 20000
        self.current_session_id = None
    
    async def ensure_valid_session(self, page: Page) -> bool:
        """Verifica y asegura que haya una sesión válida con manejo mejorado de login en URL principal"""
        print("InstagramScraper: Verificando sesión...")
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                print(f"InstagramScraper: Intento #{attempt} de verificación de sesión")
                
                # Limpiar cookies existentes
                await page.context.clear_cookies()
                
                # Navegar a URL principal
                clean_url = "https://www.instagram.com/"
                print(f"InstagramScraper: Navegando a: {clean_url}")
                await page.goto(clean_url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                await asyncio.sleep(random.uniform(2, 4))
                
                # Verificar sesión
                if await self._is_session_valid(page):
                    print("InstagramScraper: ✅ Sesión válida detectada")
                    return True
                
                print("InstagramScraper: ❌ Sesión no válida, intentando renovar...")
                new_session_id = await self.session_manager.renew_session(page, self.username, self.password)
                if new_session_id:
                    print("InstagramScraper: ✅ Sesión renovada exitosamente")
                    # Verificar nuevamente después de renovar
                    await page.goto(clean_url, wait_until="domcontentloaded", timeout=self.navigation_timeout)
                    await asyncio.sleep(random.uniform(2, 4))
                    if await self._is_session_valid(page):
                        print("InstagramScraper: ✅ Sesión verificada después de renovar")
                        return True
                
                print(f"InstagramScraper: ❌ Intento #{attempt} fallido")
                if attempt < max_attempts:
                    await asyncio.sleep(random.uniform(5, 10))
            
            except Exception as e:
                print(f"InstagramScraper: Error en intento #{attempt}: {e}")
                import traceback
                print(f"Detalles del error: {traceback.format_exc()}")
                screenshot_path = self.session_manager.screenshots_dir / f"session_error_{attempt}.png"
                try:
                    await page.screenshot(path=str(screenshot_path))
                    print(f"InstagramScraper: Screenshot de error guardado en: {screenshot_path}")
                except:
                    print("InstagramScraper: No se pudo tomar screenshot del error")
        
        print("InstagramScraper: ❌ Todos los intentos de obtener sesión válida fallaron")
        return False
    
    async def _is_session_valid(self, page: Page) -> bool:
        """Verificación más robusta de sesión válida"""
        try:
            # Verificar redirección a login
            if "/login/" in page.url or "/accounts/login/" in page.url:
                return False
                
            # Verificar elementos de sesión con selectores específicos
            session_indicators = [
                'a[href="/direct/inbox/"], a[href="/explore/"]',
                'div[role="feed"], section[role="feed"]',
                '[aria-label="Home"], [aria-label="Inicio"]',
                'nav[aria-label="Menú principal"], nav[aria-label="Main menu"]'
            ]
            
            visible_count = 0
            for selector in session_indicators:
                elements = await page.locator(selector).all()
                for el in elements:
                    if await el.is_visible():
                        visible_count += 1
                        break
                        
            return visible_count >= 2  # Requiere al menos 2 indicadores visibles
            
        except Exception as e:
            print(f"Error verificando sesión: {e}")
            return False
    
    async def scrape_posts(self):
        """Método principal para scrapear publicaciones del feed principal"""
        print("InstagramScraper: Iniciando scraping de publicaciones")
        
        # Obtener cuentas de Instagram a monitorear
        instagram_accounts: List[InfluencerModel] = self.accounts_dao.get_by_platform(SocialMedia.INSTAGRAM)
        one_week_ago = datetime.now(settings.TIMEZONE) - timedelta(days=7)
        
        print(f"InstagramScraper: Cuentas obtenidas: {len(instagram_accounts)}")
        if not instagram_accounts:
            print("InstagramScraper: ⚠️ No hay cuentas de Instagram para procesar")
            return
        
        print("InstagramScraper: Cuentas a procesar:")
        for account in instagram_accounts:
            print(f"- {account['name']} ({account['description']})")
        
        # Obtener contexto persistente
        browser_context = self.bot.playwright_config.get_context()
        print("InstagramScraper: ✅ Contexto persistente obtenido")
        
        # Crear nueva pestaña
        page = await browser_context.new_page()
        
        try:
            # Verificar sesión
            if not await self.ensure_valid_session(page):
                print("❌ InstagramScraper: No se pudo obtener sesión válida, abortando scraping")
                return
            
            print("InstagramScraper: ✅ Sesión válida establecida")
            
            # Navegar al feed principal
            print("InstagramScraper: Navegando al feed principal...")
            await page.goto(self.base_url, timeout=self.navigation_timeout, wait_until="domcontentloaded")
            await HumanEmulation.random_delay(2000, 4000)
            
            # Tomar screenshot del feed inicial
            await self.session_manager.take_screenshot(page, "feed_initial")
            
            # Hacer scrolling para cargar posts
            print("InstagramScraper: Realizando scrolling para cargar 30 publicaciones...")
            await self._human_scroll_to_load_posts(page, target_post_count=30)
            
            # Extraer posts del feed
            print("InstagramScraper: Extrayendo posts del feed...")
            valid_posts = await self._extract_and_filter_feed_posts(page, instagram_accounts, one_week_ago)
            
            print(f"InstagramScraper: ✅ Encontrados {len(valid_posts)} posts relevantes")
            
            # Procesar posts válidos
            for i, post_data in enumerate(valid_posts):
                print(f"InstagramScraper: Procesando post {i+1}/{len(valid_posts)}: {post_data['url']}")
                await self._process_feed_post(post_data, instagram_accounts, one_week_ago)
                await HumanEmulation.random_delay(1000, 2500)
            
            print("InstagramScraper: ✅ Proceso de scraping completado exitosamente")
            
        except Exception as e:
            print(f"InstagramScraper: ❌ Error general en scrape_posts: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")
            await self.session_manager.take_screenshot(page, "general_error")
        finally:
            await page.close()
            print("InstagramScraper: ✅ Pestaña cerrada")
    
    async def _human_scroll_to_load_posts(self, page: Page, target_post_count: int = 30):
        """Realiza scrolling humano para cargar posts en el feed"""
        from utils.anti_detection import HumanEmulation
        
        print(f"InstagramScraper: Iniciando scrolling para cargar al menos {target_post_count} posts")
        
        initial_post_count = await self._count_feed_posts(page)
        print(f"InstagramScraper: Posts iniciales detectados: {initial_post_count}")
        
        max_scrolls = 20  # Límite de scrolls
        scrolls_performed = 0
        last_post_count = initial_post_count
        
        while scrolls_performed < max_scrolls:
            current_post_count = await self._count_feed_posts(page)
            print(f"InstagramScraper: Posts actuales: {current_post_count}")
            
            # Verificar si alcanzamos el objetivo
            if current_post_count >= target_post_count:
                print(f"InstagramScraper: ✅ Objetivo alcanzado: {current_post_count} posts >= {target_post_count}")
                break
            
            # Verificar si no hay más posts para cargar
            if current_post_count == last_post_count and scrolls_performed > 3:
                print(f"InstagramScraper: ⚠️ No se cargaron nuevos posts después de {scrolls_performed} scrolls")
                break
            
            # Realizar scroll humano
            scroll_amount = random.randint(400, 800)
            print(f"InstagramScraper: Realizando scroll #{scrolls_performed + 1}/{max_scrolls} - Cantidad: {scroll_amount}px")
            await HumanEmulation.human_scroll(page, scroll_amount)
            
            # Esperar a que se carguen nuevos posts
            wait_time = random.uniform(1.5, 3.0)
            print(f"InstagramScraper: Esperando {wait_time:.2f} segundos para que se carguen nuevos posts...")
            await asyncio.sleep(wait_time)
            
            # Movimiento de mouse aleatorio para parecer humano
            if random.random() > 0.3:
                viewport = await page.evaluate('''() => {
                    return {
                        width: window.innerWidth,
                        height: window.innerHeight
                    };
                }''')
                
                random_x = random.randint(100, viewport['width'] - 100)
                random_y = random.randint(100, viewport['height'] - 100)
                await page.mouse.move(random_x, random_y, steps=random.randint(3, 8))
                await asyncio.sleep(random.uniform(0.3, 1.2))
            
            # Hover sobre algún post para simular interacción humana
            if random.random() > 0.5:
                try:
                    visible_posts = await page.locator('article').all()
                    if visible_posts:
                        random_post = random.choice(visible_posts[:3])
                        if await random_post.is_visible():
                            await random_post.hover()
                            await asyncio.sleep(random.uniform(0.8, 2.0))
                except:
                    pass
            
            last_post_count = current_post_count
            scrolls_performed += 1
        
        final_post_count = await self._count_feed_posts(page)
        print(f"InstagramScraper: Scrolling completado. Posts finales: {final_post_count}")
        await self.session_manager.take_screenshot(page, "feed_after_scrolling")
    
    async def _count_feed_posts(self, page: Page) -> int:
        """Cuenta los posts visibles en el feed"""
        try:
            post_selectors = [
                'article',
                'div[role="article"]',
                'div.x1lliihq:has(a[href*="/p/"])',
                'div._aabd._aa8h._aa9d'
            ]
            
            for selector in post_selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        return count
                except:
                    continue
            
            return 0
        except Exception as e:
            print(f"InstagramScraper: Error contando posts: {e}")
            return 0
    
    async def _extract_and_filter_feed_posts(self, page: Page, accounts: List[InfluencerModel], since_date: datetime) -> List[Dict]:
        """Extrae y filtra posts del feed que pertenecen a cuentas monitorizadas"""
        account_names = {account['name'].lower() for account in accounts}
        valid_posts = []
        
        try:
            # Seleccionar todos los posts visibles
            post_elements = await page.locator('article').all()
            print(f"InstagramScraper: Encontrados {len(post_elements)} posts en el feed")
            
            for post in post_elements:
                try:
                    # Extraer datos del post
                    post_data = await self._extract_post_from_feed(page, post, account_names, since_date)
                    if post_data:
                        valid_posts.append(post_data)
                        print(f"InstagramScraper: ✅ Post válido encontrado: {post_data['url']} de @{post_data['author']}")
                except Exception as e:
                    print(f"InstagramScraper: ❌ Error extrayendo post: {e}")
                    continue
            
            print(f"InstagramScraper: ✅ Total posts válidos: {len(valid_posts)}")
            return valid_posts
            
        except Exception as e:
            print(f"InstagramScraper: ❌ Error extrayendo posts del feed: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")
            await self.session_manager.take_screenshot(page, "feed_extraction_error")
            return []
    
    async def _extract_post_from_feed(self, page: Page, post_element, account_names: set, since_date: datetime) -> Optional[Dict]:
        """Extrae datos de un post individual del feed"""
        try:
            # 1. Extraer autor del post
            author = None
            author_selectors = [
                'a[role="link"]:not([href="/direct/inbox/"]):not([href="/"])',
                'header a[href*="/"]',
                'span a[href*="/"]'
            ]
            
            for selector in author_selectors:
                try:
                    author_el = post_element.locator(selector).first
                    if await author_el.count() > 0:
                        href = await author_el.get_attribute("href")
                        if href and href.strip().startswith('/'):
                            author = href.strip('/').split('/')[0]
                            break
                except:
                    continue
            
            if not author or author.lower() not in account_names:
                return None
            
            # 2. Extraer URL del post
            post_url = None
            url_selectors = [
                'a[href*="/p/"]',
                'a[href*="/reel/"]'
            ]
            
            for selector in url_selectors:
                try:
                    url_el = post_element.locator(selector).first
                    if await url_el.count() > 0:
                        href = await url_el.get_attribute("href")
                        if href and href.strip():
                            post_url = f"https://www.instagram.com{href.strip()}"
                            break
                except:
                    continue
            
            if not post_url or self.news_dao.exists(post_url):
                return None
            
            # 3. Extraer timestamp
            datetime_str = None
            time_selectors = [
                'time[datetime]',
                'time'
            ]
            
            for selector in time_selectors:
                try:
                    time_el = post_element.locator(selector).first
                    if await time_el.count() > 0:
                        datetime_str = await time_el.get_attribute('datetime')
                        if datetime_str:
                            break
                except:
                    continue
            
            if not datetime_str:
                return None
            
            # Convertir timestamp
            try:
                post_time = datetime.fromisoformat(datetime_str.replace('Z', '+00:00')).astimezone(settings.TIMEZONE)
                if post_time < since_date:
                    return None
            except Exception as e:
                print(f"InstagramScraper: ❌ Error parseando fecha: {e}")
                return None
            
            # 4. Extraer descripción
            description = await self._extract_post_description(post_element)
            
            # 5. Extraer imagen
            image_url = await self._extract_post_image(post_element)
            
            return {
                'url': post_url,
                'author': author.lower(),
                'taken_at': post_time,
                'description': description,
                'image_url': image_url
            }
            
        except Exception as e:
            print(f"InstagramScraper: ❌ Error extrayendo datos de post: {e}")
            return None
    
    async def _extract_post_description(self, post_element) -> str:
        """Extrae la descripción de un post"""
        try:
            # Método 1: Buscar en el texto del post
            description = await post_element.evaluate('''el => {
                const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
                let text = "";
                let node;
                while (node = walker.nextNode()) {
                    const t = node.textContent.trim();
                    if (t && t.length > 2 && !t.includes("Ver más") && !t.includes("Me gusta") && !t.includes("Seguir")) {
                        text += t + " ";
                    }
                }
                return text.trim();
            }''')
            
            if description and len(description) > 20:
                return self._clean_description(description)
            
            # Método 2: Buscar en elementos específicos
            desc_selectors = [
                'span[aria-describedby]',
                'div[role="button"]:has-text("Ver más") + span',
                'div._aa_c > span',
                'div.x193iq5w > span'
            ]
            
            for selector in desc_selectors:
                try:
                    desc_el = post_element.locator(selector).first
                    if await desc_el.count() > 0:
                        desc_text = await desc_el.text_content()
                        if desc_text and len(desc_text.strip()) > 20:
                            return self._clean_description(desc_text.strip())
                except:
                    continue
            
            return "Publicación sin descripción"
            
        except Exception as e:
            print(f"InstagramScraper: ❌ Error extrayendo descripción: {e}")
            return "Publicación sin descripción"
    
    async def _extract_post_image(self, post_element) -> Optional[str]:
        """Extrae la URL de la imagen del post"""
        try:
            img_selectors = [
                'img[src*="instagram.com"]',
                'img[src*="cdninstagram.com"]',
                'img[alt*="Photo"]',
                'img[alt*="photo"]',
                'img[alt*="Foto"]',
                'div._aagv img'
            ]
            
            for selector in img_selectors:
                try:
                    img_el = post_element.locator(selector).first
                    if await img_el.count() > 0:
                        src = await img_el.get_attribute("src")
                        if src and src.startswith('http'):
                            return src
                except:
                    continue
            
            return None
        except Exception as e:
            print(f"InstagramScraper: ❌ Error extrayendo imagen: {e}")
            return None
    
    def _clean_description(self, text: str) -> str:
        """Limpia la descripción de textos no deseados"""
        unwanted_phrases = [
            "Ver traducción", "Ver más", "Seguir", "Guardar", "Me gusta", 
            "Responder", "Compartir", "Más opciones", "Ver respuestas", 
            "Ver todos los comentarios", "Like", "Comment", "Share", 
            "Follow", "Save", "See translation", "See more", "View all comments"
        ]
        
        for phrase in unwanted_phrases:
            text = text.replace(phrase, "")
        
        # Limpiar espacios múltiples
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Limitar longitud
        if len(text) > 500:
            text = text[:497] + '...'
        
        return text
    
    async def _process_feed_post(self, post_data: Dict, accounts: List[InfluencerModel], since_date: datetime):
        """Procesa un post del feed para enviar a Discord"""
        if self.news_dao.exists(post_data['url']):
            print(f"InstagramScraper: Post ya procesado: {post_data['url']}")
            return
        
        # Encontrar cuenta correspondiente
        account = next((acc for acc in accounts if acc['name'].lower() == post_data['author']), None)
        if not account:
            return
        
        # Determinar título
        title = f"Publicación de {account['description']} en Instagram"
        
        try:
            print(f"InstagramScraper: Enviando notificación para: {post_data['url']}")
            print(f"InstagramScraper: Título: {title}")
            print(f"InstagramScraper: Descripción: {post_data['description'][:100]}...")
            
            await self.bot.messager.news(
                type=account['source'],
                title=title,
                description=post_data['description'],
                url=post_data['url'],
                image_url=post_data.get('image_url', ''),
                publisher=f"{account['description']} en Instagram",
                color="#E4405F"  # Color Instagram
            )
            
            self.news_dao.insert(post_data['url'])
            print(f"InstagramScraper: ✅ Post procesado: {post_data['url']}")
            
        except Exception as e:
            print(f"InstagramScraper: ❌ Error notificando post {post_data['url']}: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")

    async def handle_intermediate_screens(self, page: Page) -> bool:
        """Maneja pantallas intermedias automáticas después del login"""
        from utils.anti_detection import HumanEmulation
        
        try:
            print("SessionManager: Detectando pantallas intermedias automáticas...")
            max_attempts = 8
            
            for attempt in range(max_attempts):
                await asyncio.sleep(random.uniform(1.5, 3.0))
                
                # Detectar múltiples tipos de pantallas intermedias
                intermediate_screens = {
                    'save_login_info': {
                        'selectors': [
                            'button:has-text("Not Now"), button:has-text("Ahora no"), button:has-text("No ahora")',
                            'button:has-text("Save Info"), button:has-text("Guardar información")'
                        ],
                        'action': 'click'
                    },
                    'notifications': {
                        'selectors': [
                            'button:has-text("Not Now"), button:has-text("Ahora no"), button:has-text("Later"), button:has-text("Más tarde")',
                            'button:has-text("Turn On"), button:has-text("Activar notificaciones")'
                        ],
                        'action': 'click'
                    },
                    'verification_code': {
                        'selectors': [
                            'input[inputmode="numeric"], input[aria-label*="verification"], input[aria-label*="código"]',
                            'button:has-text("Send Security Code"), button:has-text("Enviar código")'
                        ],
                        'action': 'skip'  # Requiere manejo especial
                    },
                    'cookies_consent': {
                        'selectors': [
                            'button:has-text("Allow"), button:has-text("Permitir"), button:has-text("Accept")',
                            'button:has-text("Decline"), button:has-text("Rechazar"), button:has-text("Only essential")'
                        ],
                        'action': 'click'
                    },
                    'app_download': {
                        'selectors': [
                            'div[role="dialog"]:has-text("Get the app"), div[role="dialog"]:has-text("Descargar aplicación")',
                            'button:has-text("Cancel"), button:has-text("Cancelar"), button:has-text("Close"), button:has-text("Cerrar")'
                        ],
                        'action': 'click'
                    },
                    'unexpected_login': {
                        'selectors': [
                            'div[role="main"]:has-text("Log in"), div[role="main"]:has-text("Iniciar sesión")',
                            'form#loginForm, form:has(input[name="username"])'
                        ],
                        'action': 'login_retry'
                    }
                }
                
                for screen_type, config in intermediate_screens.items():
                    for selector in config['selectors']:
                        try:
                            elements = page.locator(selector)
                            count = await elements.count()
                            
                            if count > 0 and await elements.first.is_visible():
                                print(f"SessionManager: 🎯 Detectada pantalla intermedia: {screen_type}")
                                await self.take_screenshot(page, f"intermediate_screen_{screen_type}")
                                
                                if config['action'] == 'click':
                                    button = elements.first
                                    if await button.is_enabled():
                                        await HumanEmulation.human_click(page, button)
                                        print(f"SessionManager: ✅ Acción realizada en: {screen_type}")
                                        await asyncio.sleep(random.uniform(2.0, 4.0))
                                        break
                                        
                        except Exception as e:
                            continue
                
                # Verificar si ya estamos en el feed principal
                if await self.session_manager._is_logged_in(page):
                    print("SessionManager: ✅ No hay más pantallas intermedias - sesión establecida")
                    await page.wait_for_timeout(3000)  # Esperar a que aparezca la pantalla
                    await self.handle_intermediate_screens(page)
                    return True
                    
            print("SessionManager: ⚠️ Límite de intentos alcanzado para pantallas intermedias")
            return await self.session_manager._is_logged_in(page)
            
        except Exception as e:
            print(f"SessionManager: ❌ Error manejando pantallas intermedias: {e}")
            await self.take_screenshot(page, "intermediate_screens_error")
            return False