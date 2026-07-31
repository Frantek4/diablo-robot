import discord
from discord.ext import commands


class LimpiarCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="limpiar")
    async def limpiar(self, ctx, cantidad: int = None):
        """Sin argumento borra los mensajes de error y advertencia del chat.
        Con un número, borra esa cantidad de mensajes (máximo 100)."""

        def is_error_or_warning(message):
            return message.author == self.bot.user and (
                message.content.startswith("`[ERROR]`") or message.content.startswith("`[ADVERTENCIA]`")
            )

        try:
            if cantidad is None:
                deleted = await ctx.channel.purge(limit=500, check=is_error_or_warning)
                await self.bot.messager.log(f"Limpié {len(deleted)} mensajes de error/advertencia.")
            else:
                limit = max(1, min(cantidad, 100))
                deleted = await ctx.channel.purge(limit=limit)
                await self.bot.messager.log(f"Limpié {len(deleted)} mensajes.")
        except discord.Forbidden:
            await self.bot.messager.log("No tengo permisos para borrar mensajes acá.", level="ERROR")


async def setup(bot):
    await bot.add_cog(LimpiarCommand(bot))
