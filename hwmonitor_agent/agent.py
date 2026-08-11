"""
Agente HTTP mínimo para exponer métricas de hardware de una PC Windows
(CPU, RAM, disco, uptime, temperaturas, apagados no controlados y si está
corriendo ViewPower) para que Diablo Robot lo consulte por la VPN de
WireGuard.

Config vía variables de entorno:
  HWMON_PORT  - puerto donde escuchar (default 8788)
  HWMON_TOKEN - si se define, se exige el header 'X-Auth-Token' con este valor

Ver README.md para instrucciones de instalación y de cómo dejarlo corriendo
como Tarea Programada de Windows.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psutil
import win32evtlog

PORT = int(os.environ.get("HWMON_PORT", "8788"))
TOKEN = os.environ.get("HWMON_TOKEN", "")
LIBRE_HARDWARE_MONITOR_URL = "http://localhost:8085/data.json"
KERNEL_POWER_EVENT_ID = 41
KERNEL_POWER_SOURCE = "Microsoft-Windows-Kernel-Power"
VIEWPOWER_PROCESS_NAME = "ViewPower.exe"


def is_viewpower_running() -> bool:
    """Chequea si el proceso de ViewPower (monitoreo del UPS) está corriendo."""
    for process in psutil.process_iter(["name"]):
        try:
            if process.info["name"] and process.info["name"].lower() == VIEWPOWER_PROCESS_NAME.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _find_lhm_sensor(node: dict, name_fragment: str) -> float | None:
    """Recorre el árbol de sensores de LibreHardwareMonitor buscando una temperatura por nombre."""
    text = node.get("Text", "")
    value = node.get("Value", "")
    if name_fragment in text and "°C" in value:
        try:
            return float(value.replace("°C", "").strip())
        except ValueError:
            pass
    for child in node.get("Children", []):
        result = _find_lhm_sensor(child, name_fragment)
        if result is not None:
            return result
    return None


def get_temperatures() -> tuple[float | None, float | None]:
    """Lee temperaturas de CPU/GPU desde el Remote Web Server de LibreHardwareMonitor, si está corriendo."""
    try:
        with urllib.request.urlopen(LIBRE_HARDWARE_MONITOR_URL, timeout=2) as response:
            data = json.load(response)
    except Exception:
        return None, None

    cpu_temp = _find_lhm_sensor(data, "CPU Package")
    gpu_temp = _find_lhm_sensor(data, "GPU Core")
    return cpu_temp, gpu_temp


def get_last_unclean_shutdown() -> datetime | None:
    """Busca el Kernel-Power Event ID 41 más reciente (apagado no controlado) en el Event Log de Windows."""
    handle = win32evtlog.OpenEventLog(None, "System")
    try:
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        cutoff = datetime.now() - timedelta(days=30)
        checked = 0
        while checked < 5000:
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            if not events:
                break
            for event in events:
                checked += 1
                if event.TimeGenerated.replace(tzinfo=None) < cutoff:
                    return None
                event_id = event.EventID & 0xFFFF
                if event_id == KERNEL_POWER_EVENT_ID and event.SourceName == KERNEL_POWER_SOURCE:
                    return event.TimeGenerated.replace(tzinfo=None)
    finally:
        win32evtlog.CloseEventLog(handle)
    return None


def build_metrics() -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime_seconds = (datetime.now() - boot_time).total_seconds()
    cpu_temp, gpu_temp = get_temperatures()
    last_unclean_shutdown = get_last_unclean_shutdown()
    viewpower_running = is_viewpower_running()

    return {
        "cpu_percent": cpu_percent,
        "ram_percent": memory.percent,
        "ram_used_gb": round(memory.used / (1024 ** 3), 2),
        "ram_total_gb": round(memory.total / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "uptime_seconds": int(uptime_seconds),
        "boot_time": boot_time.isoformat(),
        "cpu_temp_c": cpu_temp,
        "gpu_temp_c": gpu_temp,
        "last_unclean_shutdown": last_unclean_shutdown.isoformat() if last_unclean_shutdown else None,
        "viewpower_running": viewpower_running,
    }


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return

        if TOKEN and self.headers.get("X-Auth-Token") != TOKEN:
            self.send_response(403)
            self.end_headers()
            return

        try:
            body = json.dumps(build_metrics()).encode("utf-8")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silencia el logging default de BaseHTTPRequestHandler


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), MetricsHandler)
    print(f"hwmonitor_agent escuchando en 0.0.0.0:{PORT} (token {'activado' if TOKEN else 'DESACTIVADO'})")
    server.serve_forever()
