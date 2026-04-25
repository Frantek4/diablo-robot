from discord.ext import commands, tasks

from integrations.twitter import Twitter


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
            await self.bot.messager.log(f"No pude escanear Twitter: {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(TwitterCheckScheduler(bot))
