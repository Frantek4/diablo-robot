"""Leer la home de Instagram con la sesión de un navegador, sin intermediarios.

Los pedidos son los mismos que hace la web de instagram.com estando logueado. Las cookies salen de
la sesión que guarda `instaloader --load-cookies firefox`, pero instaloader ya no hace ningún pedido:
era una caja más entre el bot y lo que Instagram contesta, y su manejo de errores (dormir, reintentar,
buscar perfiles parecidos) era justo lo que había que esquivar.
"""

import json
import pickle
from datetime import datetime
from os.path import expanduser

import aiohttp

from config.settings import settings
from integrations.social_errors import AccountFlagged, ClientOutdated, TargetMissing, Throttled, Unreachable, dig

_BASE = "https://www.instagram.com"
# El id público de la app web de Instagram. No es un secreto: viaja en cada pedido del navegador
_APP_ID = "936619743392459"
# Lo que Instagram contesta cuando acusó a la cuenta. Ninguno se arregla esperando; el último es
# además la sesión vencida, que con `reanudar` solo no alcanza: hay que rehacerla
_FLAGGED = ("checkpoint_required", "challenge_required", "feedback_required")
_SESSION_DEAD = "login_required"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


def session_path() -> str:
    """Donde la deja `instaloader --load-cookies firefox --sessionfile ...` (ver CLAUDE.md)."""
    return expanduser(f"~/.config/instaloader/session-{settings.IG_USERNAME}")


class InstagramClient:
    """Una sesión de cookies contra la API web de Instagram."""

    def __init__(self, cookies: dict, user_agent: str):
        self._cookies = cookies
        self._user_agent = user_agent

    @classmethod
    def from_session_file(cls) -> "InstagramClient":
        try:
            with open(session_path(), "rb") as f:
                # Un dict de cookies en pickle: el formato de instaloader. El archivo es nuestro
                cookies = pickle.load(f)
        except FileNotFoundError:
            # Sin sesión no sale ningún pedido, pero tampoco tiene sentido despertarse cada vuelta a
            # descubrir lo mismo: es un freno como cualquier otro, hasta que alguien la genere
            raise AccountFlagged(f"no hay sesión guardada en {session_path()}", session_dead=True)
        return cls(cookies, settings.IG_USER_AGENT or settings.USER_AGENT)

    async def home(self, session: aiohttp.ClientSession) -> dict:
        """La home: un pedido. Devuelve la respuesta entera, sin parsear."""
        data = {"reason": "cold_start_fetch", "num_prefetch_live_ms": "0"}
        return await self._request(session, "POST", "/api/v1/feed/timeline/", data=data)

    async def user_id(self, session: aiohttp.ClientSession, username: str) -> str:
        """El id numérico de una cuenta, que es lo que pide el follow. Es la misma ficha que pide la
        web al abrir un perfil."""
        data = await self._request(session, "GET", "/api/v1/users/web_profile_info/",
                                   params={"username": username}, target=username)
        user_id = dig(data, "data", "user", "id")
        if not user_id:
            raise TargetMissing(f"Instagram no encuentra a @{username}")
        return user_id

    async def follow(self, session: aiohttp.ClientSession, user_id: str):
        """Seguir una cuenta, con el mismo pedido que hace el botón de la web."""
        form = {"container_module": "profile", "nav_chain": "", "user_id": user_id}
        await self._request(session, "POST", f"/api/v1/friendships/create/{user_id}/", data=form)

    async def _request(self, session: aiohttp.ClientSession, method: str, path: str,
                       target: str | None = None, **kwargs) -> dict:
        headers = {
            "accept": "*/*",
            "accept-language": "es-AR,es;q=0.9,en;q=0.8",
            "cookie": "; ".join(f"{k}={v}" for k, v in self._cookies.items()),
            "origin": _BASE,
            "referer": f"{_BASE}/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self._user_agent,
            "x-csrftoken": self._cookies.get("csrftoken", ""),
            "x-ig-app-id": _APP_ID,
            "x-requested-with": "XMLHttpRequest",
        }
        try:
            async with session.request(method, f"{_BASE}{path}", headers=headers, timeout=_TIMEOUT,
                                       **kwargs) as response:
                body = await response.text()
                return _check(response.status, str(response.url), body, target)
        except (aiohttp.ClientError, TimeoutError) as e:
            raise Unreachable(f"{type(e).__name__}: {e}"[:300]) from e


