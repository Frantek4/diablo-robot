from discord.ext import commands

from config.settings import settings
from models.social_media import SocialMedia

_DISCORD_LIMIT = 1990


class SeguidosCommand(commands.Cog):
    """La tabla de `influencers` de cada red: a quién tiene que seguir la cuenta del bot.

    Sale de Mongo y no le pide nada a la plataforma. Como el bot sólo lee la home, esta es la lista
    con la que hay que hacer coincidir los seguidos de la cuenta.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="seguidos_twitter")
    async def seguidos_twitter(self, ctx):
        """Las cuentas de X de la tabla: a quién tiene que seguir la cuenta del bot"""
        await self._list(ctx, "Twitter", settings.X_USERNAME, SocialMedia.TWITTER)

    @commands.command(name="seguidos_instagram")
    async def seguidos_instagram(self, ctx):
        """Las cuentas de Instagram de la tabla: a quién tiene que seguir la cuenta del bot"""
        await self._list(ctx, "Instagram", settings.IG_USERNAME, SocialMedia.INSTAGRAM)

    async def _list(self, ctx, label: str, username: str, platform: SocialMedia):
        accounts = sorted(self.bot.influencer_dao.get_by_platform(platform), key=lambda i: i["name"].lower())
        if not accounts:
            await ctx.send(f"No hay cuentas de {label} en la tabla.")
            return

        lines = [f"**{label}** — {len(accounts)} cuenta(s) que @{username} tiene que seguir"]
        for account in accounts:
            lines.append(f"· @{account['name']} → {account['description']} ({account['source']})")

        message = ""
        for line in lines:
            if len(message) + len(line) + 1 > _DISCORD_LIMIT:
                await ctx.send(message)
                message = ""
            message += line + "\n"
        if message:
            await ctx.send(message)


async def setup(bot):
    await bot.add_cog(SeguidosCommand(bot))
