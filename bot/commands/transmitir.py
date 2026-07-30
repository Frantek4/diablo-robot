import asyncio
import json
import logging
import os
import shutil
import subprocess

import aiohttp
from discord.ext import commands

logger = logging.getLogger(__name__)

_APAGAR = "APAGAR"
_CDP_PORT = 9222
_CHROMIUM = shutil.which("chromium") or shutil.which("chromium-browser") or "chromium-browser"

# Espera hasta 20s a que aparezca un <video> en la página
_WAIT_VIDEO_JS = """
new Promise(resolve => {
    const check = () => document.querySelector('video') ? resolve(true) : setTimeout(check, 500);
    check();
    setTimeout(() => resolve(false), 20000);
})
"""

# Devuelve el centro del primer <video> en coordenadas de viewport
_VIDEO_CENTER_JS = """
(() => {
    const v = document.querySelector('video');
    if (!v) return null;
    const r = v.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
})()
"""


class TransmitirCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._proc: subprocess.Popen | None = None

    def cog_unload(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None

    async def _stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(self._proc.wait), timeout=5.0)
            except asyncio.TimeoutError:
                self._proc.kill()
        self._proc = None

    async def _cdp_msg(self, ws, method: str, params: dict, msg_id: int, timeout: float = 5.0) -> dict:
        await ws.send_str(json.dumps({"id": msg_id, "method": method, "params": params}))
        try:
            async with asyncio.timeout(timeout):
                async for raw in ws:
                    if raw.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(raw.data)
                        if data.get("id") == msg_id:
                            return data
        except asyncio.TimeoutError:
            pass
        return {}

    async def _fullscreen_player(self, ws):
        # Espera a que cargue el video
        await self._cdp_msg(ws, "Runtime.evaluate", {
            "expression": _WAIT_VIDEO_JS,
            "awaitPromise": True,
            "timeout": 22000,
        }, msg_id=1, timeout=25.0)

        # Obtiene coordenadas del centro del video
        result = await self._cdp_msg(ws, "Runtime.evaluate", {
            "expression": _VIDEO_CENTER_JS,
            "returnByValue": True,
        }, msg_id=2)

        center = result.get("result", {}).get("result", {}).get("value")
        if center and isinstance(center, dict):
            x, y = float(center["x"]), float(center["y"])
            # Click para dar foco al player (necesario para que funcione la tecla)
            for i, ev in enumerate(["mousePressed", "mouseReleased"]):
                await self._cdp_msg(ws, "Input.dispatchMouseEvent", {
                    "type": ev, "x": x, "y": y, "button": "left", "clickCount": 1,
                }, msg_id=10 + i)
            await asyncio.sleep(0.3)

        # Tecla 'f': fullscreen nativo en YouTube, Twitch y la mayoría de players
        for i, (ev_type, text) in enumerate([("rawKeyDown", ""), ("keyPress", "f"), ("keyUp", "")]):
            await self._cdp_msg(ws, "Input.dispatchKeyEvent", {
                "type": ev_type, "windowsVirtualKeyCode": 70,
                "key": "f", "text": text, "code": "KeyF",
            }, msg_id=20 + i)

    async def _start(self, url: str):
        env = {**os.environ}
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"

        self._proc = subprocess.Popen(
            [
                _CHROMIUM,
                f"--remote-debugging-port={_CDP_PORT}",
                "--start-fullscreen",
                "--no-sandbox",
                "--disable-infobars",
                "--noerrdialogs",
                url,
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        async with aiohttp.ClientSession() as session:
            ws_url = None
            for _ in range(20):
                await asyncio.sleep(1)
                try:
                    async with session.get(
                        f"http://localhost:{_CDP_PORT}/json",
                        timeout=aiohttp.ClientTimeout(total=2),
                    ) as resp:
                        tabs = await resp.json(content_type=None)
                        page = next((t for t in tabs if t.get("type") == "page"), None)
                        if page:
                            ws_url = page["webSocketDebuggerUrl"]
                            break
                except Exception:
                    pass

            if not ws_url:
                logger.warning("No pude conectarme al CDP; el browser está abierto pero sin fullscreen del player.")
                return

            async with session.ws_connect(ws_url) as ws:
                await self._fullscreen_player(ws)

    @commands.command(name="transmitir", extras={"admin": True})
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def transmitir(self, ctx, *, arg: str = None):
        """Transmite una URL de video por el navegador. Usá 'APAGAR' para cortar la transmisión."""
        if not arg or arg.strip().upper() == _APAGAR:
            await self._stop()
            await self.bot.messager.log("Transmisión apagada.")
            return

        url = arg.strip()
        await self._stop()
        try:
            await self._start(url)
            await self.bot.messager.log(f"Transmitiendo: {url}")
        except Exception as e:
            await self.bot.messager.log(f"No pude iniciar la transmisión de '{url}': {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(TransmitirCommand(bot))
