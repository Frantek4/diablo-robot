import asyncio
import random
from datetime import datetime, timedelta, timezone

from discord.ext import commands, tasks

from config.settings import settings
from integrations.instagram import AccountFlagged, Instagram, Throttled
from models.influencer import AttentionLevel
from models.social_media import SocialMedia
from utils.date_format import format_datetime, format_time

# Horario de gente despierta. De madrugada nadie postea y una lectura a las 4am es, ella sola, una
# firma de que del otro lado no hay nadie
_ACTIVE_HOURS = set(range(9, 24)) | {0}
# El loop tiquea seguido pero la vuelta de verdad se agenda sola: pedir clavado en el mismo minuto
# de cada hora es el patrón más fácil de marcar que hay
_TICK_MINUTES = 5
_RUN_EVERY_MINUTES = (75, 180)
# El presupuesto de la vuelta, repartido por nivel de atención. Instagram no publica ningún contador
# —a diferencia de Nitter, que expone los headers de X—, así que el límite no se consulta: se elige,
# y se elige chico. Cada cuenta leída es exactamente un pedido, así que esto son 4 pedidos por vuelta
_HIGH_PER_RUN = 3
_LOW_PER_RUN = 1
# Cuánto se espera después de cada falla seguida. Instagram no dice cuándo se repone nada, así que
# el reloj es a ciegas y por eso arranca largo
_BACKOFF_HOURS = (2, 6, 12, 24)
_STARTUP_GRACE_SECONDS = (60, 180)


