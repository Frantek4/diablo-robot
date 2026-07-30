import discord
from discord.ext import commands, tasks

from config.settings import settings
from integrations import minecraft


class MinecraftCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.banner_message_id = settings.MINECRAFT_STATUS_MESSAGE_ID

    def cog_unload(self):
        self.minecraft_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.minecraft_scheduled_job.is_running():
            self.minecraft_scheduled_job.start()

    @tasks.loop(minutes=1)
    async def minecraft_scheduled_job(self):
        try:
            status = await minecraft.get_status()
            embed = self._build_embed(status)
            message = await self.bot.messager.minecraft_status(embed, self.banner_message_id)
            if message.id != self.banner_message_id:
                self.banner_message_id = message.id
                await self.bot.messager.log(
                    f"Cree el banner de estado de Minecraft (mensaje {message.id}). Poné "
                    f"MINECRAFT_STATUS_MESSAGE_ID={message.id} en el .env para que lo siga usando tras un reinicio."
                )
        except Exception as e:
            await self.bot.messager.log(f"No pude actualizar el estado del server de Minecraft: {e}", level="ERROR", exc=e)

    def _build_embed(self, status) -> discord.Embed:
        if status is None:
            embed = discord.Embed(title="🔴 APAGADO", color=discord.Color.red())
        else:
            embed = discord.Embed(title="🟢 ENCENDIDO", color=discord.Color.green())
            embed.add_field(name="Jugadores", value=f"{status.players.online}/{status.players.max}", inline=True)

            names = [p.name for p in (status.players.sample or [])]
            if names:
                text = ", ".join(names)
                if status.players.online > len(names):
                    text += f" y {status.players.online - len(names)} más"
                embed.add_field(name="Conectados", value=text, inline=False)

        embed.set_footer(text=f"{settings.MINECRAFT_SERVER_HOST}:{settings.MINECRAFT_SERVER_PORT}")
        return embed


async def setup(bot):
    await bot.add_cog(MinecraftCheckScheduler(bot))
