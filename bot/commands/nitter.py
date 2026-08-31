import discord
from discord.ext import commands

from utils.date_format import format_datetime


class NitterCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nitter")
    async def nitter(self, ctx, accion: str = None):
        """Muestra el repositorio de mirrors de Nitter y cómo le fue a cada uno.
        Con `revisar` los prueba a todos de nuevo en el momento."""
        if accion and accion.lower() in ("revisar", "chequear", "probar"):
            scheduler = self.bot.get_cog("NitterMirrorCheckScheduler")
            if not scheduler:
                await self.bot.messager.log("No tengo cargado el chequeo de mirrors de Nitter.", level="ERROR")
                return
            await ctx.send("Dale, los pruebo a todos y te digo. Tarda un minuto.")
            await scheduler.check_mirrors(force=True)

        mirrors = self.bot.nitter_mirror_dao.get_ranked()
        if not mirrors:
            await ctx.send(f"Todavía no tengo ningún mirror de Nitter en el repositorio. Probá con `{ctx.clean_prefix}nitter revisar`.")
            return

        online = sum(1 for mirror in mirrors if mirror.is_online)
        embed = discord.Embed(
            title="Mirrors de Nitter",
            description=f"{online} de {len(mirrors)} andando.",
            color=discord.Color.green() if online else discord.Color.red(),
        )

        for mirror in mirrors[:25]:
            if mirror.is_online:
                detail = f"anda ({round(mirror.latency_ms)} ms)" if mirror.latency_ms else "anda"
            elif mirror.is_online is None:
                detail = "todavía no lo probé"
            else:
                detail = mirror.last_reason or "no anda"
                if mirror.consecutive_failures > 1:
                    detail += f" · {mirror.consecutive_failures} veces seguidas"

            if mirror.last_check:
                detail += f"\nÚltimo chequeo: {format_datetime(mirror.last_check)}"

            embed.add_field(name=f"{mirror.status_emoji} {mirror.host}", value=detail, inline=False)

        embed.set_footer(text=f"Origen del listado: wiki de Nitter · {ctx.clean_prefix}nitter revisar para probarlos ahora")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(NitterCommand(bot))
