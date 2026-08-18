"""
Agente HTTP mínimo para exponer métricas de hardware y de red de una PC Windows
(CPU, RAM, disco, uptime, temperaturas, apagados no controlados, si está
corriendo ViewPower y performance de internet) para que Diablo Robot lo
consulte por la VPN de WireGuard.

Config vía variables de entorno:
  HWMON_PORT               - puerto donde escuchar (default 8788)
  HWMON_TOKEN              - si se define, se exige el header 'X-Auth-Token' con este valor
  HWMON_GATEWAY            - host:puerto del router para medir el tramo local (default 192.168.0.1:80)
  HWMON_INTERNET_TARGET    - host:puerto público para medir internet (default 1.1.1.1:443)
  HWMON_DNS_PROBE_HOST     - dominio a resolver para medir el DNS (default www.google.com)
  HWMON_SPEEDTEST_MINUTES  - cada cuánto correr el test de velocidad, 0 lo desactiva (default 60)
  HWMON_SPEEDTEST_URL      - URL de descarga del test de velocidad (default Cloudflare, 10 MB)

Ver README.md para instrucciones de instalación y de cómo dejarlo corriendo
como Tarea Programada de Windows.
"""
import json
import os
import socket
import statistics
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psutil
import win32evtlog

PORT = int(os.environ.get("HWMON_PORT", "8788"))
TOKEN = os.environ.get("HWMON_TOKEN", "")
GATEWAY_TARGET = os.environ.get("HWMON_GATEWAY", "192.168.0.1:80")
INTERNET_TARGET = os.environ.get("HWMON_INTERNET_TARGET", "1.1.1.1:443")
DNS_PROBE_HOST = os.environ.get("HWMON_DNS_PROBE_HOST", "www.google.com")
SPEEDTEST_MINUTES = int(os.environ.get("HWMON_SPEEDTEST_MINUTES", "60"))
SPEEDTEST_URL = os.environ.get(
    "HWMON_SPEEDTEST_URL", "https://speed.cloudflare.com/__down?bytes=10000000"
)
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

NETWORK_PROBE_SECONDS = 30
PROBE_SAMPLES = 4
PROBE_TIMEOUT_SECONDS = 2.0
SPEEDTEST_TIMEOUT_SECONDS = 20

_network_state: dict | None = None
_network_lock = threading.Lock()


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


def _parse_target(target: str, default_port: int) -> tuple[str, int]:
    host, _, port = target.rpartition(":")
    if not host:
        return target, default_port
    try:
        return host, int(port)
    except ValueError:
        return target, default_port


