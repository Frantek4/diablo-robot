from discord.ext import commands

from data_access.influencers import InfluencerDAO
from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia
from integrations.youtube import YouTube

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
            
            if platform_enum == SocialMedia.YOUTUBE:
                channel_id = await YouTube.get_channel_id(username)
                if not channel_id:
                    await self.bot.messager.log(f"No se pudo encontrar el canal de YouTube para @{username}")
                    return
                
                account = InfluencerModel(
                    id=channel_id,
                    name=username,
                    description=description,
                    source=source_enum,
                    platform=platform_enum
                )

            elif platform_enum == SocialMedia.INSTAGRAM:
            
                account = InfluencerModel(
                    id=None,
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