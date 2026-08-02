import discord
from datetime import datetime, timedelta
from discord.ext import commands, tasks

from config.settings import settings
from integrations import hardware_monitor
from models.hardware_snapshot import HardwareSnapshot, format_duration


class HardwareMonitorCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.banner_message_id = settings.HARDWARE_MONITOR_STATUS_MESSAGE_ID

        state = self.bot.hardware_monitor_dao.get_latest()
        self.is_online = state["is_online"] if state else True
        self.last_snapshot = HardwareSnapshot.from_dict(state["snapshot"]) if state and state.get("snapshot") else None
        self.went_offline_at = None

    def cog_unload(self):
        self.hardware_monitor_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.hardware_monitor_scheduled_job.is_running():
            self.hardware_monitor_scheduled_job.start()

    @tasks.loop(minutes=1)
    async def hardware_monitor_scheduled_job(self):
        try:
            snapshot = await hardware_monitor.get_status()
            now = datetime.now(settings.TIMEZONE)

            if snapshot is not None:
                if not self.is_online:
                    downtime = (
                        f" (estuvo caída {format_duration((now - self.went_offline_at).total_seconds())})"
                        if self.went_offline_at else ""
                    )
                    await self.bot.messager.hardware_monitor_alert(f"✅ Volvió la PC de Minecraft{downtime}.")
                    self.bot.hardware_monitor_dao.log_transition(is_online=True, snapshot=snapshot, timestamp=now)
                    self.went_offline_at = None

                self.is_online = True
                self.last_snapshot = snapshot
                self.bot.hardware_monitor_dao.save_latest(snapshot, is_online=True)

                embed = self._build_embed(snapshot, now)
                message = await self.bot.messager.hardware_monitor_status(embed, self.banner_message_id)
                if message.id != self.banner_message_id:
                    self.banner_message_id = message.id
                    await self.bot.messager.log(
                        f"Creé el banner de hardware de la PC de Minecraft (mensaje {message.id}). Poné "
                        f"HARDWARE_MONITOR_STATUS_MESSAGE_ID={message.id} en el .env para que lo siga usando tras un reinicio."
                    )
            else:
                if self.is_online:
                    self.went_offline_at = now
                    await self.bot.messager.hardware_monitor_alert(self._crash_message())
                    self.bot.hardware_monitor_dao.log_transition(is_online=False, snapshot=self.last_snapshot, timestamp=now)

                self.is_online = False
                self.bot.hardware_monitor_dao.save_latest(self.last_snapshot, is_online=False)
        except Exception as e:
            await self.bot.messager.log(f"No pude chequear el hardware de la PC de Minecraft: {e}", level="ERROR", exc=e)

    def _crash_message(self) -> str:
        if self.last_snapshot is None:
            return "🔴 Se cayó la PC de Minecraft y no tengo métricas previas."
        s = self.last_snapshot
        temps = ""
        if s.cpu_temp_c is not None:
            temps += f" · CPU {s.cpu_temp_c:.0f}°C"
        if s.gpu_temp_c is not None:
            temps += f" · GPU {s.gpu_temp_c:.0f}°C"
        return (
            f"🔴 Se cayó la PC de Minecraft (no responde). Últimas métricas conocidas:\n"
            f"CPU {s.cpu_percent:.0f}% · RAM {s.ram_percent:.0f}% ({s.ram_used_gb:.1f}/{s.ram_total_gb:.1f} GB) · "
            f"Disco {s.disk_percent:.0f}%{temps}"
        )

    def _build_embed(self, snapshot: HardwareSnapshot, now: datetime) -> discord.Embed:
        embed = discord.Embed(title="🟢 PC de Minecraft", color=discord.Color.green())
        embed.add_field(name="CPU", value=f"{snapshot.cpu_percent:.0f}%", inline=True)
        embed.add_field(
            name="RAM",
            value=f"{snapshot.ram_percent:.0f}% ({snapshot.ram_used_gb:.1f}/{snapshot.ram_total_gb:.1f} GB)",
            inline=True
        )
        embed.add_field(name="Disco", value=f"{snapshot.disk_percent:.0f}%", inline=True)

        if snapshot.cpu_temp_c is not None or snapshot.gpu_temp_c is not None:
            temp_parts = []
            if snapshot.cpu_temp_c is not None:
                temp_parts.append(f"CPU {snapshot.cpu_temp_c:.0f}°C")
            if snapshot.gpu_temp_c is not None:
                temp_parts.append(f"GPU {snapshot.gpu_temp_c:.0f}°C")
            embed.add_field(name="Temperaturas", value=" · ".join(temp_parts), inline=True)

        embed.add_field(name="Uptime", value=format_duration(snapshot.uptime_seconds), inline=True)

        if snapshot.last_unclean_shutdown and (now - snapshot.last_unclean_shutdown) < timedelta(hours=2):
            embed.add_field(
                name="⚠️ Apagado inesperado",
                value=f"Windows detectó un apagado no controlado a las {snapshot.last_unclean_shutdown.strftime('%H:%M')}",
                inline=False
            )

        embed.set_footer(text=f"{settings.HARDWARE_MONITOR_HOST}:{settings.HARDWARE_MONITOR_PORT}")
        return embed


async def setup(bot):
    await bot.add_cog(HardwareMonitorCheckScheduler(bot))
