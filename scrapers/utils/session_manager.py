import asyncio
from datetime import datetime
from pathlib import Path
import random
import traceback

from playwright.async_api import Page

from config.settings import settings
from scrapers.utils.human_emulation import HumanEmulation
from scrapers.utils.recaptcha_solver import RecaptchaSolver


class SessionManager:
    """Gestor de sesiones mejorado con detección avanzada de pantallas intermedias"""
    
    def __init__(self, base_dir: str = "assets/sessions"):
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.screenshots_dir = self.base_dir / "screenshots"
        self.cookies_file = self.sessions_dir / "cookies.json"
        
        # Crear directorios si no existen
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuración para reCAPTCHA
        self.recaptcha_solver = RecaptchaSolver() if hasattr(settings, 'RECAPTCHA_API_KEY') else None

    async def detect_login_type(self, page: Page) -> str:
        """Detección mejorada para nueva interfaz de Instagram"""
        try:
            current_url = page.url.lower()
            print(f"SessionManager: 🔍 Analizando URL actual (nueva interfaz): {current_url}")
            
            # Verificar si ya estamos logueados en la nueva interfaz
            if await self._is_logged_in(page):
                print("SessionManager: ✅ Usuario ya autenticado en nueva interfaz")
                return "logged_in"
            
            # Detectar redirección a login
            if any(keyword in current_url for keyword in ["/login", "/accounts/login", "/challenge", "/checkpoint"]):
                print("SessionManager: 🔄 Detectada redirección a pantalla de login")
                return "login_redirect"
            
            # Nuevos selectores para la interfaz actualizada
            new_login_indicators = [
                'input[name="username"], input[name="email"], input[aria-label*="username"], input[aria-label*="usuario"]',
                'input[name="password"], input[type="password"], input[aria-label*="password"], input[aria-label*="contraseña"]',
                'button[type="submit"]:has-text("Log In"), button[type="submit"]:has-text("Iniciar sesión")',
                'div:has-text("Welcome to Instagram"), div:has-text("Bienvenido a Instagram")',
                'form#loginForm, form#login_form',
                # Clases específicas de la nueva interfaz basadas en el HTML proporcionado
                'div.x1ey2m1c:has(span:has-text("Log in")), div.x1ey2m1c:has(span:has-text("Iniciar sesión"))',
                'input[name="username"]:visible, input[name="email"]:visible',
                'button[type="submit"]:visible'
            ]
            
            for selector in new_login_indicators:
                try:
                    if await page.locator(selector).count() > 0:
                        elements = await page.locator(selector).all()
                        for element in elements:
                            if await element.is_visible(timeout=3000):
                                print(f"SessionManager: ✅ Detectada NUEVA interfaz de login con selector: {selector}")
                                return "new_login_interface_v2"
                except Exception as e:
                    continue
            
            # Detectar login en página principal (nueva interfaz)
            main_login_selectors = [
                'button:has-text("Log in"), button:has-text("Iniciar sesión")',
                'a:has-text("Log in with Facebook"), a:has-text("Iniciar sesión con Facebook")',
                'div:has-text("Get the app"), div:has-text("Descargar la aplicación")',
                'div.x1c1uobl:has(input[aria-label*="Phone"]), div.x1c1uobl:has(input[aria-label*="Teléfono"])'
            ]
            
            for selector in main_login_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        print(f"SessionManager: ✅ Detectada pantalla de login principal NUEVA con selector: {selector}")
                        return "main_login_v2"
                except Exception as e:
                    continue
            
            print("SessionManager: ❓ Tipo de pantalla no reconocido, asumiendo sesión válida (nueva interfaz)")
            return "logged_in"
            
        except Exception as e:
            print(f"SessionManager: ❌ Error detectando tipo de login en nueva interfaz: {str(e)}")
            print(f"Detalles: {traceback.format_exc()}")
            return "unknown"

    async def handle_intermediate_screens(self, page: Page) -> bool:
        """Manejo avanzado de pantallas intermedias incluyendo la nueva pantalla de consentimiento"""
        
        try:
            print("SessionManager: 🎯 Buscando nuevas pantallas intermedias...")
            max_attempts = 15  # Aumentado para mayor cobertura
            handled_any_screen = False
            
            for attempt in range(max_attempts):
                await asyncio.sleep(random.uniform(1.5, 3.5))
                
                # Nuevos selectores para la interfaz actualizada de Instagram
                intermediate_screens = {
                    'meta_verification': {
                        'selectors': [
                            'div:has-text("Meta Verified"), div:has-text("Verificado por Meta")',
                            'button:has-text("Skip"), button:has-text("Omitir"), button:has-text("Saltar")',
                            'a[href*="/accounts/meta_verified/"]'
                        ],
                        'action': 'click',
                        'priority': 1
                    },
                    'terms_consent': {
                        'selectors': [
                            'button:has-text("Continue"), button:has-text("Continuar"), button:has-text("Accept"), button:has-text("Aceptar")',
                            'div:has-text("By continuing, you agree to Instagram\'s Terms of Use")',
                            'div:has-text("terms of use"), div:has-text("términos de uso")',
                            'button:has-text("Agree"), button:has-text("Acepto")'
                        ],
                        'action': 'click',
                        'priority': 1
                    },
                    'cookies_consent': {
                        'selectors': [
                            'button:has-text("Allow"), button:has-text("Permitir"), button:has-text("Accept"), button:has-text("Aceptar")',
                            'div:has-text("cookies"), div:has-text("Cookies")',
                            'button:has-text("Only necessary"), button:has-text("Solo necesario")'
                        ],
                        'action': 'click',
                        'priority': 1
                    },
                    'new_user_setup': {
                        'selectors': [
                            'div:has-text("Create new account"), div:has-text("Crear cuenta nueva")',
                            'button:has-text("Next"), button:has-text("Siguiente"), button:has-text("Continue"), button:has-text("Continuar")',
                            'div[role="button"]:has-text("Skip"), div[role="button"]:has-text("Omitir")'
                        ],
                        'action': 'click',
                        'priority': 2
                    },
                    'app_promo': {
                        'selectors': [
                            'div:has-text("Get the app"), div:has-text("Descargar la aplicación")',
                            'button:has-text("Cancel"), button:has-text("Cancelar"), button:has-text("Close"), button:has-text("Cerrar")',
                            'div[role="dialog"]:has-text("Download the Instagram app")'
                        ],
                        'action': 'click',
                        'priority': 3
                    },
                    'profile_setup': {
                        'selectors': [
                            'div:has-text("profile picture"), div:has-text("foto de perfil")',
                            'button:has-text("Skip"), button:has-text("Omitir"), button:has-text("Later"), button:has-text("Más tarde")',
                            'div[role="button"]:has-text("Next"), div[role="button"]:has-text("Siguiente")'
                        ],
                        'action': 'click',
                        'priority': 1
                    }
                }
                
                # Ordenar pantallas por prioridad
                sorted_screens = sorted(intermediate_screens.items(), key=lambda x: x[1]['priority'], reverse=True)
                
                screen_handled = False
                for screen_type, config in sorted_screens:
                    for selector in config['selectors']:
                        try:
                            elements = page.locator(selector)
                            count = await elements.count()
                            
                            if count > 0:
                                # Verificar visibilidad de los elementos
                                visible_elements = []
                                for i in range(count):
                                    element = elements.nth(i)
                                    if await element.is_visible(timeout=2000):
                                        visible_elements.append(element)
                                
                                if visible_elements:
                                    print(f"SessionManager: 🎯 🎯 🔥 Detectada NUEVA pantalla intermedia: {screen_type} con selector: {selector}")
                                    await self.take_screenshot(page, f"new_intermediate_screen_{screen_type}_{attempt}")
                                    
                                    if config['action'] == 'click':
                                        button = visible_elements[0]
                                        if await button.is_enabled():
                                            await HumanEmulation.human_click(page, button)
                                            print(f"SessionManager: ✅ ✅ ✅ Acción realizada en NUEVA pantalla: {screen_type}")
                                            screen_handled = True
                                            handled_any_screen = True
                                            await asyncio.sleep(random.uniform(2.5, 5.0))
                                            break
                                
                        except Exception as e:
                            continue
                    
                    if screen_handled:
                        break
                
                # Verificar si ya estamos en el feed principal
                if await self._is_logged_in(page):
                    print("SessionManager: ✅ ✅ ✅ No hay más pantallas intermedias - sesión establecida (nueva interfaz)")
                    await page.wait_for_timeout(3000)
                    return True
                
                # Verificar si hay elementos del feed visibles
                feed_indicators = [
                    'div[role="feed"], section[role="feed"]',
                    'article, div[role="article"]',
                    'a[href="/explore/"], a[href="/direct/inbox/"]',
                    'nav[aria-label="Menú principal"], nav[aria-label="Main menu"]',
                    'div.x78zum5:has(div[role="feed"])',
                    'div.x1ey2m1c:has(span:has-text("Home")), div.x1ey2m1c:has(span:has-text("Inicio"))'
                ]
                
                for selector in feed_indicators:
                    try:
                        if await page.locator(selector).count() > 0:
                            visible_count = 0
                            elements = await page.locator(selector).all()
                            for element in elements:
                                if await element.is_visible(timeout=2000):
                                    visible_count += 1
                            
                            if visible_count > 0:
                                print(f"SessionManager: ✅ ✅ ✅ Detectado feed principal con selector: {selector} ({visible_count} elementos visibles)")
                                await asyncio.sleep(3000)
                                return True
                    except Exception as e:
                        continue
                
                # Verificar si estamos en una pantalla de error o bloqueo
                error_indicators = [
                    'div:has-text("suspicious"), div:has-text("sospechoso")',
                    'div:has-text("verify"), div:has-text("verificar")',
                    'div:has-text("challenge"), div:has-text("desafío")',
                    'div:has-text("blocked"), div:has-text("bloqueado")'
                ]
                
                for selector in error_indicators:
                    try:
                        if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible(timeout=2000):
                            print(f"SessionManager: ⚠️ ⚠️ ⚠️ Detectada pantalla de ERROR/SEGURIDAD: {selector}")
                            await self.take_screenshot(page, f"security_challenge_{attempt}")
                            return False
                    except Exception as e:
                        continue
                
                if not screen_handled and attempt > 3:
                    print(f"SessionManager: ℹ️ No se detectaron nuevas pantallas intermedias en el intento {attempt}")
                    if handled_any_screen:
                        # Verificar una última vez si estamos logueados
                        if await self._is_logged_in(page):
                            print("SessionManager: ✅ Sesión válida después de manejar pantallas intermedias")
                            return True
                        return True
                    break
            
            print("SessionManager: ⚠️ ⚠️ Finalizado manejo de NUEVAS pantallas intermedias")
            # Verificación final de sesión
            if await self._is_logged_in(page):
                print("SessionManager: ✅ Sesión válida después de todos los intentos")
                return True
            
            print("SessionManager: ❌ No se pudo establecer sesión válida")
            await self.take_screenshot(page, "final_session_check_failed")
            return False
            
        except Exception as e:
            print(f"SessionManager: ❌ ❌ ❌ Error manejando NUEVAS pantallas intermedias: {str(e)}")
            print(f"Detalles completos: {traceback.format_exc()}")
            await self.take_screenshot(page, "new_intermediate_screens_error")
            return False

    async def _is_logged_in(self, page: Page) -> bool:
        """Verificación mejorada para nueva interfaz de Instagram"""
        try:
            # Verificar URL - la nueva interfaz puede tener diferentes rutas
            current_url = page.url.lower()
            if any(keyword in current_url for keyword in ["/login", "/accounts/login", "/challenge", "/checkpoint", "/onetap"]):
                print(f"SessionManager: ❌ URL de login detectada: {current_url}")
                return False
            
            # Nuevos selectores para la interfaz actualizada basados en el HTML proporcionado
            session_indicators = [
                # Selectores específicos de la nueva interfaz
                'nav[aria-label="Menú principal"], nav[aria-label="Main menu"]',
                'a[href="/direct/inbox/"], a[href="/explore/"]',
                'div[role="feed"], section[role="feed"]',
                'div.x78zum5:has(div[role="feed"])',
                'div.x9f619:has(nav[aria-label="Menú principal"])',
                'div.x1c4vz4f:has(div[role="button"]:has-text("Create")), div.x1c4vz4f:has(div[role="button"]:has-text("Crear"))',
                # Clases específicas observadas en el HTML
                'div.x1q0g3np:has(svg[aria-label="Instagram"])',
                'div.x1ey2m1c:has(span:has-text("Home")), div.x1ey2m1c:has(span:has-text("Inicio"))',
                'div.x1c1uobl:has(input[aria-label*="Search"]), div.x1c1uobl:has(input[aria-label*="Búsqueda"])',
                'button[aria-label*="search"], button[aria-label*="búsqueda"]',
                # Elementos de publicación
                'article, div[role="article"]',
                'div.x1ey2m1c:has(span:has-text("Like")), div.x1ey2m1c:has(span:has-text("Me gusta"))'
            ]
            
            visible_count = 0
            for selector in session_indicators:
                try:
                    elements = await page.locator(selector).all()
                    for element in elements:
                        if await element.is_visible(timeout=3000):
                            visible_count += 1
                            print(f"SessionManager: ✅ Elemento de sesión encontrado: {selector}")
                            break
                except Exception as e:
                    continue
            
            print(f"SessionManager: 📊 {visible_count} elementos de sesión válida encontrados (nueva interfaz)")
            return visible_count >= 2
            
        except Exception as e:
            print(f"SessionManager: ❌ Error verificando login en nueva interfaz: {str(e)}")
            print(f"Detalles: {traceback.format_exc()}")
            return False

    async def _perform_new_login_interface(self, page: Page, username: str, password: str) -> bool:
        """Login optimizado para nueva interfaz con manejo de errores avanzado y pantallas de consentimiento"""
        
        try:
            print("SessionManager: 🔐 Iniciando login en nueva interfaz...")
            
            # 1. Manejar cualquier pantalla intermedia antes del login
            await self.handle_intermediate_screens(page)
            
            # 2. Buscar y llenar campo de usuario
            username_selectors = [
                'input[name="username"], input[name="email"], input[aria-label*="username"], input[aria-label*="usuario"]',
                'input[aria-label="Phone number, username, or email"]',
                'input[aria-label="Teléfono, correo electrónico o nombre de usuario"]'
            ]
            
            username_field = None
            for selector in username_selectors:
                try:
                    field = page.locator(selector).first
                    if await field.count() > 0 and await field.is_visible(timeout=8000):
                        username_field = field
                        print(f"SessionManager: ✅ ✅ Campo de usuario encontrado: {selector}")
                        break
                except Exception as e:
                    continue
            
            if not username_field:
                print("SessionManager: ❌ ❌ No se encontró campo de usuario")
                await self.take_screenshot(page, "no_username_field_new_interface")
                return False
            
            # Escribir usuario con comportamiento humano avanzado
            await HumanEmulation.human_typing(username_field, username)
            await asyncio.sleep(random.uniform(1.5, 2.8))
            
            # 3. Buscar y llenar campo de contraseña
            password_selectors = [
                'input[name="password"], input[type="password"], input[aria-label*="password"], input[aria-label*="contraseña"]',
                'input[aria-label="Password"]',
                'input[aria-label="Contraseña"]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    field = page.locator(selector).first
                    if await field.count() > 0 and await field.is_visible(timeout=8000):
                        password_field = field
                        print(f"SessionManager: ✅ ✅ Campo de contraseña encontrado: {selector}")
                        break
                except Exception as e:
                    continue
            
            if not password_field:
                print("SessionManager: ❌ ❌ No se encontró campo de contraseña")
                await self.take_screenshot(page, "no_password_field_new_interface")
                return False
            
            # Escribir contraseña con comportamiento humano avanzado
            await HumanEmulation.human_typing(password_field, password)
            await asyncio.sleep(random.uniform(1.8, 3.2))
            
            # 4. Buscar y hacer clic en botón de login
            login_button_selectors = [
                'button[type="submit"]:has-text("Log In"), button[type="submit"]:has-text("Iniciar sesión")',
                'div[role="button"]:has-text("Log In"), div[role="button"]:has-text("Iniciar sesión")',
                'button:has-text("Log In"), button:has-text("Iniciar sesión")',
                'button[type="submit"]'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0 and await button.is_visible(timeout=8000) and await button.is_enabled():
                        login_button = button
                        print(f"SessionManager: ✅ ✅ Botón de login encontrado: {selector}")
                        break
                except Exception as e:
                    continue
            
            if not login_button:
                # Intentar con selectores más específicos de la nueva interfaz
                specific_selectors = [
                    'div.x1c1uobl:has(button[type="submit"])',
                    'div.x1ey2m1c:has(span:has-text("Log in")), div.x1ey2m1c:has(span:has-text("Iniciar sesión"))',
                    'button:has(div:has-text("Log in")), button:has(div:has-text("Iniciar sesión"))'
                ]
                
                for selector in specific_selectors:
                    try:
                        button = page.locator(selector).first
                        if await button.count() > 0 and await button.is_visible(timeout=8000) and await button.is_enabled():
                            login_button = button
                            print(f"SessionManager: ✅ ✅ Botón de login encontrado (selector específico): {selector}")
                            break
                    except Exception as e:
                        continue
                
                if not login_button:
                    print("SessionManager: ❌ ❌ No se encontró botón de login")
                    await self.take_screenshot(page, "no_login_button_new_interface")
                    return False
            
            # Click humano en botón de login
            await HumanEmulation.human_click(page, login_button)
            
            # Esperar con progreso visual
            print("SessionManager: ⏳ ⏳ Esperando respuesta del servidor...")
            for i in range(10):
                await asyncio.sleep(1)
                if i % 2 == 0:
                    print(f"SessionManager: ⏳ {i+1}/10 segundos...")
            
            # 5. Manejar posibles errores de login
            error_selectors = [
                'p:has-text("password"), p:has-text("contraseña")',
                'p:has-text("username"), p:has-text("usuario")',
                'p:has-text("invalid"), p:has-text("incorrect"), p:has-text("wrong")',
                'div:has-text("error"), div:has-text("Error")',
                'div:has-text("suspicious login attempt"), div:has-text("intento de inicio de sesión sospechoso")'
            ]
            
            for selector in error_selectors:
                try:
                    if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible(timeout=5000):
                        error_text = await page.locator(selector).text_content()
                        print(f"SessionManager: ❌ ❌ ❌ Error de login detectado: {error_text}")
                        await self.take_screenshot(page, "login_error_detailed")
                        return False
                except Exception as e:
                    continue
            
            # 6. Manejar pantallas intermedias después del login
            print("SessionManager: 🔄 🔄 Manejando pantallas intermedias después del login...")
            login_success = await self.handle_intermediate_screens(page)
            
            if not login_success:
                print("SessionManager: ⚠️ Manejo de pantallas intermedias no completo, verificando sesión...")
            
            # 7. Verificar si el login fue exitoso
            if await self._is_logged_in(page):
                print("SessionManager: ✅ ✅ ✅ ✅ ✅ Login exitoso en nueva interfaz")
                await self.take_screenshot(page, "login_successful_new_interface")
                return True
            
            print("SessionManager: ❌ ❌ Login fallido en nueva interfaz")
            await self.take_screenshot(page, "login_failed_final_new_interface")
            return False
            
        except Exception as e:
            print(f"SessionManager: ❌ ❌ ❌ ❌ ❌ Error en login en nueva interfaz: {str(e)}")
            print(f"Detalles completos: {traceback.format_exc()}")
            await self.take_screenshot(page, "login_error_detailed_new_interface")
            return False
    
    async def take_screenshot(self, page: Page, name: str, page_name: str = "instagram") -> str:
        """Toma un screenshot para debugging"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            path = self.screenshots_dir  / page_name / filename
            
            await page.screenshot(path=str(path), full_page=True)
            print(f"SessionManager: Screenshot guardado: {path}")
            return str(path)
        except Exception as e:
            print(f"SessionManager: Error tomando screenshot: {e}")
            return ""
        
    async def _attempt_login_on_main_page(self, page: Page, username: str, password: str) -> bool:
        
        try:
            print("SessionManager: Intentando login en URL principal...")
            
            # 1. Buscar y llenar campo de usuario
            username_selectors = [
                'input[name="username"]',
                'input[aria-label="Phone number, username, or email"]',
                'input[aria-label="Teléfono, correo electrónico o nombre de usuario"]'
            ]
            
            username_field = None
            for selector in username_selectors:
                try:
                    field = page.locator(selector).first
                    if await field.count() > 0 and await field.is_visible():
                        username_field = field
                        print(f"SessionManager: ✅ Campo de usuario encontrado: {selector}")
                        break
                except:
                    continue
            
            if not username_field:
                print("SessionManager: ❌ No se encontró campo de usuario")
                return False
            
            # Escribir usuario con comportamiento humano
            await HumanEmulation.human_typing(username_field, username)
            await asyncio.sleep(random.uniform(0.8, 1.5))
            
            # 2. Buscar y llenar campo de contraseña
            password_selectors = [
                'input[name="password"]',
                'input[name="pass"]',
                'input[aria-label="Password"]',
                'input[aria-label="Contraseña"]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    field = page.locator(selector).first
                    if await field.count() > 0 and await field.is_visible():
                        password_field = field
                        print(f"SessionManager: ✅ Campo de contraseña encontrado: {selector}")
                        break
                except:
                    continue
            
            if not password_field:
                print("SessionManager: ❌ No se encontró campo de contraseña")
                return False
            
            # Escribir contraseña con comportamiento humano
            await HumanEmulation.human_typing(password_field, password)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # 3. Buscar y hacer clic en botón de login
            login_button_selectors = [
                'button[type="submit"]:has-text("Log In")',
                'button[type="submit"]:has-text("Iniciar sesión")',
                'div[role="button"]:has-text("Log In")',
                'div[role="button"]:has-text("Iniciar sesión")'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0 and await button.is_visible() and await button.is_enabled():
                        login_button = button
                        print(f"SessionManager: ✅ Botón de login encontrado: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                print("SessionManager: ❌ No se encontró botón de login")
                return False
            
            # Click humano en botón de login
            await HumanEmulation.human_click(page, login_button)
            
            # Esperar a que se complete el login
            await asyncio.sleep(random.uniform(4, 8))
            
            # Verificar si el login fue exitoso
            if await self._is_logged_in(page):
                print("SessionManager: ✅ Login exitoso en URL principal")
                await self.handle_intermediate_screens(page) 
                return True
            
            print("SessionManager: ❌ Login fallido en URL principal")
            return False
            
        except Exception as e:
            print(f"SessionManager: ❌ Error en login en URL principal: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")
            await self.take_screenshot(page, "login_error_main_url")
            return False