import discord
from discord.ext import commands


class LimpiarCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="limpiar")
    async def limpiar(self, ctx):
        """Borra los mensajes de error y advertencia del chat"""

        def is_error_or_warning(message):
            return message.author == self.bot.user and (
                message.content.startswith("`[ERROR]`") or message.content.startswith("`[ADVERTENCIA]`")
            )

        try:
            deleted = await ctx.channel.purge(limit=500, check=is_error_or_warning)
        except discord.Forbidden:
            await self.bot.messager.log("No tengo permisos para borrar mensajes acá.", level="ERROR")
            return

        await self.bot.messager.log(f"Limpié {len(deleted)} mensajes de error/advertencia.")


async def setup(bot):
    await bot.add_cog(LimpiarCommand(bot))
