import asyncio
import random
from datetime import datetime, timedelta

from discord.ext import commands, tasks

from config.settings import settings
from integrations import nitter
from integrations.twitter import InstanceDown, Twitter
from models.social_media import SocialMedia
from utils.date_format import format_time

# No tiene sentido machacar de madrugada: nadie tuitea y el rate limit de X se paga igual
_ACTIVE_HOURS = set(range(0, 2)) | set(range(8, 24))
# Cada cuánto me fijo si me toca leer. La vuelta de verdad no cae en punto: la agendo yo con jitter,
# porque pedir clavado en el mismo minuto de cada hora es el patrón más fácil de marcar que hay
_TICK_MINUTES = 5
_RUN_EVERY_MINUTES = (60, 150)
# Cuánto espero después de cada falla seguida de la instancia. Insistir contra una sesión que X está
# castigando no trae tweets: sólo hunde más la cuenta y repite el mismo aviso
_BACKOFF_HOURS = (1, 2, 4, 6)
# Si el presupuesto viene en cero mucho rato pero no falló nada, pruebo con una cuenta sola: el flag
# `limited` de Nitter se limpia recién cuando le entra un pedido, y no quiero quedarme trabado
_MAX_QUIET = timedelta(hours=2)
# tasks.loop corre la primera vuelta apenas arranca. La gracia le da tiempo al bot a terminar de
# levantarse; que un reinicio no compre una lectura extra lo resuelve la primera vuelta, que se
# agenda como cualquier otra: si reinicio cinco veces seguidas, el scaneo sigue yendo al mismo ritmo
_STARTUP_GRACE_SECONDS = (60, 180)


