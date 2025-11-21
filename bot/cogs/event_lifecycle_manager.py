import asyncio
from datetime import datetime
from discord.ext import commands
import discord
from bot.ui.join_voice_button import VoiceJoinView
from config.settings import settings

class EventLifecycleManager(commands.Cog):
    
    
    def __init__(self, bot):
        self.bot = bot
        self._scheduled_jobs = {}



    def cog_unload(self):
        for jobs in self._scheduled_jobs.values():
            for task in jobs.values():
                if not task.done():
                    task.cancel()
        self._scheduled_jobs.clear()



    def schedule_event_lifecycle(self, event: discord.ScheduledEvent):

        if event.id in self._scheduled_jobs:
            for task in self._scheduled_jobs[event.id].values():
                if not task.done():
                    task.cancel()

        now = datetime.now(settings.TIMEZONE)

        start_time = event.start_time.astimezone(settings.TIMEZONE)
        end_time = event.end_time.astimezone(settings.TIMEZONE)

        start_delay = max(0, (start_time - now).total_seconds())
        end_delay = max(0, (end_time - now).total_seconds())

        start_task = asyncio.create_task(
            self._run_after_delay(start_delay, self._on_event_start, event)
        )
        end_task = asyncio.create_task(
            self._run_after_delay(end_delay, self._on_event_end, event)
        )

        self._scheduled_jobs[event.id] = {
            'start': start_task,
            'end': end_task
        }



    async def _run_after_delay(self, delay: float, callback, *args):
        try:
            await asyncio.sleep(delay)
            await callback(*args)
        except asyncio.CancelledError:
            pass



    async def _on_event_start(self, event_id: int, channel_id: int, event_name: str):
        guild = self.bot.get_guild(settings.GUILD_ID)
        if not guild:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return

        try:
            invite = await channel.create_invite(max_uses=0)
            view = VoiceJoinView(invite.url)
            await self.bot.messager.announce_interactive(
                f"**¡Arranca el partido!**\nSumate a {channel.mention} para ver **{event_name}**",
                view=view
            )

        except Exception as e:
            await self.bot.messager.log(f"Error al iniciar evento {event_id}: {e}")



    async def _on_event_end(self, event_id: int, channel_id: int, event_name: str):
        guild = self.bot.get_guild(settings.GUILD_ID)
        if not guild:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return

        try:
            try:
                event = await guild.fetch_scheduled_event(event_id)
                await event.delete(reason="Evento finalizado")
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        except Exception as e:
            await self.bot.messager.log(f"Error al eliminar evento {event_id}: {e}")

async def setup(bot):
    await bot.add_cog(EventLifecycleManager(bot))