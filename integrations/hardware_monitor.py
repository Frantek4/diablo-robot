import asyncio
import time

import aiohttp

from config.settings import settings
from models.hardware_snapshot import HardwareSnapshot, VpnLink

PING_SAMPLES = 4
PING_TIMEOUT_SECONDS = 3


def _base_url() -> str:
    return f"http://{settings.HARDWARE_MONITOR_HOST}:{settings.HARDWARE_MONITOR_PORT}"


def _headers() -> dict:
    return {"X-Auth-Token": settings.HARDWARE_MONITOR_TOKEN}


async def get_status() -> HardwareSnapshot | None:
    """Consulta al agente de hardware en la PC de Minecraft. Devuelve None si está caída o no responde."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_base_url()}/metrics", headers=_headers(), timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return HardwareSnapshot.from_dict(data)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
        return None


async def measure_vpn_link(samples: int = PING_SAMPLES) -> VpnLink:
    """Mide latencia, jitter y pérdida del túnel de WireGuard pegándole al endpoint liviano /ping del agente."""
    url = f"{_base_url()}/ping"
    latencies = []

    try:
        async with aiohttp.ClientSession(headers=_headers()) as session:
            for _ in range(samples):
                start = time.perf_counter()
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT_SECONDS)) as response:
                        await response.read()
                        if response.status == 200:
                            latencies.append((time.perf_counter() - start) * 1000)
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    continue
    except Exception:
        return VpnLink()

    if not latencies:
        return VpnLink()

    average = sum(latencies) / len(latencies)
    jitter = sum(abs(latency - average) for latency in latencies) / len(latencies)
    return VpnLink(
        latency_ms=round(average, 1),
        jitter_ms=round(jitter, 1),
        loss_percent=round(100 * (samples - len(latencies)) / samples, 1),
    )