class TwitterCheckScheduler(commands.Cog):
    """Lee Twitter al ritmo que le permita el rate limit, no al que diga el reloj.

    Antes de cada vuelta le pregunta a la instancia cuánto margen le queda (`/.sessions`, que es
    local y no llama a X) y de ahí sale cuántas cuentas lee: si sobra presupuesto lee unas pocas, si
    está justo lee una, y si no hay margen no lee ninguna y no gasta un pedido que ya sabe que va a
    rebotar. Los tweets no son urgentes; la cuenta de X es lo único que no se puede reponer.
    """

    def __init__(self, bot):
        self.bot = bot
        self.twitter = Twitter(bot)
        self._cursor = 0
        self._last_read_at = datetime.now(settings.TIMEZONE)
        # La primera lectura se agenda igual que las demás: arrancar no es motivo para leer
        self._next_run_at = self._last_read_at + timedelta(minutes=random.uniform(*_RUN_EVERY_MINUTES))
        self._backoff_step = 0
        self._last_failure = None
        self._has_read = False

    def cog_unload(self):
        self.twitter_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.twitter_scheduled_job.is_running():
            self.twitter_scheduled_job.start()

    @tasks.loop(minutes=_TICK_MINUTES)
    async def twitter_scheduled_job(self):
        now = datetime.now(settings.TIMEZONE)
        if now.hour not in _ACTIVE_HOURS:
            return
        if now < self._next_run_at:
            return

        influencers = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)
        if not influencers:
            return

        pool = await nitter.get_pool()
        feeds = self._feeds_to_read(pool, now)
        if not feeds:
            # Callado a propósito: no leer porque no hay margen es el bot portándose bien, no una falla
            self._schedule_next(pool.resumes_at if pool else None, now)
            return

        try:
            consumed = await self.twitter.check_rss_notifications(self._next_batch(influencers, feeds))
        except InstanceDown as e:
            await self._handle_instance_down(e, len(influencers))
            return
        except Exception as e:
            self._schedule_next(None, datetime.now(settings.TIMEZONE))
            await self.bot.messager.log(f"No pude escanear Twitter: {e}", level="ERROR", exc=e)
            return

        recovered = self._backoff_step > 0
        self._advance_cursor(consumed, len(influencers))
        self._backoff_step = 0
        self._last_failure = None
        self._last_read_at = datetime.now(settings.TIMEZONE)
        self._has_read = True
        self._schedule_next(None, self._last_read_at)

        if recovered:
            await self.bot.messager.log("Nitter volvió a servirme feeds, retomo el scaneo de Twitter.")

    @twitter_scheduled_job.before_loop
    async def before_twitter_scheduled_job(self):
        await asyncio.sleep(random.uniform(*_STARTUP_GRACE_SECONDS))

    def status_lines(self) -> list[str]:
        """Cómo viene el scaneo, para poder mirarlo desde Discord sin entrar al Pi."""
        lines = [
            f"Última lectura: {format_time(self._last_read_at)}" if self._has_read else "Todavía no leí nada desde que arranqué",
            f"Próxima: {format_time(self._next_run_at)}",
        ]
        if self._backoff_step:
            lines.append(f"En pausa por falla ({self._last_failure}), paso {self._backoff_step} de {len(_BACKOFF_HOURS)}")
        return lines

    def _feeds_to_read(self, pool, now: datetime) -> int:
        feeds = nitter.budget(pool)
        if feeds or self._backoff_step:
            return feeds
        # Sin margen pero sin falla reciente: si hace rato que no leo nada, tanteo con una sola cuenta
        return 1 if now - self._last_read_at > _MAX_QUIET else 0

    def _schedule_next(self, resumes_at: datetime | None, now: datetime):
        """Si sé cuándo se repone la ventana arranco un rato después, no en el segundo exacto: pegarle
        al instante en que se libera el límite es, otra vez, comportarse como un bot."""
        if resumes_at and resumes_at > now:
            self._next_run_at = resumes_at + timedelta(minutes=random.uniform(1, 5))
        else:
            self._next_run_at = now + timedelta(minutes=random.uniform(*_RUN_EVERY_MINUTES))

    async def _handle_instance_down(self, error: InstanceDown, total: int):
        now = datetime.now(settings.TIMEZONE)
        self._advance_cursor(error.consumed, total)
        self._backoff_step = min(self._backoff_step + 1, len(_BACKOFF_HOURS))
        self._last_failure = error.reason

        hours = _BACKOFF_HOURS[self._backoff_step - 1] * random.uniform(0.9, 1.2)
        retry_at = now + timedelta(hours=hours)

        # El estado de la instancia va en el aviso siempre, porque es lo que hace que el aviso sirva
        # para algo; pero estirar la espera hasta que se reponga la ventana sólo tiene sentido si lo
        # que pasó fue un rate limit: si la sesión se quemó, esperar el reset no arregla nada
        pool = await nitter.get_pool()
        if error.rate_limited and pool and pool.resumes_at and pool.resumes_at > retry_at:
            retry_at = pool.resumes_at
        self._next_run_at = retry_at

        await self.bot.messager.log(await self._failure_report(error, pool, retry_at), level="ERROR")

    async def _failure_report(self, error: InstanceDown, pool, retry_at: datetime) -> str:
        """El HTTP que devuelve Nitter no dice nada: el mismo cartel sirve para un challenge de
        Cloudflare, una cuenta bloqueada, el rate limit de verdad o un corte de red. Así que el aviso
        no afirma una causa: trae lo que el contenedor escribió recién y deja que se vea sola."""
        parts = [f"Mi instancia de Nitter no está sirviendo feeds ({error.reason})."]

        failures = await nitter.recent_failures()
        if failures:
            parts.append("Nitter escupió esto: " + " ".join(f"`{line}`" for line in failures))
        elif failures is None:
            parts.append("No pude leerle los logs al contenedor (¿tengo `docker` a mano en el Pi?).")
        else:
            parts.append("En sus logs no dijo nada, así que la falla no llegó a la API de X.")

        if error.rate_limited and pool and pool.feeds:
            parts.append("Ojo que le queda margen de sobra, así que esto **no** es límite de X: "
                         "apuntá a la sesión (¿se quemó?) o a la red del Pi.")
        if pool:
            parts.append(f"Sesiones: {pool.detail}.")

        parts.append(f"Dejo Twitter tranquilo hasta las {format_time(retry_at)} para no seguir "
                     f"golpeando la sesión.")
        return " ".join(parts)

    def _next_batch(self, influencers: list, size: int) -> list:
        """La ventana que toca esta vuelta; el cursor avanza después, y sólo por lo que se leyó."""
        self._cursor %= len(influencers)
        batch = (influencers + influencers)[self._cursor:self._cursor + size]
        return batch[:len(influencers)]

    def _advance_cursor(self, consumed: int, total: int):
        if total:
            self._cursor = (self._cursor + consumed) % total


async def setup(bot):
    await bot.add_cog(TwitterCheckScheduler(bot))
