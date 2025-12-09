import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from playwright.async_api import Page

class SessionManager:
    """Gestiona sesiones persistentes y renovación de cookies"""
    
    def __init__(self, base_dir: str = "assets/sessions"):
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.screenshots_dir = self.base_dir / "screenshots"
        self.cookies_file = self.sessions_dir / "cookies.json"
        
        # Crear directorios si no existen
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    async def renew_session(self, page: Page, username: str, password: str) -> Optional[str]:
        """Renueva la sesión, manejando login en URL principal"""
        print("SessionManager: Renovando sesión...")
        
        try:
            # Tomar screenshot antes de login
            await self.take_screenshot(page, "before_login")
            
            # Navegar a la URL principal
            await page.goto("https://www.instagram.com/", timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(3, 6))
            
            # Detectar si estamos en pantalla de login
            if not await self._is_logged_in(page):
                print("SessionManager: Detectada pantalla de login en URL principal")
                # Intentar login
                login_success = await self._attempt_login_on_main_page(page, username, password)
                if login_success:
                    print("SessionManager: Manejando pantallas intermedias después del login...")
                    await self.handle_intermediate_screens(page) 
                else:
                    print("SessionManager: ❌ Falló el login en URL principal")
                    await self.take_screenshot(page, "login_failed_main_url")
                    return None
            
            # Manejar pantallas intermedias
            print("SessionManager: Manejando pantallas intermedias después del login...")
            await self.handle_intermediate_screens(page)
            
            # Verificar sesión
            await asyncio.sleep(random.uniform(3, 5))
            if not await self._is_logged_in(page):
                print("SessionManager: ❌ Login no verificado después de pantallas intermedias")
                await self.take_screenshot(page, "login_not_verified_after_intermediate")
                return None
            
            # Guardar sesión
            if await self.save_session(page):
                print("SessionManager: ✅ Sesión renovada y guardada")
                await self.take_screenshot(page, "login_successful")
                return "session_renewed"
            
            return None
            
        except Exception as e:
            print(f"SessionManager: ❌ Error al renovar sesión: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")
            await self.take_screenshot(page, "session_renewal_error")
            return None
    
    async def detect_login_type(self, page: Page) -> str:
        """Detecta qué tipo de pantalla de login se está mostrando"""
        try:
            # Detectar nueva interfaz de login
            new_login_indicators = [
                'input[name="username"]',
                'input[name="password"]',
                'input[name="pass"]',
                'button[type="submit"]:has-text("Iniciar sesión")',
                'button[type="submit"]:has-text("Log In")',
                'div[role="button"]:has-text("Iniciar sesión")'
            ]
            
            for selector in new_login_indicators:
                try:
                    if await page.locator(selector).count() > 0:
                        print(f"SessionManager: ✅ Detectada nueva interfaz de login con selector: {selector}")
                        return "new_login_interface"
                except:
                    continue
            
            # Detectar login principal
            main_login_selectors = [
                'button:has-text("Log in"), button:has-text("Iniciar sesión")',
                'a:has-text("Log in with Facebook"), a:has-text("Iniciar sesión con Facebook")',
                'div:has-text("Get the app"), div:has-text("Descargar la aplicación")',
                'input[name="username"], input[aria-label*="Phone"], input[aria-label*="Teléfono"]',
                'input[name="password"], input[aria-label*="Password"], input[aria-label*="Contraseña"]',
                # Selectores genéricos por clases
                'div.x1c1uobl:has(input[name="username"]), div.x1c1uobl:has(input[name="password"])',
                'div.x1ey2m1c:has(span:has-text("Log in")), div.x1ey2m1c:has(span:has-text("Iniciar sesión"))',
                'section.x78zum5:has(button:has-text("Log in"))'
            ]
            
            for selector in main_login_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        return "main_login"
                except:
                    continue
            
            return "unknown"
        except Exception as e:
            print(f"SessionManager: Error detectando tipo de login: {e}")
            return "unknown"
    
    async def _perform_new_login_interface(self, page: Page, username: str, password: str) -> bool:
        """Maneja la nueva interfaz de login de Instagram"""
        from utils.anti_detection import HumanEmulation
        
        try:
            print("SessionManager: Iniciando login en nueva interfaz...")
            
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
                        print(f"SessionManager: ✅ Campo de usuario encontrado con selector: {selector}")
                        break
                except:
                    continue
            
            if not username_field:
                print("SessionManager: ❌ No se encontró campo de usuario en nueva interfaz")
                await self.take_screenshot(page, "no_username_field_new_interface")
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
                        print(f"SessionManager: ✅ Campo de contraseña encontrado con selector: {selector}")
                        break
                except:
                    continue
            
            if not password_field:
                print("SessionManager: ❌ No se encontró campo de contraseña en nueva interfaz")
                await self.take_screenshot(page, "no_password_field_new_interface")
                return False
            
            # Escribir contraseña con comportamiento humano
            await HumanEmulation.human_typing(password_field, password)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # 3. Buscar y hacer clic en botón de login
            login_button_selectors = [
                'button[type="submit"]:has-text("Iniciar sesión")',
                'button[type="submit"]:has-text("Log In")',
                'div[role="button"]:has-text("Iniciar sesión")',
                'div[role="button"]:has-text("Log In")'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0 and await button.is_visible() and await button.is_enabled():
                        login_button = button
                        print(f"SessionManager: ✅ Botón de login encontrado con selector: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                print("SessionManager: ❌ No se encontró botón de login en nueva interfaz")
                await self.take_screenshot(page, "no_login_button_new_interface")
                return False
            
            # Click humano en botón de login
            await HumanEmulation.human_click(page, login_button)
            
            # Esperar a que se complete el login
            await asyncio.sleep(random.uniform(4, 8))
            
            print("SessionManager: ✅ Credenciales enviadas en nueva interfaz")
            await self.handle_intermediate_screens(page) 
            return True
            
        except Exception as e:
            print(f"SessionManager: ❌ Error en nueva interfaz de login: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")
            await self.take_screenshot(page, "new_interface_login_error")
            return False
    
    async def handle_intermediate_screens(self, page: Page) -> bool:
        """Maneja las pantallas intermedias después del login"""
        from utils.anti_detection import HumanEmulation
        
        try:
            print("SessionManager: Buscando pantallas intermedias...")
            
            # Esperar un poco después del login
            await asyncio.sleep(random.uniform(3, 6))
            
            # Intentar hasta 5 veces
            for attempt in range(5):
                await asyncio.sleep(random.uniform(2, 4))
                
                # Detectar pantalla de guardar información
                if await page.locator('button:has-text("Not Now"), button:has-text("Ahora no")').count() > 0:
                    print("SessionManager: Manjeando pantalla 'Save your login info'")
                    not_now_button = page.locator('button:has-text("Not Now"), button:has-text("Ahora no")').first
                    await HumanEmulation.human_click(page, not_now_button)
                    await asyncio.sleep(random.uniform(2, 4))
                    continue
                
                # Detectar pantalla de notificaciones
                if await page.locator('button:has-text("Not Now"), button:has-text("Ahora no"), button:has-text("Later"), button:has-text("Más tarde")').count() > 0:
                    print("SessionManager: Manjeando pantalla 'Turn on notifications'")
                    not_now_button = page.locator('button:has-text("Not Now"), button:has-text("Ahora no"), button:has-text("Later"), button:has-text("Más tarde")').first
                    await HumanEmulation.human_click(page, not_now_button)
                    await asyncio.sleep(random.uniform(2, 4))
                    continue
                
                # Verificar si ya estamos logueados
                if await self._is_logged_in(page):
                    print("SessionManager: ✅ Sesión válida después de pantallas intermedias")
                    await self.handle_intermediate_screens(page)
                    return True
            
            print("SessionManager: ⚠️ Límite de intentos alcanzado para pantallas intermedias")
            return await self._is_logged_in(page)
            
        except Exception as e:
            print(f"SessionManager: ❌ Error manejando pantallas intermedias: {e}")
            await self.take_screenshot(page, "intermediate_screens_error")
            return False
    
    async def _is_logged_in(self, page: Page) -> bool:
        """Verifica si el usuario está logueado (versión mejorada)"""
        try:
            # Verificar si hay elementos de login visibles
            login_elements = [
                'input[name="username"]',
                'input[name="password"]',
                'input[name="pass"]',
                'button[type="submit"]:has-text("Log In")',
                'button[type="submit"]:has-text("Iniciar sesión")',
                '#login_form'
            ]
            
            for selector in login_elements:
                try:
                    if await page.locator(selector).count() > 0 and await page.locator(selector).is_visible():
                        print(f"SessionManager: ❌ Elemento de login detectado: {selector}")
                        return False
                except:
                    continue
            
            # Verificar elementos de sesión válida
            valid_elements = [
                'nav[aria-label="Menú principal"]',
                'a[href="/direct/inbox/"]',
                'a[href="/explore/"]',
                '[aria-label="Búsqueda"], [aria-label="Search"]',
                'section[role="feed"], div[role="feed"]',
                'article'
            ]
            
            visible_count = 0
            for selector in valid_elements:
                try:
                    elements = await page.locator(selector).all()
                    for element in elements:
                        if await element.is_visible():
                            visible_count += 1
                            break
                except:
                    continue
            
            print(f"SessionManager: ✅ {visible_count} elementos de sesión válida encontrados")
            return visible_count >= 2
            
        except Exception as e:
            print(f"SessionManager: Error verificando login: {e}")
            return False
    
    async def save_session(self, page: Page) -> bool:
        """Guarda la sesión actual"""
        try:
            cookies = await page.context.cookies()
            session_data = {
                'timestamp': datetime.now().isoformat(),
                'cookies': cookies,
                'user_agent': await page.evaluate('navigator.userAgent'),
                'viewport': await page.evaluate('({ width: window.innerWidth, height: window.innerHeight })')
            }
            
            with open(self.cookies_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            print(f"SessionManager: ✅ Sesión guardada exitosamente en {self.cookies_file}")
            return True
        except Exception as e:
            print(f"SessionManager: ❌ Error al guardar sesión: {e}")
            return False
    
    async def take_screenshot(self, page: Page, name: str) -> str:
        """Toma un screenshot para debugging"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            path = self.screenshots_dir / filename
            
            await page.screenshot(path=str(path), full_page=True)
            print(f"SessionManager: Screenshot guardado: {path}")
            return str(path)
        except Exception as e:
            print(f"SessionManager: Error tomando screenshot: {e}")
            return ""
        
    async def _attempt_login_on_main_page(self, page: Page, username: str, password: str) -> bool:
        """Intenta hacer login cuando la pantalla de login aparece en la URL principal"""
        from utils.anti_detection import HumanEmulation
        
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