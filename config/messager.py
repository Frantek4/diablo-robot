import discord
from config.settings import settings

class Messager:

    def __init__(self, bot):
        self.bot = bot
        self.guild = self.bot.get_guild(settings.GUILD_ID)
        if not self.guild:
            raise RuntimeError(f"Mensajero invocado antes de conectarse al servidor.")

        self.general_channel = discord.utils.get(self.guild.text_channels, name=settings.GENERAL_TEXT_CHANNEL_NAME)
        self.announcements_channel = discord.utils.get(self.guild.text_channels, name=settings.ANNOUNCEMENTS_TEXT_CHANNEL_NAME)
        self.games_channel = discord.utils.get(self.guild.text_channels, name=settings.GAMES_TEXT_CHANNEL_NAME)
        self.devil_robot_channel = discord.utils.get(self.guild.text_channels, name=settings.ROBOT_DEVIL_TEXT_CHANNEL_NAME)

        missing_channels = []
        if not self.general_channel:
            missing_channels.append(settings.GENERAL_TEXT_CHANNEL_NAME)
        if not self.announcements_channel:
            missing_channels.append(settings.ANNOUNCEMENTS_TEXT_CHANNEL_NAME)
        if not self.games_channel:
            missing_channels.append(settings.GAMES_TEXT_CHANNEL_NAME)
        if not self.devil_robot_channel:
            missing_channels.append(settings.ROBOT_DEVIL_TEXT_CHANNEL_NAME)

        if missing_channels:
            raise RuntimeError(f"Canales no encontrados: {', '.join(missing_channels)}. Revisá las configuraciones.")

    async def chat(self, msg: str):
        await self.general_channel.send(msg)
    
    async def announce(self, msg: str):
        await self.announcements_channel.send(msg)

    async def announce_interactive(self, msg: str, view):
        await self.announcements_channel.send(msg, view=view)

    async def add_to_catalogue(self, title: str, attachment_file: discord.File):
        message = await self.games_channel.send(content=title, file=attachment_file)
        return message
    
    async def log(self, msg: str):
        print(msg)
        if len(msg) > 2000:
            msg = msg[:1997] + "..."
        await self.devil_robot_channel.send(msg)

def init_messager(bot):
    if hasattr(bot, 'messager') and bot.messager is not None:
        return bot.messager

    messager = Messager(bot)
    bot.messager = messager
