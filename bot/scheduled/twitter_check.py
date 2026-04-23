import logging
from discord.ext import commands, tasks

from integrations.twitter import Twitter

logger = logging.getLogger(__name__)


class TwitterCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitter = Twitter(bot)

    def cog_unload(self):
        self.twitter_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.twitter_scheduled_job.is_running():
            self.twitter_scheduled_job.start()

    @tasks.loop(minutes=10)
    async def twitter_scheduled_job(self):
        try:
            await self.twitter.check_rss_notifications()
        except Exception as e:
            logger.error(f"Error in Twitter check: {str(e)}", exc_info=True)
            await self.bot.messager.log(f"Error escaneando Twitter: {str(e)}")


async def setup(bot):
    await bot.add_cog(TwitterCheckScheduler(bot))
