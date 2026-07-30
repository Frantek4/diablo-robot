from discord.ext import commands

from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia

class NuevoYouTube(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='nuevo_youtube')
    async def nuevo_influencer(self, ctx, account_id: str, username: str, description: str, source: str):
        """Suscribe un canal de YouTube para avisar cuando suba un video."""
        try:
            source_enum = NewsSource(source.lower())
            platform_enum = SocialMedia.YOUTUBE

            if self.bot.influencer_dao.exists(username,platform_enum):
                await self.bot.messager.log(f'Ya estoy suscrito a {description} en YouTube.')
                return
            
            account = InfluencerModel(
                account_id=account_id,
                name=username,
                description=description,
                source=source_enum,
                platform=platform_enum
            )
            
            self.bot.influencer_dao.insert(account)
            
            await self.bot.messager.log(f'Suscrito a {description} en YouTube.')
        except ValueError:
            await self.bot.messager.log(f"No reconozco la fuente '{source}' para YouTube.", level="WARNING")

async def setup(bot):
    await bot.add_cog(NuevoYouTube(bot))