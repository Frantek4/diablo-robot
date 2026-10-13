"""Leer la home "Siguiendo" de X con una sesión de cookies, sin intermediarios.

Lo que hace de pedido HTTP está adaptado de Nitter (github.com/zedeus/nitter, AGPL-3.0):
`consts.nim` (bearer, blob de features), `apiutils.nim` (headers de una sesión de cookies) y
`tid.nim` (la firma `x-client-transaction-id`). Nitter nunca leyó una home, así que el queryId de
`HomeLatestTimeline` no sale de ahí: se busca en el JavaScript que sirve x.com (ver
`discover_home_query`). Y lo que no se trajo a propósito es su manejo de errores: Nitter convierte
casi cualquier falla en el mismo `rateLimitError()` y reintenta. Acá cada respuesta se mira cruda
—status, `errors[].code`, headers— y se tira una excepción que dice qué pasó.
"""

import base64
import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import aiohttp

from config.settings import settings
from integrations.social_errors import AccountFlagged, ClientOutdated, TargetMissing, Throttled, Unreachable, dig
from utils.date_format import format_time

BEARER = ("Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
          "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
GRAPHQL = "https://x.com/i/api/graphql"
HOME_OPERATION = "HomeLatestTimeline"
# Para seguir una cuenta hace falta su id; éste sí está en Nitter (`graphUser` en `consts.nim`)
USER_BY_SCREEN_NAME = "Gb-d6r0vxPOADdG62OEBpQ/UserByScreenName"
_USER_TOGGLES = {"withArticleRichContentState": True, "withArticlePlainText": False,
                 "withGrokAnalyze": False, "withDisallowedReplyControls": False}
# Lo que manda el botón "Seguir" de la web junto con el id
_FOLLOW_FLAGS = ("include_profile_interstitial_type", "include_blocking", "include_blocked_by",
                 "include_followed_by", "include_want_retweets", "include_mute_edge", "include_can_dm",
                 "include_can_media_tag", "include_ext_is_blue_verified", "include_ext_verified_type",
                 "include_ext_profile_image_shape", "skip_status")
# Cuántos tweets pido por vuelta. Entre vuelta y vuelta pasan hasta dos horas y media, así que la
# página tiene que alcanzar para no dejar huecos con las cuentas que seguimos
HOME_COUNT = 40

# Los valores que Nitter sabe que X acepta. El blob que se manda de verdad sale de las
# `featureSwitches` que declara el bundle para la operación (ver `_build_features`); esto sólo
# decide el valor de las que conoce
FEATURES = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": False,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "c9s_list_members_action_api_enabled": False,
    "c9s_superc9s_indication_enabled": False,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": False,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": False,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

# Las que van en false aunque Nitter no las nombre. X sólo falla cuando una feature **falta**
# ("cannot be null"), no por el valor, así que el resto se manda en true
_FALSE_FEATURES = {
    "rweb_video_screen_enabled",
    "verified_phone_label_enabled",
    "premium_content_api_read_enabled",
    "responsive_web_grok_analyze_button_fetch_trends_enabled",
    "responsive_web_jetfuel_frame",
    "responsive_web_grok_show_grok_translated_post",
    "tweet_awards_web_tipping_enabled",
    "creator_subscriptions_quote_tweet_preview_enabled",
    "responsive_web_enhance_cards_enabled",
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled",
}

# Los códigos de `errors[]` que importan. Los de sesión y cuenta frenan todo hasta que un humano
# rehaga las cookies o destrabe la cuenta
_SESSION_DEAD = {32: "no autentica", 89: "token vencido", 239: "token inválido", 353: "ct0 no coincide"}
_ACCOUNT_FLAGGED = {37: "cuenta suspendida", 64: "cuenta suspendida", 326: "cuenta bloqueada"}
_RATE_LIMITED = 88
# Los del follow: llegar al límite de follows se pasa solo; los otros son de la cuenta a seguir
_FOLLOW_LIMIT = 161
_ALREADY_REQUESTED = 160
_TARGET_MISSING = {50: "no existe", 63: "está suspendida", 108: "no existe", 162: "no deja que la sigamos"}

# La firma `x-client-transaction-id` sale de un par (verificación, clave de animación) de los que
# arma el web de X. Nitter no los calcula: usa este diccionario público, que se renueva solo, y no
# toca x.com para conseguirlos. Se refresca cada hora
_TID_PAIRS_URL = ("https://raw.githubusercontent.com/fa0311/x-client-transaction-id-pair-dict"
                  "/refs/heads/main/pair.json")
_TID_TTL_SECONDS = 3600
_TID_EPOCH = 1682924400
_TID_KEYWORD = "obfiowerehiring"

# El bundle de x.com se mudó de `responsive-web/client-web/` a `x-web/x-web/`: se aceptan los dos
_BUNDLE = re.compile(r'https://abs\.twimg\.com/(?:x-web|responsive-web)/[^"\'\s<>]+?\.js')
_RELATIVE_BUNDLE = re.compile(r'["\'](\.{0,2}/[\w\-./]+?\.js)["\']')
_MAX_BUNDLES = 120

_TIMEOUT = aiohttp.ClientTimeout(total=30)


@dataclass(frozen=True)
class RateWindow:
    """Lo que X dijo que le queda al endpoint de la home, en la ventana en curso."""
    remaining: int
    limit: int
    reset: datetime

    @property
    def stale(self) -> bool:
        """La ventana ya venció: X repuso el presupuesto y `remaining` no frena nada."""
        return self.reset <= datetime.now(settings.TIMEZONE)

    def __str__(self) -> str:
        window = "ventana vencida" if self.stale else f"se repone {format_time(self.reset)}"
        return f"{self.remaining}/{self.limit} ({window})"


@dataclass(frozen=True)
class HomeQuery:
    """Lo que hace falta para pedir la home y que X rota cada tanto: el queryId y el blob de
    features. Se guarda en Mongo y se vuelve a buscar sólo cuando X lo rechaza."""
    query_id: str
    features: dict


class XClient:
    """Una sesión de cookies contra la API GraphQL de X."""

    def __init__(self, auth_token: str, ct0: str, user_agent: str):
        self._auth_token = auth_token
        self._ct0 = ct0
        self._user_agent = user_agent
        self._pairs: list[dict] = []
        self._pairs_at = 0.0
        self.window: RateWindow | None = None

    async def home_latest(self, session: aiohttp.ClientSession, query: HomeQuery) -> dict:
        """La pestaña "Siguiendo": un pedido. Va por POST con el cuerpo en JSON, como lo pide la
        web de x.com, y devuelve la respuesta entera, sin parsear."""
        path = f"/i/api/graphql/{query.query_id}/{HOME_OPERATION}"
        body = {
            "variables": {"count": HOME_COUNT, "includePromotedContent": False,
                          "latestControlAvailable": True, "requestContext": "launch"},
            "features": query.features,
            "queryId": query.query_id,
        }
        headers = await self._api_headers(session, "POST", path)

        try:
            async with session.post(f"https://x.com{path}", json=body, headers=headers,
                                    timeout=_TIMEOUT) as response:
                text = await response.text()
                status, response_headers = response.status, response.headers
        except (aiohttp.ClientError, TimeoutError) as e:
            raise Unreachable(f"{type(e).__name__}: {e}"[:300]) from e

        self._track_limits(response_headers)
        return _check(status, response_headers, text)

    async def discover_home_query(self, session: aiohttp.ClientSession) -> HomeQuery:
        """Busca el queryId de `HomeLatestTimeline` y sus features en el JavaScript de x.com.

        Es contra x.com/home (un documento, lo que pide cualquier navegador al abrir la pestaña) y
        el CDN de los bundles: no es la API, no gasta rate limit. Va con las cookies porque el HTML
        de deslogueado no trae las queries de la home. Cuesta decenas de pedidos al CDN, por eso se
        guarda y sólo se repite cuando X rechaza el que tenemos.
        """
        document = {
            "user-agent": self._user_agent,
            "cookie": self._cookie,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "es-AR,es;q=0.9,en;q=0.8",
            "upgrade-insecure-requests": "1",
        }
        try:
            async with session.get("https://x.com/home", headers=document, timeout=_TIMEOUT) as response:
                html = await response.text()
                final_url = str(response.url)
        except (aiohttp.ClientError, TimeoutError) as e:
            raise Unreachable(f"no pude bajar x.com/home: {type(e).__name__}: {e}"[:300]) from e

        if "/login" in final_url or "/i/flow/" in final_url:
            # Con la sesión vencida x.com/home manda al login. Es el primer lugar donde se ve, y
            # seguir insistiendo con esas cookies es justo lo que no hay que hacer
            raise AccountFlagged(f"x.com/home me mandó a {final_url.split('?')[0]}: la sesión no sirve más",
                                 session_dead=True)

        pending = list(dict.fromkeys(_BUNDLE.findall(html)))
        if not pending:
            raise ClientOutdated("x.com/home no referenció ningún bundle: cambió la forma en que la web carga su JavaScript")

        seen, checked = set(), 0
        while pending and checked < _MAX_BUNDLES:
            url = pending.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                async with session.get(url, headers={"user-agent": self._user_agent},
                                       timeout=_TIMEOUT) as response:
                    code = await response.text()
            except (aiohttp.ClientError, TimeoutError):
                continue
            checked += 1

            found = _extract_operation(code, HOME_OPERATION)
            if found:
                query_id, switches = found
                return HomeQuery(query_id, _build_features(switches))

            # Los chunks se referencian absolutos desde el manifiesto del bundle principal, y
            # relativos al bundle que los carga
            pending.extend(_BUNDLE.findall(code))
            base = url.rsplit("/", 1)[0] + "/"
            pending.extend(urljoin(base, ref) for ref in _RELATIVE_BUNDLE.findall(code) if "/messages/" not in ref)

        raise ClientOutdated(f"no encontré el queryId de {HOME_OPERATION} en {checked} bundles de x.com")

    async def user_id(self, session: aiohttp.ClientSession, screen_name: str) -> str:
        """El id numérico de una cuenta, que es lo que pide el follow."""
        variables = {"screen_name": screen_name, "withGrokTranslatedBio": False}
        path = f"/i/api/graphql/{USER_BY_SCREEN_NAME}"
        params = {"variables": json.dumps(variables, separators=(",", ":")),
                  "features": json.dumps(FEATURES, separators=(",", ":")),
                  "fieldToggles": json.dumps(_USER_TOGGLES, separators=(",", ":"))}
        data = await self._send(session, "GET", path, params=params)
        user = dig(data, "data", "user", "result") or {}
        if not user.get("rest_id") or user.get("__typename") == "UserUnavailable":
            raise TargetMissing(f"X no encuentra a @{screen_name}")
        return user["rest_id"]

    async def follow(self, session: aiohttp.ClientSession, user_id: str):
        """Seguir una cuenta, con el mismo pedido que hace el botón de la web."""
        form = {name: "1" for name in _FOLLOW_FLAGS}
        form["user_id"] = user_id
        await self._send(session, "POST", "/i/api/1.1/friendships/create.json", data=form, form=True)

    async def _send(self, session: aiohttp.ClientSession, method: str, path: str, form: bool = False, **kwargs) -> dict:
        headers = await self._api_headers(session, method, path)
        if form:
            headers["content-type"] = "application/x-www-form-urlencoded"
        try:
            async with session.request(method, f"https://x.com{path}", headers=headers, timeout=_TIMEOUT,
                                       **kwargs) as response:
                return _check(response.status, response.headers, await response.text())
        except (aiohttp.ClientError, TimeoutError) as e:
            raise Unreachable(f"{type(e).__name__}: {e}"[:300]) from e

    @property
    def _cookie(self) -> str:
        return f"auth_token={self._auth_token}; ct0={self._ct0}"

    async def _api_headers(self, session: aiohttp.ClientSession, method: str, path: str) -> dict:
        """Los de una pestaña de x.com logueada. Sin los `sec-ch-ua` que manda Nitter: son de Chrome,
        y con el User-Agent de Firefox serían la contradicción que justamente queremos evitar."""
        return {
            "accept": "*/*",
            "accept-language": "es-AR,es;q=0.9,en;q=0.8",
            "authorization": BEARER,
            "content-type": "application/json",
            "cookie": self._cookie,
            "origin": "https://x.com",
            "referer": "https://x.com/home",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self._user_agent,
            "x-client-transaction-id": await self._transaction_id(session, method, path),
            "x-csrf-token": self._ct0,
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "es",
        }

    async def _transaction_id(self, session: aiohttp.ClientSession, method: str, path: str) -> str:
        pair = random.choice(await self._tid_pairs(session))
        now = int(time.time() - _TID_EPOCH)
        digest = hashlib.sha256(f"{method}!{path}!{now}{_TID_KEYWORD}{pair['animationKey']}".encode()).digest()
        payload = (base64.b64decode(pair["verification"]) + now.to_bytes(4, "little")
                   + digest[:16] + bytes([3]))
        salt = random.randrange(256)
        return base64.b64encode(bytes([salt]) + bytes(b ^ salt for b in payload)).decode().rstrip("=")

    async def _tid_pairs(self, session: aiohttp.ClientSession) -> list[dict]:
        if self._pairs and time.time() - self._pairs_at < _TID_TTL_SECONDS:
            return self._pairs
        try:
            async with session.get(_TID_PAIRS_URL, timeout=_TIMEOUT) as response:
                pairs = json.loads(await response.text()) if response.status == 200 else []
        except (aiohttp.ClientError, TimeoutError, ValueError):
            pairs = []

        if pairs:
            self._pairs, self._pairs_at = pairs, time.time()
        elif not self._pairs:
            # Ni siquiera salí para X: esto no tiene por qué contar como un freno
            raise Unreachable("no pude bajar los pares de la firma x-client-transaction-id")
        return self._pairs

    def _track_limits(self, headers):
        """Los contadores no los llevo yo: X los manda en cada respuesta."""
        try:
            self.window = RateWindow(
                remaining=int(headers["x-rate-limit-remaining"]),
                limit=int(headers["x-rate-limit-limit"]),
                reset=datetime.fromtimestamp(int(headers["x-rate-limit-reset"]), settings.TIMEZONE),
            )
        except (KeyError, ValueError):
            pass


def _extract_operation(code: str, operation: str) -> tuple[str, list[str]] | None:
    """El `queryId` y las `featureSwitches` de una operación, tal como los declara el bundle.

    La forma es `queryId:"...",operationName:"X",operationType:"query",metadata:{featureSwitches:[...]}`,
    pero no se da por sentado ni el orden ni el minificador: se ubica el nombre y se mira alrededor.
    """
    position = code.find(f'operationName:"{operation}"')
    if position == -1:
        return None
    window = code[max(0, position - 400):position + 6000]
    match = re.search(r'queryId\s*:\s*"([\w-]+)"', window)
    if not match:
        return None
    block = re.search(r'featureSwitches\s*:\s*\[(.*?)\]', window, re.DOTALL)
    switches = re.findall(r'"(\w+)"', block.group(1)) if block else []
    return match.group(1), switches


def _build_features(switches: list[str]) -> dict:
    """El blob que pide X, armado con la lista que el propio bundle declara para la operación. Si
    el bundle no la trajo, el de Nitter: mejor eso que mandar nada."""
    if not switches:
        return dict(FEATURES)
    return {name: FEATURES.get(name, name not in _FALSE_FEATURES) for name in switches}


def _check(status: int, headers, body: str) -> dict:
    """Lee la respuesta cruda y decide qué pasó. Es la parte que Nitter tapaba con un solo cartel."""
    if body.lstrip()[:1] == "<":
        title = body.split("<title>", 1)[-1].split("</title>", 1)[0].strip()[:80] if "<title>" in body else ""
        if "cloudflare" in body.lower() or "cf-ray" in headers:
            raise AccountFlagged(f"challenge de Cloudflare (HTTP {status}, «{title}»): X marcó el tráfico")
        raise Throttled(f"HTTP {status} con una página HTML en vez de JSON («{title}»)")

    try:
        data = json.loads(body) if body else {}
    except ValueError:
        data = {}

    codes = {e.get("code"): e.get("message", "") for e in data.get("errors", []) if isinstance(e, dict)}
    detail = "; ".join(f"({code}) {message}" for code, message in codes.items())[:300]

    for code, why in _SESSION_DEAD.items():
        if code in codes:
            raise AccountFlagged(f"{why}: {detail}", session_dead=True)
    for code, why in _ACCOUNT_FLAGGED.items():
        if code in codes:
            raise AccountFlagged(f"{why}: {detail}")

    if status == 429 or _RATE_LIMITED in codes:
        reset = headers.get("x-rate-limit-reset")
        resets_at = datetime.fromtimestamp(int(reset), settings.TIMEZONE) if reset and reset.isdigit() else None
        raise Throttled(f"rate limit de X (HTTP {status}{', ' + detail if detail else ''})", resets_at=resets_at)

    if _FOLLOW_LIMIT in codes:
        raise Throttled(f"X no me deja seguir a más cuentas por ahora: {detail}")
    if _ALREADY_REQUESTED in codes:
        return data
    for code, why in _TARGET_MISSING.items():
        if code in codes:
            raise TargetMissing(f"la cuenta {why}: {detail}")

    if status == 401:
        raise AccountFlagged(f"HTTP 401: {detail or body[:200]}", session_dead=True)
    if status == 403:
        raise AccountFlagged(f"HTTP 403 sin explicación: {detail or body[:200]}")

    if status == 404 or status == 400 or "cannot be null" in detail:
        # Un queryId rotado, una feature nueva que X exige, o una firma que no le gustó. No se
        # arregla esperando: la próxima vuelta vuelve a buscar el queryId y las features en x.com
        raise Throttled(f"X no acepta el pedido (HTTP {status}{': ' + detail if detail else ''}). "
                        f"Probablemente rotó el queryId o pide features nuevas: los vuelvo a buscar",
                        stale_query=True)

    if status >= 400:
        raise Throttled(f"HTTP {status}: {detail or body[:200]}")

    if not data.get("data") and codes:
        raise Throttled(f"X contestó sólo errores: {detail}")
    return data
