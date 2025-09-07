from discord.ext import commands
from bot.cogs.fixture_event_creator import FixtureEventCreator
from models.team_url import Teams

class FijateCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fixture_event_creator = FixtureEventCreator(bot)
    
    @commands.command(name='fijate')
    @commands.has_permissions(manage_guild=True)
    async def fijate(self, ctx):
        """Manually trigger fixture check"""
        await self.bot.messager.log("Buscando próximos partidos.")
        for team in Teams:
            await self.fixture_event_creator.upsert_next_fixture_event(team)

async def setup(bot):
    await bot.add_cog(FijateCommand(bot))