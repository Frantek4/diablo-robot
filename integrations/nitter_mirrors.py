import asyncio
import re
import time
from urllib.parse import urlparse

import aiohttp
import feedparser

from config.settings import settings
from models.nitter_mirror import SOURCE_ENV, SOURCE_SEED, SOURCE_WIKI, normalize_mirror_url
from models.social_media import SocialMedia

# Arranco con esta lista si el wiki no contesta; después el catálogo se actualiza solo
SEED_MIRRORS = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
    "https://nitter.tiekoetter.com",
    "https://nuku.trabun.org",
    "https://nitter.catsarch.com",
    "https://nitter.kareem.one",
]

# Links del wiki que no son instancias: redirectores random, la página de estado, certificados
NON_INSTANCE_HOSTS = {
    "github.com",
    "www.ssllabs.com",
    "status.d420.de",
    "farside.link",
    "twiiit.com",
}

# Del wiki solo me sirven las instancias de la web clara: sin Tor ni I2P no llego
WIKI_SECTIONS = {"official", "public"}

_HEADERS = {"User-Agent": settings.USER_AGENT}
_PROBE_TIMEOUT = aiohttp.ClientTimeout(total=25)


def nitter_error_reason(body: str) -> str | None:
    """Saca el motivo que Nitter escribe en su pantalla de error, para no loguear un HTTP pelado."""
    match = re.search(r'error-panel"?>\s*<span>(.*?)</span>', body, re.DOTALL)
    if not match:
        return None
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', match.group(1))).strip() or None


def parse_wiki_instances(markdown: str) -> list[str]:
    """Lee la tabla de instancias del wiki de Nitter y devuelve las que dicen estar online y andando."""
    urls = []
    section = None

    for line in markdown.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            section = stripped.lstrip("#").strip().lower()
            continue
        if section not in WIKI_SECTIONS or not stripped.startswith("| ["):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        match = re.search(r'\]\((https?://[^)\s]+)\)', cells[0])
        if not match:
            continue

        # La tabla de "Public" marca online y funcionando; la oficial no tiene esas columnas
        if section == "public":
            marks = " ".join(cells[1:3])
            if ":x:" in marks or "❌" in marks:
                continue

        url = normalize_mirror_url(match.group(1))
        if not url:
            continue

        host = urlparse(url).netloc
        if host in NON_INSTANCE_HOSTS or host.endswith((".onion", ".i2p")):
            continue

        urls.append(url)

    return list(dict.fromkeys(urls))


async def fetch_wiki_candidates(session: aiohttp.ClientSession) -> list[str]:
    async with session.get(settings.NITTER_INSTANCES_URL, headers=_HEADERS, timeout=_PROBE_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        markdown = (await response.read()).decode("utf-8", errors="replace")
    return parse_wiki_instances(markdown)


def entries_have_tweets(entries, account: str) -> bool:
    """Los items tienen que linkear a tweets de la cuenta.

    Hay mirrors (xcancel) que contestan HTTP 200 con un RSS válido cuyo único item dice que el lector
    no está en su whitelist: para el bot eso es tan inservible como un 403.
    """
    pattern = re.compile(rf'/{re.escape(account)}/status/\d+', re.IGNORECASE)
    return any(pattern.search(entry.get("link", "")) for entry in entries)


def feed_has_tweets(content: str, account: str) -> bool:
    feed = feedparser.parse(content)
    return bool(feed.entries) and entries_have_tweets(feed.entries, account)


async def probe(session: aiohttp.ClientSession, mirror_url: str, account: str) -> tuple[bool, str | None, float | None]:
    """Le pide a un mirror el feed de una cuenta de verdad. Devuelve (anda, motivo, latencia en ms)."""
    started = time.perf_counter()
    try:
        async with session.get(
            f"{mirror_url}/{account}/rss", headers=_HEADERS, timeout=_PROBE_TIMEOUT
        ) as response:
            body = (await response.read()).decode("utf-8", errors="replace")
            latency_ms = (time.perf_counter() - started) * 1000

            if response.status != 200:
                reason = nitter_error_reason(body)
                return False, f"HTTP {response.status}: {reason}" if reason else f"HTTP {response.status}", latency_ms

            if not feed_has_tweets(body, account):
                reason = nitter_error_reason(body) or "contesta pero no devuelve tweets"
                return False, reason, latency_ms

            return True, None, latency_ms
    except asyncio.TimeoutError:
        return False, "timeout", None
    except aiohttp.ClientError as e:
        return False, type(e).__name__, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


def probe_account(bot) -> str:
    """Pruebo con una cuenta que realmente sigo, así el chequeo mide lo mismo que va a hacer el scaneo."""
    influencers = bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)
    if influencers:
        return influencers[0]["name"]
    return settings.NITTER_PROBE_ACCOUNT


async def seed_catalog(bot) -> int:
    """Deja en Mongo los mirrors de arranque (el del .env y la lista fija). Devuelve cuántos sumó."""
    added = 0
    env_url = normalize_mirror_url(settings.TWITTER_RSS_BRIDGE_URL)
    if env_url and bot.nitter_mirror_dao.upsert_candidate(env_url, source=SOURCE_ENV):
        added += 1
    for url in SEED_MIRRORS:
        if bot.nitter_mirror_dao.upsert_candidate(url, source=SOURCE_SEED):
            added += 1
    return added


async def refresh_catalog(bot, session: aiohttp.ClientSession) -> list[str]:
    """Trae la lista de instancias del wiki de Nitter y suma al repositorio las que no tenía."""
    candidates = await fetch_wiki_candidates(session)
    return [url for url in candidates if bot.nitter_mirror_dao.upsert_candidate(url, source=SOURCE_WIKI)]


async def report_pool_state(bot):
    """Avisa cuando el repositorio se queda sin mirrors online, y cuando vuelve a tener. Una sola vez cada uno."""
    online = bot.nitter_mirror_dao.count_online()
    already_alerted = bot.nitter_mirror_dao.get_state().get("no_mirrors_alerted", False)

    if online == 0 and not already_alerted:
        total = len(bot.nitter_mirror_dao.get_all())
        await bot.messager.log(
            f"Me quedé sin mirrors de Nitter online: probé los {total} que tengo en el repositorio y no anda "
            f"ninguno. No voy a poder traer nada de Twitter hasta que aparezca uno nuevo. "
            f"Mirá `{settings.PREFIX}nitter` para ver por qué falló cada uno.",
            level="CRITICAL",
        )
        bot.nitter_mirror_dao.save_state(no_mirrors_alerted=True)
    elif online > 0 and already_alerted:
        await bot.messager.log(f"Volvió a haber mirrors de Nitter: tengo {online} online, sigo con Twitter.")
        bot.nitter_mirror_dao.save_state(no_mirrors_alerted=False)
