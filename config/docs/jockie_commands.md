# Comandos de Jockie Music (prefijo: {prefix})

## Reproducir
- `{prefix}p <artista - título>` — encolar una canción
- `{prefix}p <URL>` — reproducir desde URL (Spotify, YouTube, Deezer, Apple Music, Tidal, SoundCloud)
- `{prefix}p <término> --insert` — insertar justo después de la canción actual
- `{prefix}p <término> --now` — reproducir de inmediato, desplazando la cola
- `{prefix}p <URL playlist> --shuffle` — encolar playlist mezclada
- `{prefix}album <nombre>` — buscar y encolar un álbum completo
- `{prefix}playlist <nombre>` — buscar y encolar una playlist
- `{prefix}autoplay` — activar/desactivar autoplay al vaciarse la cola
- `{prefix}leave` — desconectar el bot (alias: stop, disconnect)

## Reproducción en curso
- `{prefix}pause` — pausar
- `{prefix}resume` — reanudar (alias: unpause)
- `{prefix}volume <0-200>` — cambiar volumen; sin argumento muestra el volumen actual
- `{prefix}wind to <mm:ss>` — ir a un momento específico (alias: seek)
- `{prefix}forward <tiempo>` — avanzar (ej: 30s, 1m30s)
- `{prefix}backward <tiempo>` — retroceder
- `{prefix}rewind` — reiniciar la canción actual desde el principio

## Navegación de cola
- `{prefix}skip` — saltear canción actual (alias: s)
- `{prefix}previous` — volver a la canción anterior (alias: prev, back)
- `{prefix}next` — ir a la siguiente sin saltear la actual
- `{prefix}skip to <N>` — saltar a la posición N (alias: jump; acepta first, last, current, +3, -3)
- `{prefix}restart` — reiniciar la cola desde el principio

## Repetición
- `{prefix}repeat current` — loopear la canción actual (alias: loop, lc)
- `{prefix}repeat queue` — loopear toda la cola (alias: loop queue, lq)
- `{prefix}repeat disable` — desactivar loop (alias: loop off)

## Gestión de cola
- `{prefix}remove <N>` — sacar canción en posición N (alias: rm; acepta first, last, current, +3, -3)
- `{prefix}remove current` — sacar la canción que está sonando ahora (alias: rmc)
- `{prefix}remove last` — deshacer el último pedido (alias: undo)
- `{prefix}remove range <inicio> <fin>` — sacar un rango (alias: rr; acepta first, last, current)
- `{prefix}mass remove <índices>` — sacar múltiples (ej: mass remove 2-5 8)
- `{prefix}remove duplicates` — sacar canciones repetidas
- `{prefix}remove keyword <palabra>` — sacar todas las canciones cuyo título contenga esa palabra
- `{prefix}remove user <@usuario>` — sacar todos los pedidos de un usuario
- `{prefix}remove absent` — sacar pedidos de usuarios que ya no están en el canal
- `{prefix}clear` — vaciar toda la cola (alias: remove all)
- `{prefix}shuffle` — mezclar la cola
- `{prefix}sort <title|author|length>` — ordenar la cola
- `{prefix}move <de> <a>` — mover una canción de posición (acepta first, last, current)
- `{prefix}swap <N> <M>` — intercambiar dos canciones de posición

## Información
- `{prefix}now playing` — qué está sonando ahora (alias: np)
- `{prefix}next up` — qué sigue en la cola
- `{prefix}queue` — ver la cola completa (alias: q)
- `{prefix}upcoming` — ver canciones pendientes (no tocadas aún)
- `{prefix}queue information` — resumen: total de canciones, duración, etc.
- `{prefix}lyrics` — letra de la canción actual
- `{prefix}save` — guardar la canción actual por DM
