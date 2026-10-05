"""Sonda de un solo uso: ¿qué camino sirve hoy para leer el home de Instagram y el de X?

No forma parte del bot. Existe porque las dos preguntas que definen la reescritura no se pueden
contestar leyendo código:

  - El home de Instagram tiene varios caminos posibles y no todos siguen vivos. El que trae
    instaloader (`get_feed_posts`) pega en la ruta vieja por `query_hash`, mientras que
    `get_posts()` logueado ya usa la nueva por `doc_id`. Hay que ver cuál contesta con la sesión
    real, no adivinar.
  - El `queryId` de `HomeLatestTimeline` de X cambia cada tanto y no hay dónde consultarlo salvo
    en el bundle de JavaScript que sirve x.com. Esto lo busca ahí.

**Un disparo por candidato, y se termina.** No es un loop ni algo para dejar corriendo: cada
candidato de Instagram es un pedido real contra la cuenta que estamos cuidando.

No escribe nada: ni en Mongo, ni en disco, ni en Discord. No imprime cookies.

    python3 tools/probe_feeds.py            # las dos plataformas
    python3 tools/probe_feeds.py --only x   # o una sola: x | instagram
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TIMEOUT = 30
# El bearer público de la web de X. No es un secreto: viaja en cada pedido que hace el navegador
BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
          "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
IG_APP_ID = "936619743392459"


def title(text: str):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def show_response(response: requests.Response):
    """Lo que importa de una respuesta: el status, el rate limit y, si falló, qué dijo."""
    print(f"  HTTP {response.status_code}  ({len(response.content)} bytes)")

    limits = {k.lower(): v for k, v in response.headers.items() if "rate-limit" in k.lower()}
    if limits:
        print(f"  rate limit: {json.dumps(limits)}")

    try:
        return response.json()
    except ValueError:
        print(f"  no es JSON. Empieza con: {response.text[:200]!r}")
        return None


def find_posts(payload):
    """Busca posts en cualquier forma de JSON, sin asumir la estructura.

    Es a propósito: la sonda existe justamente porque no sabemos qué forma tiene la respuesta.
    Se queda con cualquier diccionario que tenga pinta de post (un `shortcode`/`code`, o un
    `rest_id` con `legacy` adentro) y le saca el autor de donde esté.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            author = (
                _dig(node, "owner", "username")
                or _dig(node, "user", "username")
                or _dig(node, "user", "screen_name")
                or _dig(node, "core", "user_results", "result", "core", "screen_name")
                or _dig(node, "core", "user_results", "result", "legacy", "screen_name")
            )
            is_v1_tweet = "id_str" in node and ("full_text" in node or "text" in node)
            if (node.get("shortcode") or node.get("code")
                    or ("rest_id" in node and "legacy" in node) or is_v1_tweet):
                found.append({
                    "author": author,
                    "is_ad": bool(node.get("ad_id") or node.get("is_paid_partnership")),
                    "followed": _followed_flag(node),
                })
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _dig(node, *keys):
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) else None


def _followed_flag(node):
    """Si la respuesta dice o no que seguimos al autor. Es la pregunta que decide si se puede
    filtrar el home por cuentas seguidas o si hay que confiar en la tabla de ruteo."""
    for owner_key in ("owner", "user"):
        owner = node.get(owner_key)
        if isinstance(owner, dict):
            for flag in ("followed_by_viewer", "following"):
                if flag in owner:
                    return owner[flag]
            status = owner.get("friendship_status")
            if isinstance(status, dict) and "following" in status:
                return status["following"]
    return None


