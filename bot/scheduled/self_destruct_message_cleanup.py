from datetime import datetime

import discord
from discord.ext import commands, tasks

from config.settings import settings


class SelfDestructMessageCleanupScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.cleanup_job.cancel()

    def start_scheduled_job(self):
        if not self.cleanup_job.is_running():
            self.cleanup_job.start()

    @tasks.loop(minutes=1)
    async def cleanup_job(self):
        try:
            due = self.bot.self_destruct_message_dao.get_due(datetime.now(settings.TIMEZONE))
            for message in due:
                await self._delete_message(message.user_id, message.message_id)
                self.bot.self_destruct_message_dao.delete_by_message_id(message.message_id)
        except Exception as e:
            await self.bot.messager.log(f"No pude limpiar mensajes autodestructivos vencidos: {e}", level="ERROR", exc=e)

    async def _delete_message(self, user_id: int, message_id: int):
        try:
            user = await self.bot.fetch_user(user_id)
            dm_channel = user.dm_channel or await user.create_dm()
            message = await dm_channel.fetch_message(message_id)
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass


async def setup(bot):
    await bot.add_cog(SelfDestructMessageCleanupScheduler(bot))