def _check(status: int, final_url: str, body: str, target: str | None = None) -> dict:
    """Lee la respuesta cruda y decide qué pasó. `target` es la cuenta ajena por la que se
    preguntó, si la hay: un 404 ahí es esa cuenta que no existe, no un endpoint que cambió."""
    if "/accounts/login" in final_url:
        raise AccountFlagged(f"Instagram me mandó a {final_url.split('?')[0]}: la sesión no sirve más",
                             session_dead=True)
    if "/challenge" in final_url:
        raise AccountFlagged(f"Instagram me mandó a {final_url.split('?')[0]}: hay un challenge")

    if body.lstrip()[:1] == "<":
        # La API contesta JSON siempre; una página es el login o un challenge disfrazado de 200
        raise AccountFlagged(f"HTTP {status} con una página HTML en vez de JSON: la sesión no sirve más",
                             session_dead=True)

    try:
        data = json.loads(body) if body else {}
    except ValueError:
        data = {}

    message = str(data.get("message") or "")
    if message == _SESSION_DEAD or data.get("require_login") or status == 401:
        raise AccountFlagged(f"{message or 'login_required'} (HTTP {status})", session_dead=True)
    if message in _FLAGGED or data.get("checkpoint_url"):
        raise AccountFlagged(f"{message or 'checkpoint'} (HTTP {status})")
    if status == 403:
        raise AccountFlagged(f"HTTP 403: {message or body[:200]}")

    if status == 429 or data.get("spam") or "wait a few minutes" in message.lower():
        raise Throttled(f"Instagram me pidió que espere (HTTP {status}{': ' + message if message else ''})")

    if status == 404 and target:
        raise TargetMissing(f"Instagram no encuentra a @{target}")
    if status in (400, 404):
        # El mismo pedido va a rebotar igual mañana: esto se arregla en el código
        raise ClientOutdated(f"Instagram no acepta el pedido (HTTP {status}{': ' + message if message else ''}): "
                             f"el endpoint cambió. Correr `tools/probe_feeds.py --only instagram`")

    if status >= 400 or data.get("status") == "fail":
        raise Throttled(f"HTTP {status}: {message or body[:200]}")
    return data


def feed_media(response: dict) -> list[dict]:
    """Los posts de la home, sin publicidades. Si había items y no pude leer ninguno, Instagram
    cambió el formato: eso tiene que verse, no pasar por "no hay nada nuevo"."""
    if "feed_items" not in response:
        raise ClientOutdated("la home no trajo `feed_items`: Instagram cambió el formato de la respuesta")

    items = [item.get("media_or_ad") for item in response["feed_items"] if item.get("media_or_ad")]
    media = [m for m in items if not (m.get("ad_id") or m.get("injected") or m.get("is_ad"))]
    readable = [m for m in media if m.get("code") and dig(m, "user", "username")]
    if media and not readable:
        raise ClientOutdated("Instagram devolvió posts en un formato que no sé leer: hay que actualizar el parser")
    return readable


def media_to_post(media: dict) -> dict:
    caption = dig(media, "caption", "text") or ""
    image = (dig(media, "image_versions2", "candidates") or [{}])[0].get("url")
    if not image and media.get("carousel_media"):
        image = (dig(media["carousel_media"][0], "image_versions2", "candidates") or [{}])[0].get("url")
    return {
        "url": f"{_BASE}/p/{media['code']}/",
        "date": datetime.fromtimestamp(int(media.get("taken_at") or 0), settings.TIMEZONE),
        "caption": caption[:400] + "..." if len(caption) > 400 else caption,
        "image_url": image,
    }