def report(payload):
    posts = find_posts(payload)
    if not posts:
        keys = list(payload)[:10] if isinstance(payload, dict) else type(payload).__name__
        print(f"  ✗ ningún post reconocible. Claves de primer nivel: {keys}")
        if isinstance(payload, dict) and payload.get("errors"):
            print(f"  errores: {json.dumps(payload['errors'])[:600]}")
        return

    authors = [p["author"] for p in posts if p["author"]]
    ads = sum(1 for p in posts if p["is_ad"])
    with_flag = sum(1 for p in posts if p["followed"] is not None)

    print(f"  ✓ {len(posts)} posts, {len(set(authors))} autores distintos, {ads} marcados como ad")
    print(f"  autores: {', '.join(sorted(set(authors))[:15]) or '(no pude sacar ninguno)'}")
    print(f"  traen flag de 'seguido': {with_flag}/{len(posts)}"
          + ("  ← se puede filtrar por followed" if with_flag == len(posts) else "  ← OJO: no alcanza para filtrar"))


# ---------------------------------------------------------------- Instagram

def probe_instagram():
    title("INSTAGRAM")

    username = os.environ.get("IG_USERNAME", "")
    if not username:
        print("No hay IG_USERNAME en el .env, salteo Instagram.")
        return

    try:
        import instaloader
    except ImportError:
        print("No está instaloader en este intérprete.")
        return

    loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1, request_timeout=30.0,
                                     iphone_support=False,
                                     user_agent=os.environ.get("IG_USER_AGENT") or None)
    try:
        loader.load_session_from_file(username)
    except FileNotFoundError:
        print(f"No hay sesión guardada para @{username}. Generala con "
              f"'instaloader --load-cookies firefox --sessionfile ~/.config/instaloader/session-{username}'.")
        return

    session = loader.context._session
    csrf = session.cookies.get("csrftoken", "")
    print(f"Sesión de @{username} cargada. Verificando que siga siendo nuestra...")
    try:
        who = loader.test_login()
    except Exception as e:
        print(f"  test_login() reventó: {type(e).__name__}: {e}")
        who = None
    print(f"  Instagram dice que entro como: {who or '(nadie)'}")
    if not who:
        print("  Sin sesión válida el resto de la sonda no dice nada. Rehacé la sesión primero.")
        return

    headers = {
        "X-IG-App-ID": IG_APP_ID,
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
        "Accept": "*/*",
    }

    # Los candidatos, del menos invasivo al más. El primero es el que usa instaloader hoy
    candidates = [
        ("A. GraphQL viejo (query_hash, el de instaloader.get_feed_posts)",
         "GET", "https://www.instagram.com/graphql/query/",
         {"params": {"query_hash": "d6f4427fbe92d846298cf93df0b937d3", "variables": "{}"}}),
        ("B. REST del front web (GET /api/v1/feed/timeline/)",
         "GET", "https://www.instagram.com/api/v1/feed/timeline/", {}),
        ("C. REST del front web (POST /api/v1/feed/timeline/)",
         "POST", "https://www.instagram.com/api/v1/feed/timeline/",
         {"data": {"reason": "cold_start_fetch", "num_prefetch_live_ms": "0"}}),
    ]

    for name, method, url, extra in candidates:
        print(f"\n{name}")
        try:
            response = session.request(method, url, headers=headers, timeout=TIMEOUT, **extra)
        except requests.RequestException as e:
            print(f"  ✗ {type(e).__name__}: {e}")
            continue
        payload = show_response(response)
        if payload is not None:
            report(payload)


# ------------------------------------------------------------------------ X

def load_x_cookies(path: Path):
    """Las cookies que hoy usa Nitter. Todavía no existe X_SESSION_FILE: sale de sessions.jsonl."""
    if not path.exists():
        print(f"No encontré {path}. Pasá la ruta con --x-session.")
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        data = json.loads(line)
        if data.get("auth_token") and data.get("ct0"):
            return data
    print(f"{path} no tiene ninguna línea con auth_token y ct0.")
    return None


def x_headers(creds):
    return {
        "authorization": f"Bearer {BEARER}",
        "x-csrf-token": creds["ct0"],
        "cookie": f"auth_token={creds['auth_token']}; ct0={creds['ct0']}",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "es",
        "referer": "https://x.com/home",
        "user-agent": os.environ.get("X_USER_AGENT") or os.environ.get("USER_AGENT", "Mozilla/5.0"),
        "accept": "*/*",
    }


