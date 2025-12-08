from discord.ext import commands

from data_access.influencers import InfluencerDAO
from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia

class NuevoInfluencer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.influencer_dao = InfluencerDAO()

    @commands.command(name='nuevo_influencer')
    async def nuevo_influencer(self, ctx, username: str, description: str, source: str, platform: str):
        
        try:
            source_enum = NewsSource(source.lower())
            platform_enum = SocialMedia(platform.lower())

            if self.influencer_dao.exists(username,platform_enum):
                await self.bot.messager.log(f'{username} ya está registrado para {platform}.')
                return
            
            account = InfluencerModel(
                name=username,
                description=description,
                source=source_enum,
                platform=platform_enum
            )
            
            self.influencer_dao.insert(account)
            
            await self.bot.messager.log(f'{username} agregado como influencer.')
        except ValueError:
            await self.bot.messager.log(f"Fuente {source} o plataforma {platform} inválidos.")

async def setup(bot):
    await bot.add_cog(NuevoInfluencer(bot))