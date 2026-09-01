import logging
import discord
from discord.ext import commands
from bot.config.command_access import is_allowed_in
from bot.config.messager import Messager, init_messager
from config.settings import settings
from data_access.fixture_dao import FixtureDAO
from data_access.game_dao import GameDAO
from data_access.hardware_monitor_dao import HardwareMonitorDAO
from data_access.influencer_dao import InfluencerDAO
from data_access.news_dao import NewsDAO
from data_access.self_destruct_message_dao import SelfDestructMessageDAO

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
        self.self_destruct_message_dao = SelfDestructMessageDAO()
        self.hardware_monitor_dao = HardwareMonitorDAO()

    async def setup_hook(self):
        await self.load_extension('bot.cogs.fixture_event_creator')
        await self.load_extension('bot.cogs.event_lifecycle_manager')
        await self.load_extension('bot.commands.ayuda')
        await self.load_extension('bot.commands.ping')
        await self.load_extension('bot.commands.fijate')
        await self.load_extension('bot.commands.nuevo_juego')
        await self.load_extension('bot.commands.calendario')
        await self.load_extension('bot.commands.nuevo_instagram')
        await self.load_extension('bot.commands.nuevo_youtube')
        await self.load_extension('bot.commands.nuevo_twitter')
        await self.load_extension('bot.commands.transmitir')
        await self.load_extension('bot.commands.limpiar')
        await self.load_extension('bot.commands.reiniciar')
        await self.load_extension('bot.commands.vpn')
        await self.load_extension('bot.scheduled.fixture_check')
        await self.load_extension('bot.cogs.live_match_commentator')
        await self.load_extension('bot.scheduled.commentator_scheduler')
        await self.load_extension('bot.scheduled.news_check')
        await self.load_extension('bot.scheduled.twitter_check')
        await self.load_extension('bot.scheduled.youtube_check')
        await self.load_extension('bot.scheduled.instagram_check')
        await self.load_extension('bot.scheduled.minecraft_check')
        await self.load_extension('bot.scheduled.hardware_monitor_check')
        await self.load_extension('bot.scheduled.self_destruct_message_cleanup')
        await self.load_extension('bot.listeners.game_role')
        await self.load_extension('bot.listeners.post_match_discussion')
        await self.load_extension('bot.listeners.music_agent')
        logger.info("Extensiones cargadas")

    async def on_ready(self):
        self.get_cog('FixtureCheckScheduler').start_scheduled_job()
        self.get_cog('CommentatorScheduler').start_scheduled_job()
        self.get_cog('NewsCheckScheduler').start_scheduled_job()
        self.get_cog('TwitterCheckScheduler').start_scheduled_job()
        self.get_cog('YouTubeCheckScheduler').start_scheduled_job()
        self.get_cog('InstagramCheckScheduler').start_scheduled_job()
        self.get_cog('MinecraftCheckScheduler').start_scheduled_job()
        self.get_cog('HardwareMonitorCheckScheduler').start_scheduled_job()
        self.get_cog('SelfDestructMessageCleanupScheduler').start_scheduled_job()
        init_messager(self)
        await self.get_cog('EventLifecycleManager').start()
        logger.info(f'{self.user} conectado a {self.guilds[0].name}')
        await self.change_presence(activity=discord.CustomActivity(name="Atendiendo boludos"))

    async def on_message(self, message):
        if message.author == self.user:
            return

        ctx = await self.get_context(message)
        if ctx.command is None:
            # Solo en #robot-devil contesto los comandos que no existen
            if message.channel.id == settings.ROBOT_DEVIL_TEXT_CHANNEL_ID:
                await self.invoke(ctx)
            return

        if is_allowed_in(ctx.command, message.channel.id):
            await self.invoke(ctx)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Flashaste")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("No toqués")
        else:
            await ctx.send("Que rompimooo")
            if self.messager:
                await self.messager.log(f"Error de comando '{ctx.command}': {error}", level="ERROR", exc=error)
            else:
                await ctx.send(f"Error de comando '{ctx.command}': {error} (messager indisponible)")
