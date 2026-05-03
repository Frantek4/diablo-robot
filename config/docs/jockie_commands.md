# Comandos de Jockie Music (prefijo: {prefix})

## Reproducir
- `{prefix}p <artista - título>` — encolar una canción
- `{prefix}p <URL>` — reproducir desde URL (Spotify, YouTube, Deezer, Apple Music, Tidal, SoundCloud)
- `{prefix}p <término> --insert` — insertar justo después de la canción actual
- `{prefix}p <término> --now` — reproducir de inmediato, desplazando la cola
- `{prefix}p <URL playlist> --shuffle` — encolar playlist mezclada
- `{prefix}album <artista + álbum>` — buscar y encolar álbum; muestra un menú de selección que el usuario debe resolver manualmente; preferí `{prefix}p <URL Spotify>` cuando tenés la URL exacta
- `{prefix}playlist <nombre>` — buscar y encolar playlist; mismo comportamiento que album
- `{prefix}autoplay` — activar/desactivar autoplay al vaciarse la cola
- `{prefix}leave` — desconectar el bot

## Reproducción en curso
- `{prefix}pause` / `{prefix}resume` — pausar / reanudar
- `{prefix}volume <0-200>` — cambiar volumen
- `{prefix}wind to <mm:ss>` — ir a un momento específico
- `{prefix}forward <tiempo>` / `{prefix}backward <tiempo>` — avanzar / retroceder (ej: 30s, 1m30s)
- `{prefix}rewind` — reiniciar la canción actual desde el principio

## Navegación de cola
- `{prefix}skip` — saltear canción actual
- `{prefix}previous` — volver a la canción anterior
- `{prefix}next` — ir a la siguiente sin saltear la actual
- `{prefix}skip to <N>` — saltar a la posición N (acepta first, last, current, +3, -3)
- `{prefix}restart` — reiniciar la cola desde el principio

## Repetición
- `{prefix}repeat current` — loopear la canción actual
- `{prefix}repeat queue` — loopear toda la cola
- `{prefix}repeat disable` — desactivar loop

## Gestión de cola
- `{prefix}remove <N>` — sacar canción en posición N (acepta first, last, current, +3, -3)
- `{prefix}remove current` — sacar la canción que está sonando
- `{prefix}remove last` — deshacer el último pedido
- `{prefix}remove range <inicio> <fin>` — sacar un rango
- `{prefix}mass remove <índices>` — sacar múltiples (ej: mass remove 2-5 8)
- `{prefix}remove duplicates` — sacar canciones repetidas
- `{prefix}remove keyword <palabra>` — sacar todas las canciones con esa palabra en el título
- `{prefix}remove user <@usuario>` — sacar todos los pedidos de un usuario
- `{prefix}remove absent` — sacar pedidos de usuarios que ya no están en el canal
- `{prefix}clear` — vaciar toda la cola
- `{prefix}shuffle` — mezclar la cola
- `{prefix}sort <title|author|length>` — ordenar la cola
- `{prefix}move <de> <a>` — mover una canción de posición
- `{prefix}swap <N> <M>` — intercambiar dos canciones de posición

## Información
- `{prefix}now playing` — qué está sonando ahora
- `{prefix}next up` — qué sigue en la cola
- `{prefix}queue` — ver la cola completa
- `{prefix}upcoming` — ver canciones pendientes
- `{prefix}queue information` — resumen: total de canciones, duración, etc.
- `{prefix}recently played` — historial de canciones escuchadas
- `{prefix}session information` — info de la sesión actual
- `{prefix}lyrics` — letra de la canción actual
- `{prefix}save` — guardar la canción actual por DM
