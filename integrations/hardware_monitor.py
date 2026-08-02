import asyncio

import aiohttp

from config.settings import settings
from models.hardware_snapshot import HardwareSnapshot


async def get_status() -> HardwareSnapshot | None:
    """Consulta al agente de hardware en la PC de Minecraft. Devuelve None si está caída o no responde."""
    url = f"http://{settings.HARDWARE_MONITOR_HOST}:{settings.HARDWARE_MONITOR_PORT}/metrics"
    headers = {"X-Auth-Token": settings.HARDWARE_MONITOR_TOKEN}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return HardwareSnapshot.from_dict(data)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
        return None