# El bundle de x.com se mudó de `responsive-web/client-web/` a `x-web/x-web/`; el regex acepta
# los dos por si el Pi recibe una versión distinta de la que veo yo
_BUNDLE = re.compile(r'https://abs\.twimg\.com/(?:x-web|responsive-web)/[^"\'\s<>]+?\.js')
_MAX_BUNDLES = 120

# Las pocas features que van en false. X sólo falla cuando una **falta** ("cannot be null"), no
# por el valor, así que el resto se manda en true y el blob se arma solo desde `featureSwitches`
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


def build_features(switches):
    """El blob que pide X, derivado de la lista que el propio bundle declara para la operación."""
    return {name: name not in _FALSE_FEATURES for name in switches}


def find_query_id(session, headers):
    """El queryId de HomeLatestTimeline vive en el bundle de JS que sirve x.com.

    Es contra el CDN, no contra la API: no gasta rate limit ni lo ve la cuenta. Va **con las
    cookies**, porque el HTML de deslogueado trae un entry chico de i18n y nada más: las queries
    están en el bundle de logueado. Si esto funciona, el cliente nuevo puede resolver el queryId
    solo cuando X lo rote, en vez de tenerlo hardcodeado y romperse.
    """
    print("\nBuscando el queryId de HomeLatestTimeline en el bundle de x.com...")
    # Headers de navegador pidiendo un documento, no los de la API: un bearer viajando en el
    # pedido del HTML es una contradicción que no comete ningún cliente real
    document = {
        "user-agent": headers["user-agent"],
        "cookie": headers["cookie"],
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "es-AR,es;q=0.9,en;q=0.8",
        "upgrade-insecure-requests": "1",
    }
    try:
        home = session.get("https://x.com/home", headers=document, timeout=TIMEOUT)
    except requests.RequestException as e:
        print(f"  ✗ no pude bajar x.com/home: {type(e).__name__}: {e}")
        return None

    print(f"  x.com/home → HTTP {home.status_code}, {len(home.text)} bytes")
    pending = list(dict.fromkeys(_BUNDLE.findall(home.text)))
    if not pending:
        print("  ✗ el HTML no referenció ningún bundle. ¿Contestó la página de deslogueado?")
        return None

    seen, checked = set(), 0
    while pending and checked < _MAX_BUNDLES:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            body = requests.get(url, headers={"user-agent": headers["user-agent"]},
                                timeout=TIMEOUT).text
        except requests.RequestException:
            continue
        checked += 1

        found = _extract_operation(body, "HomeLatestTimeline")
        if found:
            query_id, switches = found
            print(f"  ✓ queryId = {query_id}   (en {url.rsplit('/', 1)[-1]}, "
                  f"tras revisar {checked} bundles)")
            print(f"  ✓ {len(switches)} features declaradas por el propio bundle "
                  f"— el blob se arma solo, no hay que mantenerlo a mano")
            return query_id, switches

        # Los chunks se referencian de dos formas: absolutos en el manifiesto que trae el bundle
        # principal, y relativos al bundle que los carga
        base = url.rsplit("/", 1)[0]
        pending.extend(_BUNDLE.findall(body))
        for ref in re.findall(r'["\'](\.{0,2}/[\w\-./]+?\.js)["\']', body):
            if "/messages/" in ref:
                continue
            pending.append(requests.compat.urljoin(base + "/", ref))

    print(f"  ✗ no lo encontré en {checked} bundles. Sacalo a mano de las devtools (pestaña Red, "
          f"filtro 'HomeLatestTimeline') o del fuente de gallery-dl.")
    return None


