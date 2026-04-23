import logging
from discord.ext import commands, tasks

from integrations.youtube import YouTube

logger = logging.getLogger(__name__)


class YouTubeCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.youtube = YouTube(bot)

    def cog_unload(self):
        self.youtube_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.youtube_scheduled_job.is_running():
            self.youtube_scheduled_job.start()

    @tasks.loop(minutes=10)
    async def youtube_scheduled_job(self):
        try:
            await self.youtube.check_rss_notifications()
        except Exception as e:
            logger.error(f"Error in YouTube check: {str(e)}", exc_info=True)
            await self.bot.messager.log(f"Error escaneando YouTube: {str(e)}")


async def setup(bot):
    await bot.add_cog(YouTubeCheckScheduler(bot))
