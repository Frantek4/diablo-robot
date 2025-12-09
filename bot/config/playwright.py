import os
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).parent.parent.parent
PLAYWRIGHT_DATA_DIR = PROJECT_ROOT / "config" / "playwright_data"

class PlaywrightConfig:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.user_data_dir = str(PLAYWRIGHT_DATA_DIR)
    
    async def initialize(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=False,
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        self.context = self.browser
    
    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def get_context(self):
        return self.context
    
    async def save_persistent_session(self):
        """Guarda la sesión persistente del navegador"""
        try:
            if not self.context or not self.context.pages:
                print("PlaywrightConfig: ❌ No hay contexto o páginas para guardar sesión")
                return False
            
            # Obtener cookies de todas las páginas
            all_cookies = []
            for page in self.context.pages:
                cookies = await page.context.cookies()
                all_cookies.extend(cookies)
            
            if not all_cookies:
                print("PlaywrightConfig: ⚠️ No se encontraron cookies para guardar")
                return False
            
            # Guardar en archivo
            session_data = {
                'timestamp': datetime.now().isoformat(),
                'cookies': all_cookies,
                'user_agent': await self.context.pages[0].evaluate('navigator.userAgent')
            }
            
            session_file = Path(self.user_data_dir) / "persistent_session.json"
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            print(f"PlaywrightConfig: ✅ Sesión persistente guardada en {session_file}")
            return True
            
        except Exception as e:
            print(f"PlaywrightConfig: ❌ Error guardando sesión persistente: {e}")
            import traceback
            print(f"Detalles del error: {traceback.format_exc()}")
            return False