# hwmonitor_agent

Agente HTTP mínimo para Windows que expone métricas de hardware (CPU, RAM,
<<<<<<< HEAD
disco, uptime, temperaturas y apagados no controlados) y de red (latencia,
jitter, pérdida de paquetes, DNS, tráfico y velocidad de bajada) en
`GET /metrics`, para que Diablo Robot lo consulte por la VPN de WireGuard y
mantenga el banner de estado en el canal de admin (`#robot-devil`).

También expone `GET /ping`, que devuelve `pong` sin hacer nada más: el bot lo
usa para medir la latencia, el jitter y la pérdida del túnel de WireGuard sin
que el tiempo de armado de las métricas ensucie la medición.
=======
disco, uptime, temperaturas, apagados no controlados y si está corriendo
ViewPower) en `GET /metrics`, para que Diablo Robot lo consulte por la VPN de
WireGuard y mantenga el banner de estado en el canal de admin (`#robot-devil`).
>>>>>>> c4acb75fe2ee782e1fb9c1799de30ac2788928cb

Corre en la PC que hostea Minecraft, **no** en la máquina donde vive el bot.

## Instalación

1. Instalar Python 3.10+ en la PC de Minecraft (si no está ya).
2. Instalar dependencias:
   ```
   pip install -r requirements.txt
   ```
3. (Opcional, para temperaturas de CPU/GPU) Instalar
   [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
   y habilitar el **Remote Web Server** desde `Options > Remote Web Server >
   Run` (puerto por defecto 8085). Si no está corriendo, el agente sigue
   funcionando normal, solo que `cpu_temp_c`/`gpu_temp_c` van a venir en
   `null`.
4. Configurar variables de entorno antes de arrancar (o setearlas en la Tarea
   Programada del paso siguiente):
   - `HWMON_PORT` (default `8788`)
   - `HWMON_TOKEN` — token compartido que el bot va a mandar en el header
     `X-Auth-Token`. Tiene que ser el mismo valor que `HARDWARE_MONITOR_TOKEN`
     en el `.env` del bot. Si se deja vacío, el endpoint queda sin auth (solo
     aceptable porque ya está restringido a la VPN).
   - `HWMON_GATEWAY` (default `192.168.0.1:80`) — router de la casa, para
     separar "se cayó internet" de "se cayó la red local".
   - `HWMON_INTERNET_TARGET` (default `1.1.1.1:443`) — host público contra el
     que se mide latencia/jitter/pérdida.
   - `HWMON_DNS_PROBE_HOST` (default `www.google.com`) — dominio que se
     resuelve para medir el DNS.
   - `HWMON_SPEEDTEST_MINUTES` (default `60`, `0` lo desactiva) y
     `HWMON_SPEEDTEST_URL` (default: 10 MB de Cloudflare) — test de velocidad
     de bajada. Cada corrida satura la línea uno o dos segundos, así que
     conviene no bajar mucho el intervalo mientras haya gente jugando.
5. Probar manualmente:
   ```
   python agent.py
   ```
   y en otra terminal (o desde la PC del bot, si ya está en la VPN):
   ```
   curl http://<ip-o-host-de-esta-pc-en-la-vpn>:8788/metrics -H "X-Auth-Token: <token>"
   ```

## Dejarlo corriendo siempre (Tarea Programada de Windows)

Como la PC se cuelga de forma no controlada, el agente tiene que arrancar
solo en cada boot, sin depender de que alguien inicie sesión:

1. Abrir el **Programador de tareas** (Task Scheduler).
2. Crear tarea (no "tarea básica") con:
   - **Desencadenador**: Al iniciar el sistema.
   - **Acción**: Iniciar un programa → `python.exe` (ruta completa) con
     argumento la ruta completa a `agent.py`.
   - **Configurar**: "Ejecutar tanto si el usuario inició sesión como si no"
     y "Ejecutar con los privilegios más altos" (necesario para leer el
     Event Log de System sin restricciones).
   - En la pestaña "Entorno"/variables, o via un `.bat` wrapper, setear
     `HWMON_PORT`/`HWMON_TOKEN` antes de invocar `python agent.py`.

## Qué expone `/metrics`

```json
{
  "cpu_percent": 23.4,
  "ram_percent": 61.2,
  "ram_used_gb": 9.8,
  "ram_total_gb": 16.0,
  "disk_percent": 72.1,
  "uptime_seconds": 123456,
  "boot_time": "2026-07-30T08:12:00",
  "cpu_temp_c": 54.3,
  "gpu_temp_c": 48.1,
  "last_unclean_shutdown": "2026-07-30T08:11:52",
<<<<<<< HEAD
  "network": {
    "measured_at": "2026-08-14T17:20:31",
    "gateway_target": "192.168.0.1:80",
    "gateway_latency_ms": 1.4,
    "gateway_loss_percent": 0.0,
    "internet_target": "1.1.1.1:443",
    "internet_latency_ms": 12.7,
    "internet_jitter_ms": 2.3,
    "internet_loss_percent": 0.0,
    "dns_ms": 18.2,
    "recv_mbps": 1.24,
    "sent_mbps": 0.41,
    "download_mbps": 87.5,
    "download_at": "2026-08-14T16:51:02"
  }
=======
  "viewpower_running": true
>>>>>>> c4acb75fe2ee782e1fb9c1799de30ac2788928cb
}
```

`last_unclean_shutdown` es la fecha del Kernel-Power Event ID 41 más reciente
encontrado en los últimos 30 días del Event Log de System — es la señal más
directa de un cuelgue/crash de hardware (a diferencia de un apagado
prendido/apagado normal, que no genera ese evento). El bot lo usa para marcar
en el banner cuando el apagado inesperado fue reciente.

<<<<<<< HEAD
## Cómo se mide la red

Un thread aparte mide cada 30 segundos y deja el resultado cacheado, así
`GET /metrics` responde al toque y no arrastra el tiempo de las mediciones
(`network` viene en `null` hasta la primera vuelta).

Las latencias se miden con handshakes TCP (4 intentos por ciclo) en vez de
ICMP: no necesita permisos especiales ni parsear la salida traducida de
`ping.exe`. Los intentos que fallan cuentan como pérdida, que es lo que
delata los microcortes. `dns_ms` sirve sobre todo para detectar que el DNS
dejó de responder — Windows cachea las resoluciones, así que el número fino no
dice tanto.

`recv_mbps`/`sent_mbps` son el tráfico real que pasó por las interfaces en el
último ciclo (no es capacidad, es uso); `download_mbps` sí es una medición de
capacidad y se refresca cada `HWMON_SPEEDTEST_MINUTES`.
=======
`viewpower_running` indica si el proceso `ViewPower.exe` (monitoreo del UPS)
está corriendo en esa PC. El agente lo busca por nombre entre los procesos
activos con `psutil`; si en algún momento se reinstala ViewPower con otro
nombre de ejecutable, hay que actualizar `VIEWPOWER_PROCESS_NAME` en
`agent.py`. El bot marca una advertencia en el banner cuando está en `false`.
>>>>>>> c4acb75fe2ee782e1fb9c1799de30ac2788928cb
