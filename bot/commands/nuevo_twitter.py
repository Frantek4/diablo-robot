from discord.ext import commands

from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia

class NuevoTwitter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='nuevo_twitter')
    async def nuevo_influencer(self, ctx, username: str, description: str, source: str):
        """Suscribe una cuenta de Twitter/X para avisar cuando publique."""
        try:
            source_enum = NewsSource(source.lower())
            platform_enum = SocialMedia.TWITTER

            if self.bot.influencer_dao.exists(username, platform_enum):
                await self.bot.messager.log(f'Ya sigo a {description} en Twitter.')
                return
            
            account = InfluencerModel(
                account_id=None,
                name=username,
                description=description,
                source=source_enum,
                platform=platform_enum
            )
            
            self.bot.influencer_dao.insert(account)
            
            await self.bot.messager.log(f'Siguiendo a {description} en Twitter.')
        except ValueError:
            await self.bot.messager.log(f"No reconozco la fuente '{source}' para Twitter.", level="WARNING")

async def setup(bot):
    await bot.add_cog(NuevoTwitter(bot))
