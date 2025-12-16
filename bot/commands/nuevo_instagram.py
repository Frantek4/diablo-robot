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
                await self.bot.messager.log(f'{username} ya está registrado para {SocialMedia.INSTAGRAM}.')
                return
            
            account = InfluencerModel(
                id=None,
                name=username,
                description=description,
                source=source_enum,
                platform=platform_enum
            )
            
            self.bot.influencer_dao.insert(account)
            
            await self.bot.messager.log(f'{username} agregado como influencer.')
        except ValueError:
            await self.bot.messager.log(f"Fuente {source} o plataforma {SocialMedia.INSTAGRAM} inválidos.")

async def setup(bot):
    await bot.add_cog(NuevoInstagram(bot))