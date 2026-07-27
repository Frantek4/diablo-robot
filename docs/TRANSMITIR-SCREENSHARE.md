# !transmitir — Screen share pendiente

## Estado actual

`bot/commands/transmitir.py` ya implementa:
- Abrir Chromium fullscreen con la URL vía subprocess
- Conectar al CDP (puerto 9222) y esperar el `<video>`
- Clickear el video y mandar tecla `f` para fullscreen del player
- `!transmitir APAGAR` / reemplazo limpio de stream

**Lo que falta:** que Discord haga Go Live automáticamente al arrancar el stream (y lo detenga al apagar).

---

## Paso 0: determinar display server

El bot corre en TTY (`XDG_SESSION_TYPE=tty`), así que hay que verificar la sesión gráfica por separado.

Desde una terminal **en el escritorio del Pi** (no SSH):
```bash
echo $XDG_SESSION_TYPE
```

- `x11` → usar **xdotool** (`sudo apt install xdotool`)
- `wayland` → usar **ydotool** (`sudo apt install ydotool`)

---

## Implementación

### Flujo completo de `!transmitir <url>`

1. Llamar a `_stop()` (mata stream anterior + detiene screen share si hay)
2. Abrir Chromium con el stream (código existente)
3. Usar xdotool/ydotool para:
   a. Encontrar la ventana de Firefox (Discord proxy)
   b. Clickear el botón **Go Live** en la UI de Discord
   c. En el diálogo del browser, seleccionar **Entire Screen** y confirmar

### Flujo de `!transmitir APAGAR`

1. Usar xdotool/ydotool para clickear **Stop Streaming** en Discord (Firefox)
2. Matar el proceso de Chromium (código existente)

---

## Cambios en transmitir.py

Agregar al `__init__` de `TransmitirCommand`:
```python
self._tool = "xdotool"  # o "ydotool" según el resultado del Paso 0
```

Agregar método `_find_discord_window()`:
```python
# xdotool: xdotool search --name "Discord"
# ydotool: diferente API, ver docs
```

Agregar métodos `_start_screenshare()` y `_stop_screenshare()` que:
- Encuentren la ventana de Firefox con Discord
- Clickeen Go Live / Stop Streaming
- Manejen el diálogo de captura de pantalla

Modificar `_start()` para llamar `_start_screenshare()` después de abrir el stream.
Modificar `_stop()` para llamar `_stop_screenshare()` antes de matar Chromium.

---

## Consideraciones

- **DISPLAY / WAYLAND_DISPLAY**: xdotool/ydotool necesitan saber a qué display apuntar cuando se llaman desde el contexto TTY del bot. Pasar `DISPLAY=:0` en el env del subprocess (igual que hacemos con Chromium).

- **Go Live solo aparece estando en un canal de voz**: el proxy tiene que estar en un canal de voz para que el botón exista. Si el proxy no está en voz cuando se manda `!transmitir`, el screen share va a fallar silenciosamente. Decidir si: (a) el bot mueve al proxy a un canal fijo antes de hacer Go Live, o (b) simplemente se loguea el fallo.

- **Posición del botón**: los clicks por coordenadas absolutas son frágiles si la ventana se mueve o cambia de tamaño. Preferir `xdotool search` + clicks relativos a la ventana, o buscar por imagen con `import`/`scrot` + template matching si las coordenadas no son confiables.

- **Puerto CDP**: el stream usa el puerto 9222. Si en algún momento se quiere controlar también Firefox via CDP (alternativa a xdotool), usar un puerto distinto (ej. 9223). Por ahora no es necesario.
