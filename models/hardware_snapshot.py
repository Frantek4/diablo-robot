from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from utils.date_format import parse_datetime


HIGH_LATENCY_MS = 150
HIGH_VPN_LATENCY_MS = 250


@dataclass
class NetworkSnapshot:
    """Performance de internet medida desde la PC de Minecraft (la mide el agente, no el bot)."""
    measured_at: Optional[datetime] = None
    gateway_target: Optional[str] = None
    gateway_latency_ms: Optional[float] = None
    gateway_loss_percent: Optional[float] = None
    internet_target: Optional[str] = None
    internet_latency_ms: Optional[float] = None
    internet_jitter_ms: Optional[float] = None
    internet_loss_percent: Optional[float] = None
    dns_ms: Optional[float] = None
    recv_mbps: Optional[float] = None
    sent_mbps: Optional[float] = None
    download_mbps: Optional[float] = None
    download_at: Optional[datetime] = None

    @property
    def internet_online(self) -> bool:
        return self.internet_loss_percent is not None and self.internet_loss_percent < 100

    @property
    def is_degraded(self) -> bool:
        """Hay microcortes o lentitud: se pierden paquetes, la latencia se disparó o el DNS no responde."""
        return (
            (self.internet_loss_percent or 0) > 0
            or (self.internet_latency_ms or 0) > HIGH_LATENCY_MS
            or (self.gateway_loss_percent or 0) > 0
            or self.dns_ms is None
        )

    def to_dict(self) -> dict:
        return {
            "measured_at": self.measured_at,
            "gateway_target": self.gateway_target,
            "gateway_latency_ms": self.gateway_latency_ms,
            "gateway_loss_percent": self.gateway_loss_percent,
            "internet_target": self.internet_target,
            "internet_latency_ms": self.internet_latency_ms,
            "internet_jitter_ms": self.internet_jitter_ms,
            "internet_loss_percent": self.internet_loss_percent,
            "dns_ms": self.dns_ms,
            "recv_mbps": self.recv_mbps,
            "sent_mbps": self.sent_mbps,
            "download_mbps": self.download_mbps,
            "download_at": self.download_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NetworkSnapshot':
        return cls(
            measured_at=parse_datetime(data["measured_at"]) if data.get("measured_at") else None,
            gateway_target=data.get("gateway_target"),
            gateway_latency_ms=data.get("gateway_latency_ms"),
            gateway_loss_percent=data.get("gateway_loss_percent"),
            internet_target=data.get("internet_target"),
            internet_latency_ms=data.get("internet_latency_ms"),
            internet_jitter_ms=data.get("internet_jitter_ms"),
            internet_loss_percent=data.get("internet_loss_percent"),
            dns_ms=data.get("dns_ms"),
            recv_mbps=data.get("recv_mbps"),
            sent_mbps=data.get("sent_mbps"),
            download_mbps=data.get("download_mbps"),
            download_at=parse_datetime(data["download_at"]) if data.get("download_at") else None,
        )


@dataclass
class VpnLink:
    """Calidad del túnel de WireGuard medida por el bot contra el agente (el bot siempre llega por VPN)."""
    latency_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    loss_percent: float = 100.0

    @property
    def is_degraded(self) -> bool:
        return self.loss_percent > 0 or (self.latency_ms or 0) > HIGH_VPN_LATENCY_MS

    def to_dict(self) -> dict:
        return {
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "loss_percent": self.loss_percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'VpnLink':
        return cls(
            latency_ms=data.get("latency_ms"),
            jitter_ms=data.get("jitter_ms"),
            loss_percent=data.get("loss_percent", 100.0),
        )


@dataclass
class HardwareSnapshot:
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_percent: float
    uptime_seconds: int
    boot_time: datetime
    cpu_temp_c: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    last_unclean_shutdown: Optional[datetime] = None
<<<<<<< HEAD
    network: Optional[NetworkSnapshot] = None
    vpn_link: Optional[VpnLink] = None
=======
    viewpower_running: Optional[bool] = None
>>>>>>> c4acb75fe2ee782e1fb9c1799de30ac2788928cb

    def to_dict(self) -> dict:
        return {
            "cpu_percent": self.cpu_percent,
            "ram_percent": self.ram_percent,
            "ram_used_gb": self.ram_used_gb,
            "ram_total_gb": self.ram_total_gb,
            "disk_percent": self.disk_percent,
            "uptime_seconds": self.uptime_seconds,
            "boot_time": self.boot_time,
            "cpu_temp_c": self.cpu_temp_c,
            "gpu_temp_c": self.gpu_temp_c,
            "last_unclean_shutdown": self.last_unclean_shutdown,
<<<<<<< HEAD
            "network": self.network.to_dict() if self.network else None,
            "vpn_link": self.vpn_link.to_dict() if self.vpn_link else None,
=======
            "viewpower_running": self.viewpower_running,
>>>>>>> c4acb75fe2ee782e1fb9c1799de30ac2788928cb
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'HardwareSnapshot':
        return cls(
            cpu_percent=data["cpu_percent"],
            ram_percent=data["ram_percent"],
            ram_used_gb=data["ram_used_gb"],
            ram_total_gb=data["ram_total_gb"],
            disk_percent=data["disk_percent"],
            uptime_seconds=data["uptime_seconds"],
            boot_time=parse_datetime(data["boot_time"]),
            cpu_temp_c=data.get("cpu_temp_c"),
            gpu_temp_c=data.get("gpu_temp_c"),
            last_unclean_shutdown=parse_datetime(data["last_unclean_shutdown"]) if data.get("last_unclean_shutdown") else None,
<<<<<<< HEAD
            network=NetworkSnapshot.from_dict(data["network"]) if data.get("network") else None,
            vpn_link=VpnLink.from_dict(data["vpn_link"]) if data.get("vpn_link") else None,
=======
            viewpower_running=data.get("viewpower_running"),
>>>>>>> c4acb75fe2ee782e1fb9c1799de30ac2788928cb
        )


def format_duration(seconds: float) -> str:
    """Formatea segundos como '2d 4h 12m' (o '45m' si es menos de una hora)."""
    total_minutes = int(seconds // 60)
    days, rem_minutes = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem_minutes, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)
