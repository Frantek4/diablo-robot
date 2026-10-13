from datetime import datetime

from discord.ext import commands

from config.settings import settings
from integrations.twitter import session_path
from utils.date_format import format_datetime

_FRENADO_A_MANO = "lo frenaste a mano"


class TwitterCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="twitter")
    async def twitter(self, ctx, accion: str = "", *, motivo: str = ""):
        """Cómo viene el scaneo de Twitter. `detener [motivo]` lo frena, `reanudar [forzar]` lo despierta"""
        scheduler = self.bot.get_cog("TwitterCheckScheduler")
        if not scheduler:
            await ctx.send("No tengo el scaneo de Twitter cargado.")
            return

        if accion.lower() == "detener":
            await self._detener(ctx, scheduler, motivo)
            return
        if accion.lower() == "reanudar":
            await self._reanudar(ctx, scheduler, forzar=motivo.strip().lower() == "forzar")
            return

        lines = [f"**Twitter** — sesión de `@{settings.X_USERNAME}`"]
        lines.extend(scheduler.status_lines())

        events = self.bot.twitter_state_dao.recent_events()
        if events:
            lines.append("**Lo que viene pasando**")
            lines.extend(f"· {format_datetime(e['timestamp'])} — {e['kind']}: {str(e.get('reason'))[:120]}"
                         for e in events)

        await ctx.send("\n".join(lines)[:1990])

    async def _detener(self, ctx, scheduler, motivo: str):
        """El aviso de que la cuenta está bajo sospecha te llega a vos, no al bot: el freno a mano
        es para cuando te enterás antes. Usa el mismo freno que se pone solo."""
        state = self.bot.twitter_state_dao.get()
        if state.get("blocked"):
            await ctx.send(f"Ya estaba frenado: {state.get('blocked_reason') or 'sin motivo guardado'}.")
            return

        razon = f"{_FRENADO_A_MANO} ({motivo.strip()})" if motivo.strip() else _FRENADO_A_MANO
        self.bot.twitter_state_dao.block(razon, datetime.now(settings.TIMEZONE), "manual")
        scheduler.twitter_scheduled_job.cancel()
        scheduler._reminded = True
        await ctx.send("Listo, apagué el scaneo de Twitter del todo. Se despierta con "
                       f"`{settings.PREFIX}twitter reanudar`.")

    async def _reanudar(self, ctx, scheduler, forzar: bool):
        """Reanudar es a mano a propósito: el bot no puede saber si alguien destrabó la cuenta."""
        state = self.bot.twitter_state_dao.get()
        if not state.get("blocked"):
            await ctx.send("El scaneo no está frenado, no hay nada que reanudar.")
            return
        if not forzar and self.bot.twitter_state_dao.stale_session(session_path()):
            await ctx.send(f"Lo frené porque la sesión venció, y la de `{session_path()}` sigue siendo la "
                           f"misma de entonces: reanudar así es mandarle otro pedido con las cookies que ya "
                           f"rechazó. Rehacé la sesión y volvé a probar, o `{settings.PREFIX}twitter reanudar "
                           f"forzar` si sabés lo que hacés.")
            return

        self.bot.twitter_state_dao.unblock(datetime.now(settings.TIMEZONE))
        # Tirar el cliente hace que relea las cookies del disco, por si rehiciste la sesión
        scheduler.twitter.reset()
        scheduler._reminded = False
        scheduler.start_scheduled_job()
        aviso = ("Listo, vuelvo a leer Twitter."
                 if (state.get("blocked_reason") or "").startswith(_FRENADO_A_MANO)
                 else "Listo, vuelvo a leer Twitter. Ojalá hayas rehecho la sesión.")
        await ctx.send(aviso)


async def setup(bot):
    await bot.add_cog(TwitterCommand(bot))
