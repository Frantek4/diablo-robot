# hwmonitor_agent

Agente HTTP mínimo para Windows que expone métricas de hardware (CPU, RAM,
disco, uptime, temperaturas, apagados no controlados y si está corriendo
ViewPower) en `GET /metrics`, para que Diablo Robot lo consulte por la VPN de
WireGuard y mantenga el banner de estado en el canal de admin (`#robot-devil`).

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
  "viewpower_running": true
}
```

`last_unclean_shutdown` es la fecha del Kernel-Power Event ID 41 más reciente
encontrado en los últimos 30 días del Event Log de System — es la señal más
directa de un cuelgue/crash de hardware (a diferencia de un apagado
prendido/apagado normal, que no genera ese evento). El bot lo usa para marcar
en el banner cuando el apagado inesperado fue reciente.

`viewpower_running` indica si el proceso `ViewPower.exe` (monitoreo del UPS)
está corriendo en esa PC. El agente lo busca por nombre entre los procesos
activos con `psutil`; si en algún momento se reinstala ViewPower con otro
nombre de ejecutable, hay que actualizar `VIEWPOWER_PROCESS_NAME` en
`agent.py`. El bot marca una advertencia en el banner cuando está en `false`.
