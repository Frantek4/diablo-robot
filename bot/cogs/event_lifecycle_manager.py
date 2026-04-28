from datetime import datetime
from discord.ext import commands, tasks
import discord
from bot.ui.join_voice_button import VoiceJoinView
from config.settings import settings
from utils.date_format import to_local


class EventLifecycleManager(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self._announced_ids: set[int] = set()

    def cog_unload(self):
        self.lifecycle_check.cancel()

    async def start(self):
        guild = self.bot.get_guild(settings.GUILD_ID)
        now = datetime.now(settings.TIMEZONE)
        midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
        for event in await guild.fetch_scheduled_events():
            if event.status != discord.EventStatus.active or event.id in self._announced_ids:
                continue
            end = to_local(event.end_time) if event.end_time else midnight
            if now >= end:
                await self._end_event(event)
            else:
                await self._announce_start(event)
        self.lifecycle_check.start()

    @commands.Cog.listener()
    async def on_scheduled_event_start(self, event):
        if event.id not in self._announced_ids:
            await self._announce_start(event)

    @tasks.loop(minutes=5)
    async def lifecycle_check(self):
        guild = self.bot.get_guild(settings.GUILD_ID)
        now = datetime.now(settings.TIMEZONE)
        midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
        for event in guild.scheduled_events:
            if event.status != discord.EventStatus.active:
                continue
            end = to_local(event.end_time) if event.end_time else midnight
            if now >= end:
                await self._end_event(event)

    async def _end_event(self, event: discord.ScheduledEvent):
        try:
            await event.end(reason="Evento finalizado")
        except discord.Forbidden:
            await self.bot.messager.log(f"No me dejan cerrar el boliche '{event.name}'.", level="ERROR")
        except (discord.NotFound, discord.HTTPException):
            pass

    async def _announce_start(self, event: discord.ScheduledEvent):
        self._announced_ids.add(event.id)
        channel = self.bot.get_channel(event.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return
        try:
            invite = await channel.create_invite(max_uses=0)
            view = VoiceJoinView(invite.url)
            await self.bot.messager.announce_interactive(
                f"**¡Arranca el partido!**\nSumate a {channel.mention} para ver **{event.name}**",
                view=view
            )
        except Exception as e:
            await self.bot.messager.log(f"No arranca esto che... '{event.name}': {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(EventLifecycleManager(bot))
