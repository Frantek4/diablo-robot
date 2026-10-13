import asyncio
import random
from datetime import datetime, timedelta, timezone

from discord.ext import commands, tasks

from config.settings import settings
from integrations.twitter import Twitter
from integrations.social_errors import AccountFlagged, ClientOutdated, Throttled, Unreachable
from integrations.twitter import session_path
from integrations.x_api import RateWindow
from models.social_media import SocialMedia
from utils.date_format import format_datetime, format_time

# Horario de gente despierta: de 08:00 a 23:00. Una lectura a las 4am es, ella sola, una firma de
# que del otro lado no hay nadie
_ACTIVE_HOURS = set(range(8, 23))
# El loop tiquea seguido pero la vuelta de verdad se agenda sola, con jitter: pedir clavado en el
# mismo minuto de cada hora es el patrón más fácil de marcar que hay
_TICK_MINUTES = 5
_RUN_EVERY_MINUTES = (45, 145)
# Cuánto se espera después de cada falla seguida en la que X contestó que no. Insistir contra una
# cuenta que X está frenando no trae tweets: sólo la hunde más y repite el mismo aviso
_BACKOFF_HOURS = (1, 2, 4, 6)
_STARTUP_GRACE_SECONDS = (60, 180)
# Por debajo de esto no se pide aunque X diga que queda margen: si la cuenta se usa para otra cosa,
# que la ráfaga la vea el humano y no el bot
_HARD_FLOOR = 10
_FLOOR_FRACTION = 0.25