def _extract_operation(body: str, operation: str):
    """El `queryId` y las `featureSwitches` de una operación, tal como los declara el bundle.

    La forma es `queryId:"...",operationName:"X",operationType:"query",metadata:{featureSwitches:[...]}`,
    pero no doy por sentado ni el orden ni el minificador: ubico el nombre y miro alrededor.
    """
    position = body.find(f'operationName:"{operation}"')
    if position == -1:
        return None

    window = body[max(0, position - 400):position + 6000]
    match = re.search(r'queryId\s*:\s*"([\w-]+)"', window)
    if not match:
        return None

    switches = []
    block = re.search(r'featureSwitches\s*:\s*\[(.*?)\]', window, re.DOTALL)
    if block:
        switches = re.findall(r'"([\w]+)"', block.group(1))
    return match.group(1), switches


def probe_x(session_path: Path):
    title("X / TWITTER")

    creds = load_x_cookies(session_path)
    if not creds:
        return
    headers = x_headers(creds)
    session = requests.Session()
    print(f"Cookies de @{creds.get('username', '?')} cargadas.")

    print("\n1. ¿La sesión sigue viva? (verify_credentials)")
    try:
        response = session.get("https://api.x.com/1.1/account/verify_credentials.json",
                               headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        print(f"  ✗ {type(e).__name__}: {e}")
        return
    payload = show_response(response)
    if response.status_code != 200:
        print("  ✗ la sesión no sirve. Esto es lo que Nitter viene disfrazando de 'rate limited'.")
        print("    Rehacé las cookies antes de seguir: el cliente nuevo fallaría igual.")
        return
    print(f"  ✓ entro como @{payload.get('screen_name')} "
          f"(sigue a {payload.get('friends_count')} cuentas)")

    # Si este anda, no hay queryId ni blob de features que mantener: es el camino más barato de
    # sostener con el tiempo, así que se prueba antes que GraphQL
    print("\n2. API v1.1: statuses/home_timeline.json")
    try:
        response = session.get("https://api.x.com/1.1/statuses/home_timeline.json",
                               headers=headers, timeout=TIMEOUT,
                               params={"count": 40, "tweet_mode": "extended",
                                       "exclude_replies": "true", "include_entities": "true"})
    except requests.RequestException as e:
        print(f"  ✗ {type(e).__name__}: {e}")
    else:
        payload = show_response(response)
        if isinstance(payload, dict) and payload.get("errors"):
            for error in payload["errors"]:
                print(f"  error {error.get('code')}: {error.get('message', '')[:300]}")
        elif payload is not None:
            report(payload)
            print("  ← si esto trajo tweets, es el camino a usar: sin queryId ni features")

    discovered = find_query_id(session, headers)
    if not discovered:
        return
    query_id, switches = discovered

    print("\n3. GraphQL: HomeLatestTimeline (la pestaña 'Siguiendo')")
    variables = {"count": 20, "includePromotedContent": False,
                 "latestControlAvailable": True, "requestContext": "launch"}
    features = build_features(switches)
    print(f"  features derivadas del bundle: {len(features)}")
    url = f"https://x.com/i/api/graphql/{query_id}/HomeLatestTimeline"
    try:
        response = session.get(url, headers=headers, timeout=TIMEOUT, params={
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(features, separators=(",", ":")),
        })
    except requests.RequestException as e:
        print(f"  ✗ {type(e).__name__}: {e}")
        return

    payload = show_response(response)
    if payload is None:
        return

    # El 400 por features es el error que más va a aparecer con el tiempo, y dice exactamente cuáles
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        for error in errors:
            print(f"  error {error.get('code')}: {error.get('message', '')[:400]}")
        missing = re.findall(r'The following features cannot be null: (.+)', json.dumps(errors))
        if missing:
            print(f"  ← faltan features: {missing[0][:400]}")
        return

    report(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("x", "instagram"), help="probar una sola plataforma")
    parser.add_argument("--x-session", default=str(ROOT / "nitter" / "sessions.jsonl"),
                        help="archivo con las cookies de X (default: las que usa Nitter)")
    args = parser.parse_args()

    if args.only != "x":
        probe_instagram()
    if args.only != "instagram":
        probe_x(Path(args.x_session))

    print("\nListo. Pasame esta salida entera.")


if __name__ == "__main__":
    sys.exit(main())