class InstagramCheckScheduler(commands.Cog):
    """Lee Instagram poco, salteado y sin insistir nunca.

    Dos cosas lo separan del scaneo de Twitter. Una: acá no hay presupuesto que consultar, porque
    Instagram nunca dice cuánto margen queda — sólo avisa cuando ya marcó la cuenta, y para ese
    entonces el daño está hecho. La otra: el estado va a Mongo, porque el único error que importa
    (que Instagram acuse a la cuenta) no se puede olvidar en un reinicio. Un bot que se reinicia y
    vuelve a leer como si nada después de un checkpoint es exactamente la forma de perder la cuenta.
    """

    def __init__(self, bot):
        self.bot = bot
        self.instagram = Instagram(bot)
        self.dao = bot.instagram_state_dao
        # El recordatorio de que el scaneo está frenado se da una vez por arranque del bot: el aviso
        # del momento en que se frenó ya salió, y repetirlo cada cinco minutos no agrega nada
        self._reminded = False

    def cog_unload(self):
        self.instagram_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.instagram_scheduled_job.is_running():
            self.instagram_scheduled_job.start()

    @tasks.loop(minutes=_TICK_MINUTES)
    async def instagram_scheduled_job(self):
        state = self.dao.get()

        if state.get("blocked"):
            await self._remind_blocked(state)
            return

        now = datetime.now(settings.TIMEZONE)
        if now.hour not in _ACTIVE_HOURS:
            return

        next_run = self._as_local(state.get("next_run_at"))
        if next_run is None:
            # Primera vuelta de la vida: se agenda como cualquier otra. Arrancar el bot no es motivo
            # para leer, así que reiniciar cinco veces no compra cinco lecturas
            self._schedule_next(now)
            return
        if now < next_run:
            return

        high, low = self._rings()
        if not high and not low:
            self._schedule_next(now)
            return

        batch = self._next_batch(high, low, state)

        try:
            consumed = await self.instagram.check_notifications(batch)
        except AccountFlagged as e:
            await self._handle_flagged(e, high, low, state, now)
            return
        except Throttled as e:
            await self._handle_throttled(e, high, low, state, now)
            return
        except Exception as e:
            self._schedule_next(datetime.now(settings.TIMEZONE))
            await self.bot.messager.log(f"No pude escanear Instagram: {e}", level="ERROR", exc=e)
            return

        recovered = state.get("backoff_step", 0) > 0
        done = datetime.now(settings.TIMEZONE)
        self._advance(high, low, state, consumed)
        self.dao.save(backoff_step=0, last_failure=None, last_read_at=done)
        self._schedule_next(done)

        if recovered:
            await self.bot.messager.log("Instagram volvió a contestarme bien, retomo el scaneo.")

    @instagram_scheduled_job.before_loop
    async def before_instagram_scheduled_job(self):
        await asyncio.sleep(random.uniform(*_STARTUP_GRACE_SECONDS))

    def status_lines(self) -> list[str]:
        """Cómo viene el scaneo, para mirarlo desde Discord sin entrar al Pi."""
        state = self.dao.get()
        lines = []

        if state.get("blocked"):
            when = self._as_local(state.get("blocked_at"))
            lines.append(f"🛑 **Frenado desde {format_datetime(when) if when else '?'}**: "
                         f"{state.get('blocked_reason', 'sin motivo guardado')}")
            lines.append(f"No vuelvo a pedirle nada a Instagram hasta que corras "
                         f"`{settings.PREFIX}instagram reanudar`.")
            return lines

        last_read = self._as_local(state.get("last_read_at"))
        next_run = self._as_local(state.get("next_run_at"))
        lines.append(f"Última lectura: {format_datetime(last_read)}" if last_read
                     else "Todavía no leí nada")
        lines.append(f"Próxima: {format_time(next_run)}" if next_run else "Próxima: sin agendar")

        step = state.get("backoff_step", 0)
        if step:
            lines.append(f"En pausa por falla ({state.get('last_failure')}), "
                         f"paso {step} de {len(_BACKOFF_HOURS)}")

        high, low = self._rings()
        if high or low:
            names = ", ".join(f"@{i['name']}" for i in self._next_batch(high, low, state))
            lines.append(f"{len(high)} cuenta(s) de atención alta y {len(low)} baja; "
                         f"{_HIGH_PER_RUN}+{_LOW_PER_RUN} por vuelta. Le tocan: {names}")
        return lines

    def _rings(self) -> tuple[list, list]:
        """Dos ruedas, una por nivel de atención, cada una con su cursor. Dos ruedas con cupo fijo
        dicen lo mismo que una sola rueda con las cuentas importantes repetidas, y no hay que
        andar descontando repetidos para saber cuánto avanzó el cursor."""
        return (
            self.bot.influencer_dao.get_by_platform_and_attention(
                SocialMedia.INSTAGRAM, AttentionLevel.HIGH),
            self.bot.influencer_dao.get_by_platform_and_attention(
                SocialMedia.INSTAGRAM, AttentionLevel.LOW),
        )

    def _next_batch(self, high: list, low: list, state: dict) -> list:
        """Las cuentas que toca leer esta vuelta: primero las de atención alta y después las bajas,
        que es también el orden en que se consumen si la vuelta se corta a la mitad."""
        return (self._slice(high, state.get("high_cursor", 0), _HIGH_PER_RUN)
                + self._slice(low, state.get("low_cursor", 0), _LOW_PER_RUN))

    @staticmethod
    def _slice(ring: list, cursor: int, size: int) -> list:
        if not ring:
            return []
        cursor %= len(ring)
        return (ring + ring)[cursor:cursor + min(size, len(ring))]

    def _advance(self, high: list, low: list, state: dict, consumed: int):
        """El cursor avanza sólo por lo que se leyó de verdad. Una vuelta que murió en la segunda
        cuenta retoma en la tercera en vez de saltearla hasta la próxima vuelta entera."""
        from_high = min(consumed, len(self._slice(high, state.get("high_cursor", 0), _HIGH_PER_RUN)))
        from_low = consumed - from_high
        if high:
            self.dao.save(high_cursor=(state.get("high_cursor", 0) + from_high) % len(high))
        if low:
            self.dao.save(low_cursor=(state.get("low_cursor", 0) + from_low) % len(low))

    def _schedule_next(self, now: datetime):
        self.dao.save(next_run_at=now + timedelta(minutes=random.uniform(*_RUN_EVERY_MINUTES)))

    def _as_local(self, value) -> datetime | None:
        """Mongo devuelve los datetime en UTC y sin tzinfo; el resto del bot piensa en hora local."""
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(settings.TIMEZONE)

    async def _handle_flagged(self, error: AccountFlagged, high: list, low: list, state: dict, now: datetime):
        """Se apaga el scaneo y se queda apagado. A propósito no hay reintento automático: si
        Instagram puso un checkpoint, lo único que arregla algo es que un humano entre a la cuenta y
        lo resuelva, y cada pedido que mandemos mientras tanto confirma lo que ya sospecha."""
        self._advance(high, low, state, error.consumed)
        self.dao.block(error.reason, now)
        self._reminded = True
        await self.bot.messager.log(
            f"**Instagram marcó la cuenta y dejo de leer.** Dijo: `{error.reason[:400]}`. "
            f"Esto no se arregla esperando: entrá a Instagram con @{settings.IG_USERNAME} desde el "
            f"celular, resolvé lo que te pida, rehacé la sesión "
            f"(`instaloader --load-cookies firefox --sessionfile ~/.config/instaloader/session-{settings.IG_USERNAME}`) "
            f"y recién ahí corré `{settings.PREFIX}instagram reanudar`. Hasta entonces no le pido "
            f"nada más.",
            level="CRITICAL",
        )

    async def _handle_throttled(self, error: Throttled, high: list, low: list, state: dict, now: datetime):
        """Instagram frenó pero no acusó a nadie. Se espera cada vez más, y se avisa una sola vez
        por episodio: repetir el mismo cartel cada dos horas no agrega información."""
        step = min(state.get("backoff_step", 0) + 1, len(_BACKOFF_HOURS))
        hours = _BACKOFF_HOURS[step - 1] * random.uniform(0.9, 1.2)
        retry_at = now + timedelta(hours=hours)

        self._advance(high, low, state, error.consumed)
        self.dao.save(backoff_step=step, last_failure=error.reason, next_run_at=retry_at)
        self.dao.log_event("throttled", error.reason, now)

        if step == 1:
            await self.bot.messager.log(
                f"Instagram me frenó (`{error.reason[:300]}`), pero sin acusar a la cuenta. "
                f"Dejo de pedirle hasta las {format_time(retry_at)} y después sigo. "
                f"Si esto se repite, mirá `{settings.PREFIX}instagram`.",
                level="WARNING",
            )

    async def _remind_blocked(self, state: dict):
        """El aviso del momento en que se frenó ya salió; esto es para que el bot no se quede
        callado si lo reiniciaron después y nadie se acuerda de por qué no hay posts."""
        if self._reminded:
            return
        self._reminded = True
        when = self._as_local(state.get("blocked_at"))
        await self.bot.messager.log(
            f"Sigo sin leer Instagram: quedó frenado el {format_datetime(when) if when else '?'} "
            f"porque {state.get('blocked_reason', 'Instagram marcó la cuenta')}. "
            f"Se reanuda con `{settings.PREFIX}instagram reanudar`.",
            level="WARNING",
        )


async def setup(bot):
    await bot.add_cog(InstagramCheckScheduler(bot))
