import logging
import discord
from discord.ext import commands
from bot.config.messager import Messager, init_messager
from config.settings import settings
from data_access.fixture_dao import FixtureDAO
from data_access.game_dao import GameDAO
from data_access.influencer_dao import InfluencerDAO
from data_access.news_dao import NewsDAO

logger = logging.getLogger(__name__)


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
        self.messager: Messager = None
        self.news_dao = NewsDAO()
        self.games_dao = GameDAO()
        self.influencer_dao = InfluencerDAO()
        self.fixture_dao = FixtureDAO()

    async def setup_hook(self):
        await self.load_extension('bot.cogs.fixture_event_creator')
        await self.load_extension('bot.cogs.event_lifecycle_manager')
        await self.load_extension('bot.commands.ping')
        await self.load_extension('bot.commands.fijate')
        await self.load_extension('bot.commands.nuevo_juego')
        await self.load_extension('bot.commands.nuevo_instagram')
        await self.load_extension('bot.commands.nuevo_youtube')
        await self.load_extension('bot.commands.nuevo_twitter')
        await self.load_extension('bot.scheduled.fixture_check')
        await self.load_extension('bot.scheduled.live_match_scheduler')
        await self.load_extension('bot.scheduled.news_check')
        await self.load_extension('bot.scheduled.twitter_check')
        await self.load_extension('bot.scheduled.youtube_check')
        await self.load_extension('bot.listeners.game_role')
        await self.load_extension('bot.listeners.event_start_announcer')
        await self.load_extension('bot.listeners.post_match_discussion')
        logger.info("Extensiones cargadas")

    async def on_ready(self):
        self.get_cog('FixtureCheckScheduler').start_scheduled_job()
        self.get_cog('LiveMatchScheduler').start_scheduled_job()
        self.get_cog('NewsCheckScheduler').start_scheduled_job()
        self.get_cog('TwitterCheckScheduler').start_scheduled_job()
        self.get_cog('YouTubeCheckScheduler').start_scheduled_job()
        init_messager(self)
        logger.info(f'{self.user} conectado a Club Atlético Independiente')
        await self.change_presence(activity=discord.CustomActivity(name="Atendiendo boludos"))

    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.channel.id != settings.ROBOT_DEVIL_TEXT_CHANNEL_ID:
            return
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Flashaste")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("No toqués")
        else:
            logger.error(f"Error de comando '{ctx.command}': {error}", exc_info=error)
            await ctx.send("Que rompimooo")