def _tcp_latency_ms(host: str, port: int) -> float | None:
    """Mide el RTT de un handshake TCP. Uso TCP y no ICMP para no depender de permisos ni de parsear ping.exe."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_SECONDS):
            return (time.perf_counter() - start) * 1000
    except OSError:
        return None


def _probe_target(target: str, default_port: int, samples: int) -> dict:
    """Devuelve latencia promedio, jitter y % de pérdida contra un host:puerto."""
    host, port = _parse_target(target, default_port)
    latencies = [_tcp_latency_ms(host, port) for _ in range(samples)]
    ok = [latency for latency in latencies if latency is not None]

    return {
        "latency_ms": round(statistics.mean(ok), 1) if ok else None,
        "jitter_ms": round(statistics.stdev(ok), 1) if len(ok) > 1 else (0.0 if ok else None),
        "loss_percent": round(100 * (samples - len(ok)) / samples, 1),
    }


def _dns_latency_ms() -> float | None:
    """Mide cuánto tarda en resolverse un dominio (ojo: Windows cachea, así que sirve más para detectar caídas)."""
    start = time.perf_counter()
    try:
        socket.getaddrinfo(DNS_PROBE_HOST, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return None
    return round((time.perf_counter() - start) * 1000, 1)


def _run_speedtest() -> float | None:
    """Descarga un archivo de prueba y devuelve la velocidad en Mbps. None si falla."""
    downloaded = 0
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(SPEEDTEST_URL, timeout=SPEEDTEST_TIMEOUT_SECONDS) as response:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                downloaded += len(chunk)
                if time.perf_counter() - start > SPEEDTEST_TIMEOUT_SECONDS:
                    break
    except Exception:
        return None

    elapsed = time.perf_counter() - start
    if not downloaded or elapsed <= 0:
        return None
    return round((downloaded * 8) / elapsed / 1_000_000, 1)


def network_probe_loop():
    """Mide la red en background y cachea el resultado, así GET /metrics sigue respondiendo al toque."""
    global _network_state

    last_counters = psutil.net_io_counters()
    last_time = time.monotonic()
    download_mbps = None
    download_at = None

    while True:
        try:
            gateway = _probe_target(GATEWAY_TARGET, 80, PROBE_SAMPLES)
            internet = _probe_target(INTERNET_TARGET, 443, PROBE_SAMPLES)
            dns_ms = _dns_latency_ms()

            counters = psutil.net_io_counters()
            now = time.monotonic()
            elapsed = max(now - last_time, 1e-6)
            recv_mbps = round((counters.bytes_recv - last_counters.bytes_recv) * 8 / elapsed / 1_000_000, 2)
            sent_mbps = round((counters.bytes_sent - last_counters.bytes_sent) * 8 / elapsed / 1_000_000, 2)
            last_counters, last_time = counters, now

            speedtest_due = download_at is None or (datetime.now() - download_at) >= timedelta(minutes=SPEEDTEST_MINUTES)
            if SPEEDTEST_MINUTES > 0 and internet["loss_percent"] < 100 and speedtest_due:
                result = _run_speedtest()
                if result is not None:
                    download_mbps = result
                    download_at = datetime.now()
                # el test satura la línea: reseteo el baseline para no ensuciar el throughput del próximo ciclo
                last_counters, last_time = psutil.net_io_counters(), time.monotonic()

            with _network_lock:
                _network_state = {
                    "measured_at": datetime.now().isoformat(),
                    "gateway_target": GATEWAY_TARGET,
                    "gateway_latency_ms": gateway["latency_ms"],
                    "gateway_loss_percent": gateway["loss_percent"],
                    "internet_target": INTERNET_TARGET,
                    "internet_latency_ms": internet["latency_ms"],
                    "internet_jitter_ms": internet["jitter_ms"],
                    "internet_loss_percent": internet["loss_percent"],
                    "dns_ms": dns_ms,
                    "recv_mbps": recv_mbps,
                    "sent_mbps": sent_mbps,
                    "download_mbps": download_mbps,
                    "download_at": download_at.isoformat() if download_at else None,
                }
        except Exception as e:
            print(f"error midiendo la red: {e}")

        time.sleep(NETWORK_PROBE_SECONDS)


def get_network() -> dict | None:
    with _network_lock:
        return dict(_network_state) if _network_state else None


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
        "network": get_network(),
    }


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/metrics", "/ping"):
            self.send_response(404)
            self.end_headers()
            return

        if TOKEN and self.headers.get("X-Auth-Token") != TOKEN:
            self.send_response(403)
            self.end_headers()
            return

        if self.path == "/ping":
            # respuesta lo más barata posible: con esto el bot mide el RTT del túnel de WireGuard
            self._respond(b"pong", "text/plain")
            return

        try:
            body = json.dumps(build_metrics()).encode("utf-8")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
            return

        self._respond(body, "application/json")

    def _respond(self, body: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silencia el logging default de BaseHTTPRequestHandler


if __name__ == "__main__":
    threading.Thread(target=network_probe_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), MetricsHandler)
    print(f"hwmonitor_agent escuchando en 0.0.0.0:{PORT} (token {'activado' if TOKEN else 'DESACTIVADO'})")
    server.serve_forever()
