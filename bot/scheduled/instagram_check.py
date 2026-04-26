from discord.ext import commands, tasks

from integrations.instagram import Instagram


class InstagramCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.instagram = Instagram(bot)

    def cog_unload(self):
        self.instagram_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.instagram_scheduled_job.is_running():
            self.instagram_scheduled_job.start()

    @tasks.loop(minutes=45)
    async def instagram_scheduled_job(self):
        try:
            await self.instagram.check_notifications()
        except Exception as e:
            await self.bot.messager.log(f"No pude escanear Instagram: {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(InstagramCheckScheduler(bot))
