#!/usr/bin/env python3
"""Arma la sesión de X del bot con las cookies de Firefox, sin automatizar un browser.

Es el equivalente de `instaloader --load-cookies firefox`: en vez de loguearse por código —que
es lo que dispara los captchas y los bloqueos— reusa la sesión que ya abriste a mano.

Uso:
    1. Entrá a https://x.com en Firefox con la cuenta descartable y dejá la sesión abierta.
    2. python3 tools/x_session.py --username lacuenta
    3. Si el scaneo estaba frenado: !twitter reanudar

Escribe ~/.config/diablo-robot/x-session-<usuario>.json, que es donde lo busca el bot. Hacen
falta tres cookies: auth_token, ct0 y twid (de donde sale el id numérico).
"""

import json
import sys
from argparse import ArgumentParser
from glob import glob
from os import chmod, makedirs
from os.path import dirname, expanduser, getsize
from platform import system
from sqlite3 import OperationalError, connect

# Las que firman los pedidos a la API de X: auth_token es la sesión, ct0 el token anti-CSRF
WANTED = ("auth_token", "ct0", "twid")


def read_cookies(cookiefile: str) -> dict:
    """Lee la base de Firefox en modo inmutable: no la toca aunque Firefox esté abierto."""
    conn = connect(f"file:{cookiefile}?immutable=1", uri=True)
    try:
        rows = conn.execute(
            "SELECT name, value FROM moz_cookies WHERE baseDomain IN ('x.com','twitter.com')"
        )
    except OperationalError:
        rows = conn.execute(
            "SELECT name, value FROM moz_cookies WHERE host LIKE '%x.com' OR host LIKE '%twitter.com'"
        )
    return {name: value for name, value in rows if name in WANTED}


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


def get_cookiefile() -> str:
    """Elijo el perfil que realmente tenga la sesión de X, no el primero que aparezca."""
    candidates = candidate_cookiefiles()
    if not candidates:
        raise SystemExit("No encontré cookies.sqlite de Firefox. Pasalo con -c COOKIEFILE.")

    for path in sorted(candidates, key=getsize, reverse=True):
        try:
            if len(read_cookies(path)) == len(WANTED):
                return path
        except OperationalError:
            continue

    # Ninguno las tiene todas: devuelvo el más grande y que el chequeo de main() diga qué falta
    return max(candidates, key=getsize)


def extract_user_id(twid: str) -> str | None:
    """El twid viene como u%3D1234567890 (o u=1234567890 sin urlencodear)."""
    twid = twid.strip('"')
    for prefix in ("u%3D", "u="):
        if prefix in twid:
            return twid.split(prefix)[1].split("&")[0].strip('"')
    return None


def main():
    parser = ArgumentParser(description="Genera la sesión de X del bot desde las cookies de Firefox.")
    parser.add_argument("-c", "--cookiefile", help="ruta a cookies.sqlite (por defecto la busca sola)")
    parser.add_argument("-u", "--username", required=True, help="la cuenta de X logueada en Firefox (X_USERNAME)")
    parser.add_argument("-o", "--output", help="dónde escribirla (por defecto donde la busca el bot)")
    args = parser.parse_args()

    cookiefile = args.cookiefile or get_cookiefile()
    print(f"Leyendo cookies de {cookiefile}", file=sys.stderr)

    try:
        cookies = read_cookies(cookiefile)
    except OperationalError as e:
        raise SystemExit(f"No pude leer las cookies: {e}")

    faltan = [c for c in WANTED if c not in cookies]
    if faltan:
        raise SystemExit(
            f"Faltan estas cookies: {', '.join(faltan)}. "
            "¿Estás logueado en https://x.com en Firefox con ese perfil?"
        )

    user_id = extract_user_id(cookies["twid"])
    if not user_id:
        raise SystemExit(f"No pude sacar el id numérico del twid: {cookies['twid']!r}")

    session = {
        "username": args.username,
        "id": user_id,
        "auth_token": cookies["auth_token"],
        "ct0": cookies["ct0"],
        "twid": cookies["twid"],
    }
    output = expanduser(args.output or f"~/.config/diablo-robot/x-session-{args.username}.json")
    makedirs(dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        # En una sola línea, porque tools/probe_feeds.py lee un JSON por línea
        f.write(json.dumps(session) + "\n")
    # Con estas cookies cualquiera entra a la cuenta
    chmod(output, 0o600)
    print(f"Sesión de @{args.username} (id {user_id}) guardada en {output}.", file=sys.stderr)


if __name__ == "__main__":
    main()
