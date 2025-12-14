import discord
from discord.ext import commands
from bot.scheduled.fixture_check import FixtureCheckScheduler
from bot.scheduled.news_check import NewsCheckScheduler
from bot.config.messager import Messager, init_messager
from config.settings import settings

class DiabloRobot(commands.Bot):


    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.members = True
        intents.reactions = True
        intents.message_content = True
        intents.guild_scheduled_events = True
        
        super().__init__(
            command_prefix=settings.PREFIX,
            intents=intents
        )
        self.messager : Messager = None
        self.playwright_config = None
    


    async def setup_hook(self):

        # Cogs
        await self.load_extension('bot.cogs.fixture_event_creator')
        await self.load_extension('bot.cogs.event_lifecycle_manager')
        
        # Commands
        await self.load_extension('bot.commands.ping')
        await self.load_extension('bot.commands.fijate')
        await self.load_extension('bot.commands.nuevo_juego')
        await self.load_extension('bot.commands.nuevo_influencer')
        
        # Scheduled
        await self.load_extension('bot.scheduled.fixture_check')
        await self.load_extension('bot.scheduled.news_check')
        
        # Listeners
        await self.load_extension('bot.listeners.game_role')
        await self.load_extension('bot.listeners.event_start_announcer')
        await self.load_extension('bot.listeners.post_match_discussion')

        print("ON")
    


    async def on_ready(self):
        
        fixture_creator: FixtureCheckScheduler = self.get_cog('FixtureCheckScheduler')
        fixture_creator.start_scheduled_job()

        news_poster: NewsCheckScheduler = self.get_cog('NewsCheckScheduler')
        news_poster.start_scheduled_job()


        init_messager(self)

        print(f'{self.user} conectado a Club Atlético Independiente')
        
        await self.change_presence(
            activity=discord.CustomActivity(
                name="Atendiendo boludos"
            )
        )
        

    
    async def on_message(self, message):
        # Ignore messages sent by the bot itself
        if message.author == self.user:
            return
        
        # Ignore incoming messages outside of #diablo-robot
        if message.channel.id != settings.ROBOT_DEVIL_TEXT_CHANNEL_ID:
            return
        
        await self.process_commands(message)



    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Flashaste")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("No toqués")
        else:
            print(f"Error de comando: {error}")
            await ctx.send("Que rompimooo")


    
    # When the guild updates their emojis
    # TODO Announce added emojis
    async def on_guild_emojis_update(self, guild, before, after):
        return
    


    # When the guild updates their stickers
    # TODO Announce added stickers
    async def on_guild_stickers_update(self, guild, before, after):
        return
    


    # When a user becomes a member of the guild
    # TODO Greet new user and give instructive
    async def on_member_join(self, member):
        return
    
    