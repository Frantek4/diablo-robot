from discord.ext import commands

class PingCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ping')
    async def ping(self, ctx):
        """Mide la latencia del bot"""
        latency = round(self.bot.latency * 1000)
        await self.bot.messager.log(f'Pong! {latency}ms')

async def setup(bot):
    await bot.add_cog(PingCommand(bot))