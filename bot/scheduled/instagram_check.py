import asyncio
import random
from datetime import datetime, timedelta, timezone

from discord.ext import commands, tasks

from config.settings import settings
from integrations.instagram import Instagram
from integrations.instagram_api import session_path
from integrations.social_errors import AccountFlagged, ClientOutdated, Throttled, Unreachable
from models.social_media import SocialMedia
from utils.date_format import format_datetime, format_time

# Horario de gente despierta: de 08:00 a 23:00. Una lectura a las 4am es, ella sola, una firma de
# que del otro lado no hay nadie
_ACTIVE_HOURS = set(range(8, 23))
# El loop tiquea seguido pero la vuelta de verdad se agenda sola, con jitter: pedir clavado en el
# mismo minuto de cada hora es el patrón más fácil de marcar que hay
_TICK_MINUTES = 5
_RUN_EVERY_MINUTES = (45, 145)
# Cuánto se espera después de cada falla seguida. Instagram no dice cuándo se repone nada, así que
# el reloj es a ciegas y por eso arranca largo
_BACKOFF_HOURS = (2, 6, 12, 24)
_STARTUP_GRACE_SECONDS = (60, 180)


class InstagramCheckScheduler(commands.Cog):
    """Mira la home de Instagram una vez por vuelta y postea lo de las cuentas de la tabla.

    Mismo diseño que Twitter: una vuelta es un solo pedido —abrir la app—, no una ronda de visitas
    a perfiles. A diferencia de X, Instagram no publica ningún contador: no dice cuánto margen
    queda, sólo avisa cuando ya marcó la cuenta. El estado va a Mongo, porque un bot que se
    reinicia y vuelve a leer como si nada después de un checkpoint es la forma de perder la cuenta.
    """

    def __init__(self, bot):
        self.bot = bot
        self.instagram = Instagram(bot)
        self.dao = bot.instagram_state_dao
        # El recordatorio de que el scaneo está frenado se da una vez por arranque del bot
        self._reminded = False

    def cog_unload(self):
        self.instagram_scheduled_job.cancel()

    def start_scheduled_job(self):
        """Lo llama `on_ready()` y también `!instagram reanudar`, así que aguanta el loop apagado,
        corriendo, o recién cancelado y todavía sin terminar de morir."""
        if self.instagram_scheduled_job.is_running():
            self.instagram_scheduled_job.restart()
        else:
            self.instagram_scheduled_job.start()

    @tasks.loop(minutes=_TICK_MINUTES)
    async def instagram_scheduled_job(self):
        state = self.dao.get()

        if state.get("blocked"):
            # Esta vuelta existe sólo para que el aviso salga después de un reinicio del bot
            await self._remind_blocked(state)
            self.instagram_scheduled_job.stop()
            return

        now = datetime.now(settings.TIMEZONE)
        if now.hour not in _ACTIVE_HOURS:
            return

        next_run = self._as_local(state.get("next_run_at"))
        if next_run is None:
            # Primera vuelta de la vida: se agenda como cualquier otra. Reiniciar el bot cinco veces
            # no compra cinco lecturas
            self._schedule_next(now)
            return
        if now < next_run:
            return

        try:
            seen = await self.instagram.read_home()
        except AccountFlagged as e:
            await self._handle_flagged(e, now)
            return
        except ClientOutdated as e:
            await self._handle_outdated(e, now)
            return
        except Throttled as e:
            await self._handle_throttled(e, state, now)
            return
        except Unreachable as e:
            self._schedule_next(now)
            await self.bot.messager.log(
                f"No llegué a Instagram ({e.reason}). Eso es la red del Pi, no un freno: el pedido no "
                f"existió para ellos, así que sigo con el ritmo de siempre.", level="WARNING")
            return
        except Exception as e:
            self._schedule_next(datetime.now(settings.TIMEZONE))
            await self.bot.messager.log(f"No pude escanear Instagram: {e}", level="ERROR", exc=e)
            return

        recovered = state.get("backoff_step", 0) > 0
        done = datetime.now(settings.TIMEZONE)
        self.dao.save(backoff_step=0, last_failure=None, last_read_at=done, last_seen=seen)
        self._schedule_next(done)

        if recovered:
            await self.bot.messager.log("Instagram volvió a contestarme bien, retomo el scaneo.")

    @instagram_scheduled_job.before_loop
    async def before_instagram_scheduled_job(self):
        await asyncio.sleep(random.uniform(*_STARTUP_GRACE_SECONDS))

    def status_lines(self) -> list[str]:
        """Cómo viene el scaneo, para mirarlo desde Discord sin entrar al Pi."""
        state = self.dao.get()
        if state.get("blocked"):
            when = self._as_local(state.get("blocked_at"))
            return [
                f"🛑 **Frenado desde {format_datetime(when) if when else '?'}**: "
                f"{state.get('blocked_reason', 'sin motivo guardado')}",
                f"El scaneo está apagado del todo hasta que corras `{settings.PREFIX}instagram reanudar`.",
            ]

        last_read = self._as_local(state.get("last_read_at"))
        next_run = self._as_local(state.get("next_run_at"))
        lines = [
            f"Última lectura: {format_datetime(last_read)}" if last_read else "Todavía no leí nada",
            f"Próxima: {format_time(next_run)}" if next_run else "Próxima: sin agendar",
        ]

        step = state.get("backoff_step", 0)
        if step:
            lines.append(f"En pausa por falla ({state.get('last_failure')}), "
                         f"paso {step} de {len(_BACKOFF_HOURS)}")

        seen = state.get("last_seen")
        if seen:
            lines.append(f"Última home: {seen['seen']} posts, {seen['matched']} de cuentas de la tabla, "
                         f"{seen['posted']} nuevos posteados")
            if seen.get("unknown"):
                lines.append("Vi posts de cuentas que no están en la tabla, así que los ignoré: "
                             + ", ".join(f"@{name}" for name in seen["unknown"]))

        accounts = len(self.bot.influencer_dao.get_by_platform(SocialMedia.INSTAGRAM))
        lines.append(f"{accounts} cuenta(s) en la tabla.")
        return lines

    def _schedule_next(self, now: datetime):
        self.dao.save(next_run_at=now + timedelta(minutes=random.uniform(*_RUN_EVERY_MINUTES)))

    def _as_local(self, value) -> datetime | None:
        """Mongo devuelve los datetime en UTC y sin tzinfo; el resto del bot piensa en hora local."""
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(settings.TIMEZONE)

    async def _handle_flagged(self, error: AccountFlagged, now: datetime):
        """Se apaga el scaneo y se queda apagado. Sin reintento automático: si Instagram puso un
        checkpoint, lo único que arregla algo es que un humano entre a la cuenta y lo resuelva, y
        cada pedido que mandemos mientras tanto confirma lo que ya sospecha. Lo llaman también los
        comandos que le piden algo a Instagram."""
        if error.session_dead:
            await self._stop(error.reason, now, "session",
                             f"**La sesión de @{settings.IG_USERNAME} en Instagram no sirve más y dejo de leer.** "
                             f"Dijo: `{error.reason[:400]}`. Seguir pidiendo con una sesión vencida es justo lo "
                             f"que delata a un programa, así que no sale ningún pedido más. Entrá a Instagram "
                             f"con esa cuenta en Firefox, rehacé la sesión (`instaloader --load-cookies firefox "
                             f"--sessionfile {session_path()}`) y corré `{settings.PREFIX}instagram reanudar`: "
                             f"hasta que la sesión en disco sea nueva, no me deja reanudar.")
        else:
            await self._stop(error.reason, now, "account",
                             f"**Instagram marcó la cuenta y dejo de leer.** Dijo: `{error.reason[:400]}`. "
                             f"Esto no se arregla esperando: entrá a Instagram con @{settings.IG_USERNAME} desde "
                             f"el celular, resolvé lo que te pida y recién ahí corré "
                             f"`{settings.PREFIX}instagram reanudar`. Hasta entonces no le pido nada más.")

    async def _handle_outdated(self, error: ClientOutdated, now: datetime):
        """Instagram cambió algo que el bot no sabe pedir o leer. Reintentar es mandar el mismo
        pedido mal armado una y otra vez: se frena hasta tocar el código."""
        await self._stop(error.reason, now, "outdated",
                         f"**Instagram cambió algo que no sé manejar y dejo de leer.** `{error.reason}`. "
                         f"No es la cuenta: es el código del bot, y el mismo pedido va a rebotar igual. "
                         f"Cuando esté actualizado, `{settings.PREFIX}instagram reanudar`.")

    async def _stop(self, reason: str, now: datetime, kind: str, message: str):
        self.dao.block(reason, now, kind)
        self._reminded = True
        # `stop()` deja terminar la vuelta en curso si estamos adentro del loop; si lo llamó un
        # comando, el loop igual no vuelve a arrancar
        self.instagram_scheduled_job.stop()
        await self.bot.messager.log(message, level="CRITICAL")

    async def _handle_throttled(self, error: Throttled, state: dict, now: datetime):
        """Instagram frenó pero no acusó a nadie. Se espera cada vez más, y se avisa una sola vez
        por episodio: repetir el mismo cartel cada dos horas no agrega información."""
        step = min(state.get("backoff_step", 0) + 1, len(_BACKOFF_HOURS))
        retry_at = now + timedelta(hours=_BACKOFF_HOURS[step - 1] * random.uniform(0.9, 1.2))

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
