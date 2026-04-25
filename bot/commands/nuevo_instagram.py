from discord.ext import commands

from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia

class NuevoInstagram(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='nuevo_instagram')
    async def nuevo_influencer(self, ctx, username: str, description: str, source: str):
        
        try:
            source_enum = NewsSource(source.lower())
            platform_enum = SocialMedia.INSTAGRAM

            if self.bot.influencer_dao.exists(username,platform_enum):
                await self.bot.messager.log(f'Ya sigo a {description} en Instagram.')
                return
            
            account = InfluencerModel(
                account_id=None,
                name=username,
                description=description,
                source=source_enum,
                platform=platform_enum
            )
            
            self.bot.influencer_dao.insert(account)
            
            await self.bot.messager.log(f'Suscrito a {description} a Instagram.')
        except ValueError:
            await self.bot.messager.log(f"No reconozco la fuente '{source}' para Instagram.", level="WARNING")

async def setup(bot):
    await bot.add_cog(NuevoInstagram(bot))