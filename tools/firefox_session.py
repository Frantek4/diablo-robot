#!/usr/bin/env python3
"""Arma la sesión de X o de Instagram del bot con las cookies de Firefox, sin un solo pedido.

Lee `cookies.sqlite` del perfil de Firefox en modo inmutable (no lo toca aunque Firefox esté
abierto) y escribe el archivo de sesión donde lo busca el bot. **No se conecta a nada.** Es a
propósito: `instaloader --load-cookies firefox` hace lo mismo pero después le pide a Instagram un
"¿estoy logueado?" a un endpoint viejo, y si le rebota lo reintenta. Generar una sesión no tiene por
qué costar pedidos, y menos justo cuando la cuenta viene de un freno. Si la sesión no sirve, lo dice
el bot en su primera vuelta y frena solo.

Uso, desde la raíz del repo, en la máquina del Firefox logueado con la cuenta del bot:
    python3 tools/firefox_session.py x robot_devil_cai
    python3 tools/firefox_session.py instagram diablo_robot_cai

Escribe:
    x          ~/.config/diablo-robot/x-session-<usuario>.json   (JSON, una línea)
    instagram  ~/.config/instaloader/session-<usuario>            (dict de cookies en pickle)

Si el bot corre en otra máquina, después hay que copiar el archivo a la misma ruta allá.
"""

import json
import pickle
import sys
from argparse import ArgumentParser
from glob import glob
from os import chmod, makedirs
from os.path import dirname, expanduser, getsize
from platform import system
from sqlite3 import OperationalError, connect

# Por red: de qué dominios son sus cookies, cuáles no pueden faltar, y cuáles se guardan
PLATFORMS = {
    "x": {
        "domains": ("x.com", "twitter.com"),
        # auth_token es la sesión, ct0 el token anti-CSRF, twid trae el id numérico
        "required": ("auth_token", "ct0", "twid"),
        "keep": ("auth_token", "ct0", "twid"),
        "site": "https://x.com",
    },
    "instagram": {
        "domains": ("instagram.com",),
        # sessionid es la sesión, csrftoken el token anti-CSRF, ds_user_id el id numérico
        "required": ("sessionid", "csrftoken", "ds_user_id"),
        # Todas: el navegador manda todas (mid, ig_did, rur, datr...), y el bot también
        "keep": None,
        "site": "https://www.instagram.com",
    },
}


def read_cookies(cookiefile: str, platform: dict) -> dict:
    """Las cookies de la red, de la base de Firefox abierta en modo inmutable."""
    conn = connect(f"file:{cookiefile}?immutable=1", uri=True)
    domains = platform["domains"]
    try:
        marks = ",".join("?" for _ in domains)
        rows = conn.execute(f"SELECT name, value FROM moz_cookies WHERE baseDomain IN ({marks})", domains)
    except OperationalError:
        clause = " OR ".join("host LIKE ?" for _ in domains)
        rows = conn.execute(f"SELECT name, value FROM moz_cookies WHERE {clause}", [f"%{d}" for d in domains])
    keep = platform["keep"]
    return {name: value for name, value in rows if keep is None or name in keep}


def candidate_cookiefiles() -> list:
    """Todas las rutas donde puede estar el perfil, incluidas las de Snap y Flatpak en Linux."""
    patterns = {
        "Windows": ["~/AppData/Roaming/Mozilla/Firefox/Profiles/*/cookies.sqlite"],
        "Darwin": ["~/Library/Application Support/Firefox/Profiles/*/cookies.sqlite"],
    }.get(system(), [
        "~/.mozilla/firefox/*/cookies.sqlite",
        # Firefox de Snap y de Flatpak no usan ~/.mozilla
        "~/snap/firefox/common/.mozilla/firefox/*/cookies.sqlite",
        "~/.var/app/org.mozilla.firefox/.mozilla/firefox/*/cookies.sqlite",
    ])
    found = []
    for pattern in patterns:
        found.extend(glob(expanduser(pattern)))
    return found


def get_cookiefile(platform: dict) -> str:
    """El perfil que realmente tenga la sesión de esa red, no el primero que aparezca."""
    candidates = candidate_cookiefiles()
    if not candidates:
        raise SystemExit("No encontré cookies.sqlite de Firefox. Pasalo con -c COOKIEFILE.")

    for path in sorted(candidates, key=getsize, reverse=True):
        try:
            cookies = read_cookies(path, platform)
        except OperationalError:
            continue
        if all(cookies.get(name) for name in platform["required"]):
            return path

    # Ninguno las tiene todas: devuelvo el más grande y que el chequeo de main() diga qué falta
    return max(candidates, key=getsize)


def extract_x_user_id(twid: str) -> str | None:
    """El twid viene como u%3D1234567890 (o u=1234567890 sin urlencodear)."""
    twid = twid.strip('"')
    for prefix in ("u%3D", "u="):
        if prefix in twid:
            return twid.split(prefix)[1].split("&")[0].strip('"')
    return None


def main():
    parser = ArgumentParser(description="Genera la sesión de X o de Instagram del bot desde las cookies de Firefox, sin pedidos.")
    parser.add_argument("platform", choices=PLATFORMS, help="x | instagram")
    parser.add_argument("username", help="la cuenta logueada en Firefox (X_USERNAME o IG_USERNAME)")
    parser.add_argument("-c", "--cookiefile", help="ruta a cookies.sqlite (por defecto la busca sola)")
    parser.add_argument("-o", "--output", help="dónde escribirla (por defecto donde la busca el bot)")
    args = parser.parse_args()
    platform = PLATFORMS[args.platform]

    cookiefile = args.cookiefile or get_cookiefile(platform)
    print(f"Leyendo cookies de {cookiefile}", file=sys.stderr)
    try:
        cookies = read_cookies(cookiefile, platform)
    except OperationalError as e:
        raise SystemExit(f"No pude leer las cookies: {e}")

    missing = [name for name in platform["required"] if not cookies.get(name)]
    if missing:
        raise SystemExit(f"Faltan estas cookies: {', '.join(missing)}. "
                         f"¿Estás logueado en {platform['site']} en Firefox con ese perfil?")

    if args.platform == "x":
        user_id = extract_x_user_id(cookies["twid"])
        if not user_id:
            raise SystemExit(f"No pude sacar el id numérico del twid: {cookies['twid']!r}")
        output = expanduser(args.output or f"~/.config/diablo-robot/x-session-{args.username}.json")
        content = (json.dumps({"username": args.username, "id": user_id, **cookies}) + "\n").encode()
    else:
        user_id = cookies["ds_user_id"]
        output = expanduser(args.output or f"~/.config/instaloader/session-{args.username}")
        # El formato de instaloader: un dict de cookies en pickle. Así sirve una sesión hecha con
        # cualquiera de los dos
        content = pickle.dumps(cookies)

    makedirs(dirname(output), exist_ok=True)
    with open(output, "wb") as f:
        f.write(content)
    # Con estas cookies cualquiera entra a la cuenta
    chmod(output, 0o600)
    print(f"Sesión de {args.platform} de @{args.username} (id {user_id}) guardada en {output}. "
          f"No se hizo ningún pedido: si no sirve, lo va a decir el bot.", file=sys.stderr)


if __name__ == "__main__":
    main()
