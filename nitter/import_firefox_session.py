#!/usr/bin/env python3
"""Arma sessions.jsonl para Nitter con las cookies de Firefox, sin automatizar un browser.

Es el equivalente de 615_import_firefox_session.py de instaloader: en vez de loguearse por
código —que es lo que dispara los captchas y los bloqueos— reusa la sesión que ya abriste a
mano en el navegador.

Uso:
    1. Entrá a https://x.com en Firefox con la cuenta descartable y dejá la sesión abierta.
    2. python3 import_firefox_session.py --username lacuenta >> sessions.jsonl
    3. Reiniciá el contenedor: docker compose restart nitter

Nitter necesita tres cookies: auth_token, ct0 y twid (de donde sale el id numérico).
"""

import json
import sys
from argparse import ArgumentParser
from glob import glob
from os.path import expanduser
from platform import system
from sqlite3 import OperationalError, connect

# Las que Nitter realmente usa para firmar los requests (ver src/apiutils.nim)
WANTED = ("auth_token", "ct0", "twid")


def get_cookiefile() -> str:
    default = {
        "Windows": "~/AppData/Roaming/Mozilla/Firefox/Profiles/*/cookies.sqlite",
        "Darwin": "~/Library/Application Support/Firefox/Profiles/*/cookies.sqlite",
    }.get(system(), "~/.mozilla/firefox/*/cookies.sqlite")
    matches = glob(expanduser(default))
    if not matches:
        raise SystemExit("No encontré cookies.sqlite de Firefox. Pasalo con -c COOKIEFILE.")
    # El perfil con más cookies suele ser el que se usa de verdad
    return max(matches, key=lambda f: len(f))


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


def extract_user_id(twid: str) -> str | None:
    """El twid viene como u%3D1234567890 (o u=1234567890 sin urlencodear)."""
    twid = twid.strip('"')
    for prefix in ("u%3D", "u="):
        if prefix in twid:
            return twid.split(prefix)[1].split("&")[0].strip('"')
    return None


def main():
    parser = ArgumentParser(description="Genera una línea de sessions.jsonl desde las cookies de Firefox.")
    parser.add_argument("-c", "--cookiefile", help="ruta a cookies.sqlite (por defecto la busca sola)")
    parser.add_argument("-u", "--username", required=True, help="la cuenta de X logueada en Firefox")
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
        "kind": "cookie",
        "username": args.username,
        "id": user_id,
        "auth_token": cookies["auth_token"],
        "ct0": cookies["ct0"],
    }
    print(json.dumps(session))
    print(f"Sesión de @{args.username} (id {user_id}) lista.", file=sys.stderr)


if __name__ == "__main__":
    main()
