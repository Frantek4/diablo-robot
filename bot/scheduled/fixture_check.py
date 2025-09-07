from discord.ext import commands, tasks
from bot.cogs.fixture_event_creator import FixtureEventCreator
from models.team_url import Teams

class FixtureCheckScheduler(commands.Cog):



    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.fixture_event_creator = FixtureEventCreator(bot)
    


    def cog_unload(self):
        self.fixture_scheduled_job.cancel()



    def start_scheduled_job(self):
        if not self.fixture_scheduled_job.is_running():
            self.fixture_scheduled_job.start()



    @tasks.loop(hours=1)
    async def fixture_scheduled_job(self):
        for team in Teams:
            await self.fixture_event_creator.upsert_next_fixture_event(team)

async def setup(bot: commands.Bot):
    await bot.add_cog(FixtureCheckScheduler(bot))