import asyncio
from datetime import datetime, timedelta, timezone

import aiohttp
from discord.ext import commands, tasks

from config.settings import settings
from integrations import nitter_mirrors

# Cada cuánto vuelvo a bajar la lista de instancias del wiki de Nitter
_CATALOG_TTL_HOURS = 12
# A los que andan casi no hace falta probarlos: el scaneo de Twitter ya los usa y actualiza su estado
_ONLINE_RECHECK_HOURS = 6
# A los caídos los espacio cada vez más, por fallas seguidas: media hora, una, dos... hasta doce
_RETRY_BACKOFF_MINUTES = [30, 60, 120, 240, 480, 720]
# Respiro entre mirror y mirror para no salir a golpear las ocho instancias de una
_PROBE_DELAY = 2


class NitterMirrorCheckScheduler(commands.Cog):
    """Mantiene el repositorio de mirrors de Nitter: los descubre, los prueba y guarda si andan."""

    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.nitter_mirror_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.nitter_mirror_scheduled_job.is_running():
            self.nitter_mirror_scheduled_job.start()

    @tasks.loop(minutes=30)
    async def nitter_mirror_scheduled_job(self):
        await self.check_mirrors()

    async def check_mirrors(self, force: bool = False):
        """Actualiza el catálogo y el estado de cada mirror. force ignora el chequeo reciente (lo usa !nitter)."""
        try:
            async with aiohttp.ClientSession() as session:
                await self._refresh_catalog(session)
                await self._probe_due(session, force=force)
        except Exception as e:
            await self.bot.messager.log(f"No pude chequear los mirrors de Nitter: {e}", level="ERROR", exc=e)
            return

        await nitter_mirrors.report_pool_state(self.bot)

    async def _refresh_catalog(self, session):
        """Siembra el repositorio la primera vez y después lo va completando con lo que publica el wiki."""
        dao = self.bot.nitter_mirror_dao
        if not dao.get_all():
            await nitter_mirrors.seed_catalog(self.bot)

        if not self._catalog_is_stale(dao.get_state()):
            return

        try:
            added = await nitter_mirrors.refresh_catalog(self.bot, session)
        except Exception as e:
            await self.bot.messager.log(
                f"No pude bajar la lista de instancias de Nitter: {e}. Sigo con los mirrors que ya tenía.",
                level="WARNING",
            )
            return

        dao.save_state(catalog_updated_at=datetime.now(settings.TIMEZONE))
        if added:
            hosts = ", ".join(url.split("//")[-1] for url in added)
            await self.bot.messager.log(f"Sumé {len(added)} mirror(s) nuevo(s) de Nitter al repositorio: {hosts}.")

    async def _probe_due(self, session, force: bool = False):
        """Le pide a cada mirror el feed de una cuenta de verdad y guarda si sirve o por qué no."""
        account = nitter_mirrors.probe_account(self.bot)
        now = datetime.now(settings.TIMEZONE)
        checked = 0

        for mirror in self.bot.nitter_mirror_dao.get_ranked():
            if not force and not self._is_due(mirror, now):
                continue

            if checked:
                await asyncio.sleep(_PROBE_DELAY)

            is_online, reason, latency_ms = await nitter_mirrors.probe(session, mirror.url, account)
            self.bot.nitter_mirror_dao.save_result(
                mirror.url, is_online=is_online, reason=reason, latency_ms=latency_ms
            )
            checked += 1

    @staticmethod
    def _is_due(mirror, now: datetime) -> bool:
        """Cuánto espero antes de volver a probar un mirror: los que andan casi nunca, los caídos cada vez menos seguido."""
        if mirror.last_check is None:
            return True

        if mirror.is_online:
            return now - mirror.last_check >= timedelta(hours=_ONLINE_RECHECK_HOURS)

        step = min(max(mirror.consecutive_failures, 1), len(_RETRY_BACKOFF_MINUTES)) - 1
        return now - mirror.last_check >= timedelta(minutes=_RETRY_BACKOFF_MINUTES[step])

    @staticmethod
    def _catalog_is_stale(state: dict) -> bool:
        updated_at = state.get("catalog_updated_at")
        if not isinstance(updated_at, datetime):
            return True
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return datetime.now(settings.TIMEZONE) - updated_at > timedelta(hours=_CATALOG_TTL_HOURS)


async def setup(bot):
    await bot.add_cog(NitterMirrorCheckScheduler(bot))