class TwitterCheckScheduler(commands.Cog):
    """Mira la home "Siguiendo" de X una vez por vuelta y postea lo de las cuentas de la tabla.

    Que sea la home y no cuenta por cuenta es todo el diseño: una vuelta es un solo pedido, el
    mismo que hace cualquiera que abre la app, en vez de una ronda de visitas a perfiles que
    ninguna persona hace cada hora. El estado —freno, backoff, la última ventana de rate limit
    que informó X, el queryId de la home— va a Mongo, porque un bot que se reinicia y vuelve a
    leer como si nada después de que X bloqueó la cuenta es exactamente la forma de perderla.
    """

    def __init__(self, bot):
        self.bot = bot
        self.twitter = Twitter(bot)
        self.dao = bot.twitter_state_dao
        # El recordatorio de que el scaneo está frenado se da una vez por arranque del bot
        self._reminded = False

    def cog_unload(self):
        self.twitter_scheduled_job.cancel()

    def start_scheduled_job(self):
        """Lo llama `on_ready()` y también `!twitter reanudar`, así que aguanta el loop apagado,
        corriendo, o recién cancelado y todavía sin terminar de morir."""
        if not settings.X_USERNAME:
            return
        if self.twitter_scheduled_job.is_running():
            self.twitter_scheduled_job.restart()
        else:
            self.twitter_scheduled_job.start()

    @tasks.loop(minutes=_TICK_MINUTES)
    async def twitter_scheduled_job(self):
        state = self.dao.get()

        if state.get("blocked"):
            # Esta vuelta existe sólo para que el aviso salga después de un reinicio del bot
            await self._remind_blocked(state)
            self.twitter_scheduled_job.stop()
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

        window = self._window(state)
        if not self._has_margin(window):
            # Callado a propósito: no leer porque no hay margen es el bot portándose bien
            self._schedule_next(now, window.reset)
            return

        try:
            seen = await self.twitter.read_home()
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
                f"No llegué a X ({e.reason}). Eso es la red del Pi, no un freno de X: el pedido no "
                f"existió para ellos, así que sigo con el ritmo de siempre.", level="WARNING")
            return
        except Exception as e:
            self._schedule_next(datetime.now(settings.TIMEZONE))
            await self.bot.messager.log(f"No pude escanear Twitter: {e}", level="ERROR", exc=e)
            return
        finally:
            self._save_window()

        recovered = state.get("backoff_step", 0) > 0
        done = datetime.now(settings.TIMEZONE)
        self.dao.save(backoff_step=0, last_failure=None, last_read_at=done, last_seen=seen)
        self._schedule_next(done)

        if recovered:
            await self.bot.messager.log("X volvió a contestarme bien, retomo el scaneo de Twitter.")

    @twitter_scheduled_job.before_loop
    async def before_twitter_scheduled_job(self):
        await asyncio.sleep(random.uniform(*_STARTUP_GRACE_SECONDS))

    def status_lines(self) -> list[str]:
        """Cómo viene el scaneo, para mirarlo desde Discord sin entrar al Pi."""
        if not settings.X_USERNAME:
            return ["No tengo `X_USERNAME` configurado, así que no leo Twitter."]

        state = self.dao.get()
        if state.get("blocked"):
            when = self._as_local(state.get("blocked_at"))
            return [
                f"🛑 **Frenado desde {format_datetime(when) if when else '?'}**: "
                f"{state.get('blocked_reason', 'sin motivo guardado')}",
                f"El scaneo está apagado del todo hasta que corras `{settings.PREFIX}twitter reanudar`.",
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

        window = self._window(state)
        lines.append(f"Margen de la home: {window}" if window else "X todavía no me dijo cuánto margen tengo")

        seen = state.get("last_seen")
        if seen:
            lines.append(f"Última home: {seen['seen']} tweets, {seen['matched']} de cuentas de la tabla, "
                         f"{seen['posted']} nuevos posteados")
            if seen.get("unknown"):
                lines.append("Sigo cuentas que no están en la tabla, así que las ignoro: "
                             + ", ".join(f"@{name}" for name in seen["unknown"]))

        accounts = len(self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER))
        lines.append(f"{accounts} cuenta(s) en la tabla. "
                     f"queryId de la home: {state.get('home_query_id') or 'lo busco en la próxima vuelta'}")
        return lines

    def _window(self, state: dict) -> RateWindow | None:
        """El último rate limit que X informó, de memoria o, después de un reinicio, de Mongo."""
        if self.twitter.window:
            return self.twitter.window
        reset = self._as_local(state.get("rate_reset"))
        if reset is None or state.get("rate_limit") is None:
            return None
        return RateWindow(remaining=state["rate_remaining"], limit=state["rate_limit"], reset=reset)

    @staticmethod
    def _has_margin(window: RateWindow | None) -> bool:
        if window is None or window.stale:
            return True
        return window.remaining > max(_HARD_FLOOR, int(window.limit * _FLOOR_FRACTION))

    def _save_window(self):
        window = self.twitter.window
        if window:
            self.dao.save(rate_remaining=window.remaining, rate_limit=window.limit, rate_reset=window.reset)

    def _schedule_next(self, now: datetime, resumes_at: datetime | None = None):
        """Si sé cuándo se repone la ventana arranco un rato después, no en el segundo exacto."""
        if resumes_at and resumes_at > now:
            next_run = resumes_at + timedelta(minutes=random.uniform(1, 5))
        else:
            next_run = now + timedelta(minutes=random.uniform(*_RUN_EVERY_MINUTES))
        self.dao.save(next_run_at=next_run)

    def _as_local(self, value) -> datetime | None:
        """Mongo devuelve los datetime en UTC y sin tzinfo; el resto del bot piensa en hora local."""
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(settings.TIMEZONE)

    async def _handle_flagged(self, error: AccountFlagged, now: datetime):
        """Se apaga el scaneo y se queda apagado. Sin reintento automático: el bot no puede saber
        si alguien destrabó la cuenta o rehízo las cookies, y adivinar que sí es justo el error que
        cuesta la cuenta. Lo llaman también los comandos que le piden algo a X."""
        if error.session_dead:
            await self._stop(error.reason, now, "session",
                             f"**La sesión de @{settings.X_USERNAME} en X no sirve más y dejo de leer Twitter.** "
                             f"Dijo: `{error.reason}`. Seguir pidiendo con una sesión vencida es justo lo que "
                             f"delata a un programa, así que no sale ningún pedido más. Logueate en x.com con "
                             f"esa cuenta en Firefox, rehacé la sesión (`python3 tools/firefox_session.py x "
                             f"{settings.X_USERNAME}`) y corré `{settings.PREFIX}twitter reanudar`: hasta que la "
                             f"sesión en disco sea nueva, no me deja reanudar.")
        else:
            await self._stop(error.reason, now, "account",
                             f"**X no me deja seguir con @{settings.X_USERNAME} y dejo de leer Twitter.** Dijo: "
                             f"`{error.reason}`. Esto no se arregla esperando: entrá a x.com con esa cuenta en "
                             f"Firefox, resolvé lo que te pida y corré `{settings.PREFIX}twitter reanudar`. "
                             f"Hasta entonces no le pido nada más.")

    async def _handle_outdated(self, error: ClientOutdated, now: datetime):
        """X cambió algo que el bot no sabe pedir o leer. Reintentar es mandar el mismo pedido mal
        armado una y otra vez, que no se parece a ningún navegador: se frena hasta tocar el código."""
        await self._stop(error.reason, now, "outdated",
                         f"**X cambió algo que no sé manejar y dejo de leer Twitter.** `{error.reason}`. "
                         f"No es la cuenta: es el código del bot, y el mismo pedido va a rebotar igual. "
                         f"Cuando esté actualizado, `{settings.PREFIX}twitter reanudar`.")

    async def _stop(self, reason: str, now: datetime, kind: str, message: str):
        self.dao.block(reason, now, kind)
        self._reminded = True
        # `stop()` deja terminar la vuelta en curso si estamos adentro del loop; si lo llamó un
        # comando, el loop igual no vuelve a arrancar
        self.twitter_scheduled_job.stop()
        await self.bot.messager.log(message, level="CRITICAL")

    async def _handle_throttled(self, error: Throttled, state: dict, now: datetime):
        """X frenó pero no acusó a nadie. Se espera cada vez más, y se avisa una sola vez por
        episodio. Si X dijo cuándo se repone la ventana, no vuelvo antes de eso."""
        step = min(state.get("backoff_step", 0) + 1, len(_BACKOFF_HOURS))
        retry_at = now + timedelta(hours=_BACKOFF_HOURS[step - 1] * random.uniform(0.9, 1.2))
        if error.resets_at and error.resets_at > retry_at:
            retry_at = error.resets_at + timedelta(minutes=random.uniform(1, 5))

        self.dao.save(backoff_step=step, last_failure=error.reason, next_run_at=retry_at)
        self.dao.log_event("throttled", error.reason, now)

        if step == 1:
            await self.bot.messager.log(
                f"X me frenó (`{error.reason}`), pero sin bloquear la cuenta. Dejo de pedirle hasta "
                f"las {format_time(retry_at)} y después sigo. Si se repite, mirá `{settings.PREFIX}twitter`.",
                level="WARNING",
            )

    async def _remind_blocked(self, state: dict):
        if self._reminded:
            return
        self._reminded = True
        when = self._as_local(state.get("blocked_at"))
        await self.bot.messager.log(
            f"Sigo sin leer Twitter: quedó frenado el {format_datetime(when) if when else '?'} "
            f"porque {state.get('blocked_reason', 'X bloqueó la cuenta')}. "
            f"Se reanuda con `{settings.PREFIX}twitter reanudar`.",
            level="WARNING",
        )


async def setup(bot):
    await bot.add_cog(TwitterCheckScheduler(bot))
