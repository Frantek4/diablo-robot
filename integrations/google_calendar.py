"""Espejo de los partidos en un Google Calendar.

El calendario lo creás vos en tu cuenta de Google y le das permiso de escritura a una
service account; el bot escribe con esas credenciales, que salen de
GOOGLE_SERVICE_ACCOUNT_FILE. El id de cada evento sale del match_id de Promiedos,
así que sincronizar es idempotente: el mismo partido siempre pisa el mismo
evento del calendario, sin necesidad de guardar nada en Mongo.
"""

import asyncio
import hashlib
from datetime import datetime
from urllib.parse import quote

import aiohttp
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from config.settings import settings

API_URL = "https://www.googleapis.com/calendar/v3/calendars"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIMEOUT = aiohttp.ClientTimeout(total=10)
# "Tomate", el más rojo de la paleta de Google. Va en el evento y no en el calendario,
# así lo ve igual todo el mundo: el color del calendario lo elige cada suscriptor.
EVENT_COLOR_TOMATO = "11"

_credentials = None


class CalendarError(Exception):
    """Google contestó cualquier cosa."""


def is_enabled() -> bool:
    """Sin calendario o sin credenciales el espejo simplemente no corre."""
    return bool(settings.GOOGLE_CALENDAR_ID and settings.GOOGLE_SERVICE_ACCOUNT_FILE)


def event_id(match_id: str) -> str:
    """Google solo acepta ids en base32hex (a-v y 0-9): el sha1 del match_id entra justo."""
    return "diablo" + hashlib.sha1(str(match_id).encode()).hexdigest()


def _fresh_token() -> str:
    """google-auth es sincrónico, así que esto siempre se llama desde un thread aparte."""
    global _credentials
    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
    if not _credentials.valid:
        _credentials.refresh(Request())
    return _credentials.token


async def _auth_headers() -> dict:
    token = await asyncio.to_thread(_fresh_token)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _calendar_path() -> str:
    return f"{API_URL}/{quote(settings.GOOGLE_CALENDAR_ID, safe='')}/events"


def ical_url() -> str:
    """El .ics público del calendario. Sirve para Apple Calendar, Outlook y cualquier otro."""
    return f"https://calendar.google.com/calendar/ical/{quote(settings.GOOGLE_CALENDAR_ID, safe='')}/public/basic.ics"


def subscribe_url() -> str:
    """Link de un click para suscribirse desde Google Calendar: abre el diálogo de
    '¿querés agregar este calendario?' con la cuenta que el tipo ya tenga logueada."""
    return f"https://calendar.google.com/calendar/render?cid={quote(ical_url().replace('https://', 'webcal://'), safe='')}"


async def upsert_event(
    match_id: str,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
    location: str = None,
) -> str:
    """Crea el evento del partido o pisa el que ya estaba. Devuelve el link al evento."""
    identifier = event_id(match_id)
    body = {
        "id": identifier,
        "summary": summary,
        "description": description,
        "location": location or "",
        "colorId": EVENT_COLOR_TOMATO,
        "start": {"dateTime": start.isoformat(), "timeZone": str(settings.TIMEZONE)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(settings.TIMEZONE)},
        "reminders": {"useDefault": True},
    }

    headers = await _auth_headers()
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=TIMEOUT) as session:
            # Piso el evento primero: es el caso normal, porque el fixture se rechequea cada hora.
            async with session.put(f"{_calendar_path()}/{identifier}", json=body) as response:
                if response.status == 200:
                    return (await response.json()).get("htmlLink", "")
                if response.status != 404:
                    raise CalendarError(f"HTTP {response.status}: {(await response.text())[:300]}")

            async with session.post(_calendar_path(), json=body) as response:
                if response.status in (200, 201):
                    return (await response.json()).get("htmlLink", "")
                raise CalendarError(f"HTTP {response.status}: {(await response.text())[:300]}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CalendarError(f"No llegué a Google Calendar: {e}") from e
