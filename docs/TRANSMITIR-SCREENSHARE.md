# !transmitir — Screen share automático

## Estado actual

`bot/commands/transmitir.py` implementa el flujo completo:
- Abrir Chromium fullscreen con la URL vía subprocess
- Conectar al CDP (puerto 9222) y esperar el `<video>`
- Clickear el video y mandar tecla `f` para fullscreen del player
- Automatizar el Go Live de Discord en Firefox (`_start_screenshare` / `_stop_screenshare`), llamados desde `_start`/`_stop`
- `!transmitir APAGAR` / reemplazo limpio de stream

**Confirmado en el Pi real** (Raspberry Pi 5, Debian trixie, compositor `labwc` sobre Wayland):
- El bot corre como servicio de sistema (`diablo-robot.service`) con `User=frantek`, sin sesión gráfica propia — por eso hay que inyectarle `XDG_RUNTIME_DIR`/`WAYLAND_DISPLAY` a mano a los subprocess de `wlrctl`/`ydotool` (ver `_WAYLAND_ENV_DEFAULTS` en el código).
- `ydotool` viene de `trixie-backports` (no está en `trixie` main). `wlrctl` sí está en main.
- El daemon `ydotoold` corre como unit de usuario (`systemctl --user enable --now ydotool.service`), usando el `/dev/uinput` del grupo `input` (frantek ya pertenece a ese grupo).
- El screen share bajo Wayland pasa por `xdg-desktop-portal-wlr` (labwc lo prioriza vía `/usr/share/xdg-desktop-portal/labwc-portals.conf`, `default=wlr;*`). No hay `chooser_cmd` configurado, así que el portal no muestra un selector de ventana/output propio: en su lugar, el cursor pasa a modo crosshair y un solo click en cualquier punto de la pantalla confirma la única salida disponible.
- Firefox corre siempre maximizado a pantalla completa (1920x1080) de forma manual — de ahí que las coordenadas calibradas sean absolutas de pantalla, no relativas a la ventana (Wayland no expone geometría de ventanas ajenas a clientes arbitrarios).

### Flujo real de Go Live

1. Click en "Compartir pantalla" en la UI de Discord (dentro de Firefox)
2. Aparece el diálogo propio de Firefox ("Use system handler" + checkbox de notificaciones) → click en confirmar
3. El cursor pasa a crosshair (selección de output del portal `wlr`) → un click en cualquier lado confirma, porque hay un solo monitor
4. Empieza a compartir

### Flujo real de Stop

1. Click en "Dejar de compartir" en la UI de Discord

---

## Coordenadas calibradas

Todas son absolutas (pantalla 1920x1080, Firefox maximizado a full screen):

| Constante | Valor | Qué es |
|---|---|---|
| `_GO_LIVE_BUTTON_POS` | `(145, 987)` | Botón "Compartir pantalla" en el panel de voz de Discord |
| `_FIREFOX_SHARE_DIALOG_CONFIRM_POS` | `(750, 296)` | Botón de confirmar del diálogo "Use system handler" de Firefox |
| `_SCREEN_PICKER_CONFIRM_POS` | `(960, 540)` | Centro de pantalla — click "en cualquier lado" con el cursor en crosshair |
| `_STOP_STREAMING_BUTTON_POS` | `(338, 886)` | Botón "Dejar de compartir" |

---

## Recalibrar (si cambia la resolución o el layout de Discord)

`slurp` (ya instalado) deja dibujar un rectángulo en pantalla y devuelve sus coordenadas exactas por stdout — mucho más confiable que estimar a ojo desde una captura.

1. Con el elemento en cuestión visible en pantalla, corré en el Pi:
   ```bash
   slurp
   ```
2. Dibujá un rectángulo ajustado sobre el botón. Te va a imprimir algo como `106,970 78x33` (formato `X,Y WxH`).
3. El punto de click es el centro: `(X + W/2, Y + H/2)`.
4. Cargalo en la constante correspondiente y reiniciá el bot.

Para el diálogo de Firefox y el crosshair del portal, hace falta disparar el flujo real (click en Compartir pantalla) para que aparezcan y poder correr `slurp` sobre ellos. Para el botón de Stop, hace falta estar compartiendo ya.

Nota: si algún comando de terminal queda tapando Firefox al sacar una captura con `grim` (porque es la terminal la que dispara el comando), usar `(sleep 3 && grim archivo.png) &` y cambiar el foco a Firefox durante esos 3 segundos.

---

## Consideraciones

- **Go Live solo aparece estando en un canal de voz**: el proxy (`not_robot_devil`) tiene que estar en un canal de voz para que el botón exista. Si no está en voz cuando se manda `!transmitir`, el click va a caer en un lugar sin el botón.

- **Fragilidad de coordenadas absolutas**: si Firefox deja de estar maximizado a pantalla completa, cambia la resolución, o Discord rediseña su UI, hay que recalibrar con `slurp` (ver arriba).

- **Dependencias del sistema en el Pi**: `wlrctl` (apt, main), `ydotool` (apt, `trixie-backports`) + `ydotoold` corriendo (`systemctl --user status ydotool.service`), `slurp` (apt, main). Todas ya instaladas y verificadas.

- **Puerto CDP**: el stream usa el puerto 9222. Si en algún momento se quiere controlar también Firefox via CDP (alternativa a wlrctl/ydotool), usar un puerto distinto (ej. 9223). Por ahora no es necesario.
