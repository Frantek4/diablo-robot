from datetime import datetime

from discord.ext import commands

from config.settings import settings
from utils.date_format import format_datetime

_FRENADO_A_MANO = "lo frenaste a mano"


class InstagramCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="instagram")
    async def instagram(self, ctx, accion: str = "", *, motivo: str = ""):
        """Cómo viene el scaneo de Instagram. `detener [motivo]` lo frena, `reanudar` lo despierta"""
        scheduler = self.bot.get_cog("InstagramCheckScheduler")
        if not scheduler:
            await ctx.send("No tengo el scaneo de Instagram cargado.")
            return

        if accion.lower() == "detener":
            await self._detener(ctx, scheduler, motivo)
            return
        if accion.lower() == "reanudar":
            await self._reanudar(ctx, scheduler)
            return

        lines = [f"**Instagram** — sesión de `@{settings.IG_USERNAME}`"]
        lines.extend(scheduler.status_lines())

        events = self.bot.instagram_state_dao.recent_events()
        if events:
            lines.append("**Lo que viene pasando**")
            lines.extend(f"· {format_datetime(e['timestamp'])} — {e['kind']}: {str(e.get('reason'))[:120]}"
                         for e in events)

        await ctx.send("\n".join(lines)[:1990])

    async def _detener(self, ctx, scheduler, motivo: str):
        """El freno a mano existe porque el que primero se entera sos vos, no el bot.

        La advertencia de comportamiento automatizado te llega a vos por mail o por la app; el bot
        recién se entera cuando Instagram le corta el acceso, que es tarde. Esto usa el mismo freno
        que se pone solo, así que sale con el mismo `reanudar`.
        """
        state = self.bot.instagram_state_dao.get()
        if state.get("blocked"):
            await ctx.send(f"Ya estaba frenado: {state.get('blocked_reason') or 'sin motivo guardado'}.")
            return

        razon = f"{_FRENADO_A_MANO} ({motivo.strip()})" if motivo.strip() else _FRENADO_A_MANO
        self.bot.instagram_state_dao.block(razon, datetime.now(settings.TIMEZONE))
        # Dos cosas distintas: `request_stop()` corta la vuelta que pueda estar corriendo ahora
        # mismo (duran varios minutos, por los huecos entre cuenta y cuenta) y `cancel()` apaga el
        # loop entero, que si no seguiría tictaqueando cada cinco minutos para no hacer nada
        scheduler.instagram.request_stop()
        scheduler.instagram_scheduled_job.cancel()
        scheduler._reminded = True
        await ctx.send("Listo, apagué el scaneo de Instagram del todo. Se despierta con "
                       f"`{settings.PREFIX}instagram reanudar`.")

    async def _reanudar(self, ctx, scheduler):
        """Reanudar es a mano a propósito: el bot no puede saber si alguien entró a la cuenta a
        resolver el checkpoint, y adivinar que sí es justo el error que cuesta la cuenta."""
        state = self.bot.instagram_state_dao.get()
        if not state.get("blocked"):
            await ctx.send("El scaneo no está frenado, no hay nada que reanudar.")
            return

        self.bot.instagram_state_dao.unblock(datetime.now(settings.TIMEZONE))
        scheduler.instagram._reset()
        scheduler._reminded = False
        scheduler.start_scheduled_job()
        aviso = ("Listo, vuelvo a leer Instagram."
                 if (state.get("blocked_reason") or "").startswith(_FRENADO_A_MANO)
                 else "Listo, vuelvo a leer Instagram. Ojalá hayas rehecho la sesión.")
        await ctx.send(aviso)


async def setup(bot):
    await bot.add_cog(InstagramCommand(bot))
