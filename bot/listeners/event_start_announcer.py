from discord.ext import commands

class EventStartAnnouncer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_scheduled_event_start(self, event):
        self.bot.messager.announce(f"{event.name} está por empezar")
