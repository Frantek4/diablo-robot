import asyncio
import random
from datetime import datetime

from discord.ext import commands, tasks

from config.settings import settings
from integrations.instagram import Instagram
from models.influencer import AttentionLevel
from models.social_media import SocialMedia

# High: every hour except 02:00–07:59
_HIGH_ACTIVE_HOURS = set(range(0, 2)) | set(range(8, 24))
# Low: twice a day within 08:00–19:00
_LOW_ACTIVE_HOURS = {9, 15}


class InstagramCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.instagram = Instagram(bot)

    def cog_unload(self):
        self.instagram_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.instagram_scheduled_job.is_running():
            self.instagram_scheduled_job.start()

    @tasks.loop(hours=1)
    async def instagram_scheduled_job(self):
        await asyncio.sleep(random.uniform(0, 600))
        hour = datetime.now(settings.TIMEZONE).hour

        high_influencers = self.bot.influencer_dao.get_by_platform_and_attention(
            SocialMedia.INSTAGRAM, AttentionLevel.HIGH
        ) if hour in _HIGH_ACTIVE_HOURS else []

        low_influencers = self.bot.influencer_dao.get_by_platform_and_attention(
            SocialMedia.INSTAGRAM, AttentionLevel.LOW
        ) if hour in _LOW_ACTIVE_HOURS else []

        random.shuffle(high_influencers)
        random.shuffle(low_influencers)
        influencers = high_influencers + low_influencers
        if not influencers:
            return

        try:
            await self.instagram.check_notifications(influencers)
        except Exception as e:
            await self.bot.messager.log(f"No pude escanear Instagram: {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(InstagramCheckScheduler(bot))
