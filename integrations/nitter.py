"""Lo que mi instancia de Nitter sabe de sí misma.

Los contadores de rate limit no son míos: son los headers `x-rate-limit-*` que X manda en cada
respuesta y que Nitter guarda por sesión y por endpoint. Con `enableDebug = true` los expone en
`/.sessions` y `/.health`, que son locales y **no le pegan a X**: preguntarlos sale gratis, así que
el scaneo se maneja con el margen real en vez de con un cronograma fijo y a ciegas.

Nada de esto se guarda en Mongo a propósito: el estado que importa (cuánto queda, cuándo se repone)
ya lo lleva Nitter contra la fuente autoritativa, y guardar una copia sería tener dos verdades.
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp

from config.settings import settings
from utils.date_format import format_time

# Nitter deja de usar una sesión cuando le quedan 10 pedidos o menos, así que por debajo de eso el
# pedido no sale igual. Le sumo un colchón proporcional para no rozar nunca el límite de X
_HARD_FLOOR = 10
_FLOOR_FRACTION = 0.25
# De lo que sobra por encima del colchón gasto un cuarto por vuelta: si algo más está consumiendo la
# sesión, freno antes de que X vea una ráfaga
_SPEND_FRACTION = 0.25
# Sin datos de la instancia no adivino: leo una sola cuenta, el ritmo más lento posible
_BLIND_FEEDS = 1
# Techo por vuelta aunque sobre margen: el objetivo es ir lento, no llenar el presupuesto
_MAX_FEEDS = 3

_TIMEOUT = aiohttp.ClientTimeout(total=10)


def instance_url() -> str | None:
    """La instancia propia de Nitter. Si no le puse esquema asumo http: corre en la misma máquina."""
    raw = (settings.NITTER_HOST_URL or "").strip().rstrip("/")
    if not raw:
        return None
    return raw if raw.startswith(("http://", "https://")) else f"http://{raw}"


@dataclass(frozen=True)
class ApiLimit:
    """El presupuesto que X le dio a una sesión para un endpoint, en la ventana en curso."""
    name: str
    remaining: int
    limit: int
    reset: datetime

    @property
    def stale(self) -> bool:
        """La ventana ya venció: `remaining` es de la anterior y X lo repuso, no me dice nada."""
        return self.reset <= datetime.now(settings.TIMEZONE)

    @property
    def floor(self) -> int:
        return max(_HARD_FLOOR, int(self.limit * _FLOOR_FRACTION))

    @property
    def spendable(self) -> int:
        """Cuánto puedo gastar sin bajar del colchón. Si la ventana venció, X ya repuso el
        presupuesto entero y el número que tengo guardado no frena nada."""
        if self.stale:
            return max(self.limit, _HARD_FLOOR)
        return max(0, self.remaining - self.floor)

    def __str__(self) -> str:
        cap = f"/{self.limit}" if self.limit else ""
        window = "ventana vencida" if self.stale else f"se repone {format_time(self.reset)}"
        return f"{self.name} {self.remaining}{cap} ({window})"


@dataclass
class NitterSession:
    kind: str
    limited: bool
    limits: list[ApiLimit] = field(default_factory=list)

    @property
    def tightest(self) -> ApiLimit | None:
        """El endpoint con menos aire. No hardcodeo cuál es el del RSS: si cualquiera está justo,
        voy lento igual, que es lo que quiero."""
        return min(self.limits, key=lambda limit: limit.spendable, default=None)

    @property
    def feeds(self) -> int:
        """Cuántos feeds me deja pedir esta sesión ahora mismo."""
        if self.limited:
            return 0
        tightest = self.tightest
        if tightest is None:
            # Sesión sin estrenar: todavía no hay headers de X que mirar
            return _BLIND_FEEDS
        return int(tightest.spendable * _SPEND_FRACTION)

    @property
    def resumes_at(self) -> datetime | None:
        pending = [limit.reset for limit in self.limits if not limit.stale]
        return min(pending) if pending else None


@dataclass
class SessionPool:
    sessions: list[NitterSession]

    @property
    def feeds(self) -> int:
        """El presupuesto de la vuelta. Suma de las sesiones: agregar cuentas en `sessions.jsonl`
        levanta el ritmo solo, sin tocar código."""
        return min(sum(session.feeds for session in self.sessions), _MAX_FEEDS)

    @property
    def resumes_at(self) -> datetime | None:
        """Cuándo vuelve a haber margen, si ahora no hay."""
        if self.feeds:
            return None
        pending = [session.resumes_at for session in self.sessions if session.resumes_at]
        return min(pending) if pending else None

    @property
    def detail(self) -> str:
        total = len(self.sessions)
        limited = sum(1 for session in self.sessions if session.limited)
        parts = [f"{total} {'sesión' if total == 1 else 'sesiones'}, {limited} marcada(s) como limitada(s)"]
        tightest = min((session.tightest for session in self.sessions if session.tightest),
                       key=lambda limit: limit.spendable, default=None)
        if tightest:
            parts.append(f"lo más justo es {tightest}")
        return "; ".join(parts)


def _iter_session_nodes(payload):
    """Las sesiones vienen anidadas distinto según la versión de Nitter, así que en vez de asumir la
    forma del JSON me quedo con cualquier objeto que traiga un `apis` adentro."""
    if isinstance(payload, dict):
        if isinstance(payload.get("apis"), dict):
            yield payload
            return
        for value in payload.values():
            yield from _iter_session_nodes(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_session_nodes(item)


def _parse_session(node: dict) -> NitterSession:
    limits = []
    for name, raw in node["apis"].items():
        if not isinstance(raw, dict):
            continue
        remaining, limit, reset = raw.get("remaining"), raw.get("limit"), raw.get("reset")
        if not isinstance(remaining, int) or not isinstance(reset, int):
            continue
        limits.append(ApiLimit(
            name=str(name),
            remaining=remaining,
            limit=limit if isinstance(limit, int) and limit > 0 else 0,
            reset=datetime.fromtimestamp(reset, settings.TIMEZONE),
        ))
    return NitterSession(kind=str(node.get("kind", "?")), limited=bool(node.get("limited")), limits=limits)


def parse_pool(payload) -> SessionPool | None:
    """None si no reconozco lo que contestó: prefiero ir a ciegas y lento antes que inventar margen."""
    nodes = list(_iter_session_nodes(payload))
    if not nodes:
        return None
    return SessionPool([_parse_session(node) for node in nodes])


async def _fetch_json(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(url, timeout=_TIMEOUT) as response:
            if response.status != 200:
                return None
            return await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None


async def fetch_pool(session: aiohttp.ClientSession, base_url: str) -> SessionPool | None:
    payload = await _fetch_json(session, f"{base_url}/.sessions")
    return parse_pool(payload) if payload is not None else None


async def fetch_health(session: aiohttp.ClientSession, base_url: str):
    """Lo que la instancia lleva hecho desde que arrancó el contenedor: sesiones y pedidos por api."""
    return await _fetch_json(session, f"{base_url}/.health")


async def get_pool() -> SessionPool | None:
    base_url = instance_url()
    if not base_url:
        return None
    async with aiohttp.ClientSession() as session:
        return await fetch_pool(session, base_url)


def budget(pool: SessionPool | None) -> int:
    """Cuántas cuentas leo esta vuelta. Sin instancia que me informe, una sola."""
    return _BLIND_FEEDS if pool is None else pool.feeds


# Nitter contesta siempre el mismo cartel genérico ("Instance has been rate limited") para seis cosas
# distintas: challenge de Cloudflare, cuenta bloqueada, token vencido, el rate limit de verdad, un
# 404 transitorio y un `except Exception` que se traga cualquier falla de red. La causa real la
# escribe por stdout, en `echo`s crudos de apiutils.nim que NO dependen de `enableDebug`
_LOG_MARKERS = re.compile(r"\[cloudflare\]|\[sessions\]|Fetch error|ERROR 400|\berror: |rate limited by api")
_LOG_LINES = 3
_LOG_LINE_CHARS = 200
_DOCKER_TIMEOUT = 10


async def recent_failures(seconds: int = 90, lines: int = _LOG_LINES) -> list[str] | None:
    """Lo que escupió el contenedor recién, filtrado a las líneas que explican la falla.

    `None` es "no pude leer los logs" (no está el binario de docker, o el usuario con el que corro no
    tiene permiso); una lista vacía es "leí y no dijo nada", que también es información.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--since", f"{seconds}s", settings.NITTER_CONTAINER,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError):
        return None

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_DOCKER_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        return None

    if proc.returncode != 0:
        return None

    # docker manda el stdout del contenedor a mi stdout y su stderr a mi stderr; los junto porque no
    # me importa por dónde salió, me importa qué dijo
    text = b"\n".join(part for part in (stdout, stderr) if part).decode("utf-8", errors="replace")
    matches = [line.strip()[:_LOG_LINE_CHARS] for line in text.splitlines() if _LOG_MARKERS.search(line)]
    return list(dict.fromkeys(matches))[-lines:]
