import asyncio

from mcstatus import JavaServer
from mcstatus.status_response import JavaStatusResponse

from config.settings import settings


async def get_status() -> JavaStatusResponse | None:
    """Consulta el server por Server List Ping. Devuelve None si está apagado o no responde."""
    server = JavaServer(settings.MINECRAFT_SERVER_HOST, settings.MINECRAFT_SERVER_PORT, timeout=5)
    try:
        return await server.async_status()
    except (OSError, asyncio.TimeoutError):
        return None
