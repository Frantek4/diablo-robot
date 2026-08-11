from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from utils.date_format import parse_datetime


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
    viewpower_running: Optional[bool] = None

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
            "viewpower_running": self.viewpower_running,
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
            viewpower_running=data.get("viewpower_running"),
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
