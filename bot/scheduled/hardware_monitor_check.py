import discord
from datetime import datetime, timedelta
from discord.ext import commands, tasks

from config.settings import settings
from integrations import hardware_monitor
from models.hardware_snapshot import HardwareSnapshot, NetworkSnapshot, VpnLink, format_duration
from utils.date_format import format_datetime, format_time, parse_datetime

INTERNET_FAILURES_BEFORE_ALERT = 2


class HardwareMonitorCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.banner_message_id = settings.HARDWARE_MONITOR_STATUS_MESSAGE_ID

        state = self.bot.hardware_monitor_dao.get_latest()
        self.is_online = state["is_online"] if state else True
        self.last_snapshot = HardwareSnapshot.from_dict(state["snapshot"]) if state and state.get("snapshot") else None
        self.internet_online = state.get("internet_online", True) if state else True
        self.last_heartbeat = parse_datetime(state["last_heartbeat"]) if state and state.get("last_heartbeat") else None
        self.went_offline_at = None
        self.internet_went_offline_at = None
        self.internet_failures = 0

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
                snapshot.vpn_link = await hardware_monitor.measure_vpn_link()

                if not self.is_online:
                    since = self.went_offline_at or self.last_heartbeat
                    downtime = (
                        f" (estuvo caída {format_duration((now - since).total_seconds())})"
                        if since else ""
                    )
                    await self.bot.messager.hardware_monitor_alert(f"✅ Volvió la PC de Minecraft{downtime}.")
                    self.bot.hardware_monitor_dao.log_transition(is_online=True, snapshot=snapshot, timestamp=now)
                    self.went_offline_at = None

                self.is_online = True
                self.last_snapshot = snapshot
                self.last_heartbeat = now
                await self._check_network(snapshot, now)
                self.bot.hardware_monitor_dao.save_latest(
                    snapshot, is_online=True, internet_online=self.internet_online, last_heartbeat=now
                )

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
                    await self.bot.messager.hardware_monitor_alert(self._crash_message(now))
                    self.bot.hardware_monitor_dao.log_transition(is_online=False, snapshot=self.last_snapshot, timestamp=now)

                self.is_online = False
                self.internet_failures = 0
                self.bot.hardware_monitor_dao.save_latest(
                    self.last_snapshot, is_online=False, internet_online=self.internet_online,
                    last_heartbeat=self.last_heartbeat
                )
        except Exception as e:
            await self.bot.messager.log(f"No pude chequear el hardware de la PC de Minecraft: {e}", level="ERROR", exc=e)

    async def _check_network(self, snapshot: HardwareSnapshot, now: datetime):
        """Avisa cuando se cae o vuelve internet en la PC, y deja registro de los microcortes."""
        network = snapshot.network
        if network is None:
            return

        if network.internet_online:
            self.internet_failures = 0
            if not self.internet_online:
                downtime = (
                    f" (estuvo {format_duration((now - self.internet_went_offline_at).total_seconds())} sin conexión)"
                    if self.internet_went_offline_at else ""
                )
                await self.bot.messager.hardware_monitor_alert(
                    f"🌐 Volvió internet en la PC de Minecraft{downtime}. {self._internet_summary(network)}".strip()
                )
                self.internet_online = True
                self.internet_went_offline_at = None
                self.bot.hardware_monitor_dao.log_transition(
                    is_online=True, snapshot=snapshot, timestamp=now, subject="internet"
                )
            elif network.is_degraded or (snapshot.vpn_link and snapshot.vpn_link.is_degraded):
                # los microcortes no ameritan aviso cada minuto, pero sí quedan registrados para después
                self.bot.hardware_monitor_dao.log_degradation(snapshot, timestamp=now)
            return

        self.internet_failures += 1
        if self.internet_online and self.internet_failures >= INTERNET_FAILURES_BEFORE_ALERT:
            self.internet_online = False
            self.internet_went_offline_at = now
            await self.bot.messager.hardware_monitor_alert(
                f"🌐 Se cayó internet en la PC de Minecraft (la PC responde, pero no llega a "
                f"{network.internet_target or 'internet'}). El túnel de WireGuard sigue en pie, así que es la "
                f"conexión de la casa, no la VPN."
            )
            self.bot.hardware_monitor_dao.log_transition(
                is_online=False, snapshot=snapshot, timestamp=now, subject="internet"
            )

    def _internet_summary(self, network: NetworkSnapshot) -> str:
        if network.internet_latency_ms is None:
            return ""
        return f"Ping {network.internet_latency_ms:.0f} ms · pérdida {network.internet_loss_percent:.0f}%."

    def _heartbeat_line(self, now: datetime) -> str:
        if self.last_heartbeat is None:
            return "No tengo registro de la última vez que me contestó."
        return (
            f"Último heartbeat: {format_datetime(self.last_heartbeat)} "
            f"(hace {format_duration((now - self.last_heartbeat).total_seconds())})"
        )

    def _crash_message(self, now: datetime) -> str:
        heartbeat = self._heartbeat_line(now)
        if self.last_snapshot is None:
            return f"🔴 Se cayó la PC de Minecraft y no tengo métricas previas.\n{heartbeat}"
        s = self.last_snapshot
        temps = ""
        if s.cpu_temp_c is not None:
            temps += f" · CPU {s.cpu_temp_c:.0f}°C"
        if s.gpu_temp_c is not None:
            temps += f" · GPU {s.gpu_temp_c:.0f}°C"
        network_lines = []
        if s.network is not None and s.network.internet_latency_ms is not None:
            network_lines.append(
                f"Internet antes de caerse: ping {s.network.internet_latency_ms:.0f} ms · "
                f"pérdida {s.network.internet_loss_percent:.0f}%"
            )
        if s.vpn_link is not None and s.vpn_link.latency_ms is not None:
            network_lines.append(
                f"VPN antes de caerse: ping {s.vpn_link.latency_ms:.0f} ms · "
                f"pérdida {s.vpn_link.loss_percent:.0f}%"
            )
        network = ("\n" + "\n".join(network_lines)) if network_lines else ""
        return (
            f"🔴 No me responde más la PC de Minecraft por la VPN (puede estar colgada la PC o caído el túnel). "
            f"Últimas métricas conocidas:\n"
            f"CPU {s.cpu_percent:.0f}% · RAM {s.ram_percent:.0f}% ({s.ram_used_gb:.1f}/{s.ram_total_gb:.1f} GB) · "
            f"Disco {s.disk_percent:.0f}%{temps}{network}\n{heartbeat}"
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


        self._add_internet_field(embed, snapshot.network, self._recent_microcuts(now))
        self._add_vpn_field(embed, snapshot.vpn_link)
        if snapshot.viewpower_running is not None:
            embed.add_field(
                name="ViewPower",
                value="✅ ON" if snapshot.viewpower_running else "⚠️ OFF",
                inline=True
            )

        if snapshot.last_unclean_shutdown and (now - snapshot.last_unclean_shutdown) < timedelta(hours=2):
            embed.add_field(
                name="⚠️ Apagado inesperado",
                value=f"Windows detectó un apagado no controlado a las {format_time(snapshot.last_unclean_shutdown)}",
                inline=False
            )

        heartbeat = format_datetime(self.last_heartbeat) if self.last_heartbeat else "—"
        embed.set_footer(
            text=f"{settings.HARDWARE_MONITOR_HOST}:{settings.HARDWARE_MONITOR_PORT} · último heartbeat {heartbeat}"
        )
        return embed

    def _recent_microcuts(self, now: datetime) -> int:
        return len(self.bot.hardware_monitor_dao.get_recent_degradations(now - timedelta(hours=24)))

    def _add_internet_field(self, embed: discord.Embed, network: NetworkSnapshot | None, microcuts: int):
        if network is None:
            embed.add_field(name="🌐 Internet", value="Todavía no tengo mediciones de red.", inline=False)
            return

        if not network.internet_online:
            embed.add_field(
                name="🔴 Internet",
                value=f"Sin conexión a {network.internet_target or 'internet'} (la PC anda, la línea no).",
                inline=False
            )
            return

        lines = [
            f"Ping {network.internet_latency_ms:.0f} ms · jitter {network.internet_jitter_ms:.0f} ms · "
            f"pérdida {network.internet_loss_percent:.0f}%"
        ]

        local = []
        if network.gateway_latency_ms is not None:
            local.append(f"Router {network.gateway_latency_ms:.0f} ms")
            if network.gateway_loss_percent:
                local.append(f"pérdida al router {network.gateway_loss_percent:.0f}%")
        elif network.gateway_loss_percent:
            local.append("Router sin respuesta")
        local.append(f"DNS {network.dns_ms:.0f} ms" if network.dns_ms is not None else "DNS no responde")
        lines.append(" · ".join(local))

        traffic = f"Tráfico ↓{network.recv_mbps:.1f} / ↑{network.sent_mbps:.1f} Mbps"
        if network.download_mbps is not None:
            traffic += f" · Bajada {network.download_mbps:.0f} Mbps"
            if network.download_at:
                traffic += f" ({format_time(network.download_at)})"
        lines.append(traffic)

        if microcuts:
            lines.append(f"Microcortes en las últimas 24 h: {microcuts}")

        embed.add_field(
            name="⚠️ Internet" if network.is_degraded else "🌐 Internet",
            value="\n".join(lines),
            inline=False
        )

    def _add_vpn_field(self, embed: discord.Embed, link: VpnLink | None):
        if link is None:
            return

        if link.latency_ms is None:
            value = "El agente respondió las métricas pero no el ping: el túnel está inestable."
        else:
            value = (
                f"Ping {link.latency_ms:.0f} ms · jitter {link.jitter_ms:.0f} ms · pérdida {link.loss_percent:.0f}%"
            )

        embed.add_field(
            name="⚠️ VPN (WireGuard)" if link.is_degraded else "🔒 VPN (WireGuard)",
            value=value,
            inline=False
        )


async def setup(bot):
    await bot.add_cog(HardwareMonitorCheckScheduler(bot))
