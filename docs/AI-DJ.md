# AI-DJ

## Problema

Jockie Music tiene una sintaxis críptica (`m!p`, `m!sk`, `m!q remove`, etc.) que obliga a los usuarios a memorizarla o buscarla constantemente. La barrera de uso hace que el canal de música quede subutilizado.

## Idea

Un canal de texto dedicado (`#música` o `#dj`) donde los usuarios escriben en lenguaje natural. El bot intercepta esos mensajes, los interpreta con Claude, y ejecuta los comandos de Jockie correspondientes — o pide aclaración al usuario si hay ambigüedad — sin que nadie tenga que saber la sintaxis.

**Ejemplo de ejecución directa:**
> "Saltá la canción actual y poné la música de los montajes de Gokú"

```
m!skip
m!p Evanescence - Bring Me to Life
```

**Ejemplo de aclaración:**
> "Poné Creep"

> "Existen 3 canciones famosas llamadas Creep: una de Radiohead, una de TLC y una de Stone Temple Pilots. ¿Cuál querés?"

> "La de Radiohead"

```
m!p Radiohead - Creep
```

---

## Comandos de Jockie a cubrir

El prefijo de Jockie es configurable vía `DJ_COMMAND_PREFIX` (por defecto `m!`).

| Intención natural                        | Comando                      |
|------------------------------------------|------------------------------|
| Poner / reproducir [canción]             | `{prefix}p [canción]`        |
| Saltear / siguiente canción              | `{prefix}skip`               |
| Parar la música                          | `{prefix}stop`               |
| Pausar                                   | `{prefix}pause`              |
| Reanudar                                 | `{prefix}resume`             |
| Ver la cola                              | `{prefix}queue`              |
| Mezclar la cola                          | `{prefix}shuffle`            |
| Poner en loop / repetir                  | `{prefix}loop`               |
| Subir/bajar el volumen a X%             | `{prefix}volume [0-200]`     |
| Sacar la canción N de la cola            | `{prefix}remove [N]`         |
| Ir al minuto X                           | `{prefix}seek [MM:SS]`       |
| Limpiar la cola                          | `{prefix}clear`              |

---

## Arquitectura

### Dentro del bot existente

```
bot/listeners/music_agent.py   ← listener del canal dedicado
config/settings.py             ← MUSIC_TEXT_CHANNEL_ID, DJ_COMMAND_PREFIX
```

No requiere schedulers ni cogs nuevos: es un listener puro que reacciona a `on_message`.

### Flujo

```
Usuario escribe en #dj
        ↓
music_agent.py intercepta el mensaje
        ↓
Agrega el mensaje al historial de conversación del usuario (en memoria)
        ↓
Llama a Claude API con [system prompt fijo] + [historial del usuario]
        ↓
Claude devuelve COMANDOS o una PREGUNTA DE ACLARACIÓN
        ↙                          ↘
Ejecuta comandos en #dj     Responde al usuario en #dj
Limpia historial            Espera el próximo mensaje del mismo usuario
```

### Manejo de historial de conversación

El agente mantiene un diccionario en memoria `dict[user_id, list[Message]]` con el historial reciente de cada usuario. Esto permite que Claude recuerde el contexto de una aclaración sin perder el system prompt.

**Reglas del historial:**
- Se inicializa vacío por usuario.
- Cada mensaje del usuario y cada respuesta del agente se agregan al historial.
- El historial se limpia cuando: (a) Claude ejecuta comandos con éxito, o (b) pasan 2 minutos sin actividad del usuario.
- El historial nunca crece más de ~10 turnos para evitar context drift.

### System prompt (borrador)

```
Sos un intérprete de comandos para el bot de música Jockie Music en Discord.
Podés hacer dos cosas:

1. EJECUTAR: si la intención es clara, devolvé únicamente los comandos, uno por línea, sin texto adicional.
   El prefijo de Jockie es "{DJ_COMMAND_PREFIX}". Ejemplo: {DJ_COMMAND_PREFIX}p Radiohead - Creep

2. PREGUNTAR: si hay ambigüedad genuina que cambia el resultado (p.ej. múltiples canciones con el mismo nombre),
   respondé en español con una pregunta breve y concreta. No preguntes si podés inferir razonablemente.

Reglas:
- Si el mensaje no es un pedido musical, devolvé exactamente: IGNORAR
- Para pedidos multi-paso, listá todos los comandos en orden.
- Infiere la canción más conocida cuando la descripción es vaga pero reconocible.
- Solo preguntá cuando la ambigüedad sea real y el resultado cambie significativamente según la elección.
- Jamás mezcles comandos con texto explicativo en la misma respuesta.
```

---

## Detalles de implementación

### Variables de entorno nuevas

```env
MUSIC_TEXT_CHANNEL_ID=123456789   # Canal #dj donde escucha el agente
DJ_COMMAND_PREFIX=m!              # Prefijo de comandos de Jockie
ANTHROPIC_API_KEY=sk-ant-...      # Si no está ya definida
```

### Comportamiento del listener

- Solo actúa en `MUSIC_TEXT_CHANNEL_ID`.
- Ignora mensajes del propio bot y de Jockie.
- Si el usuario no está en ningún canal de voz: reacciona con 💤 y no procesa nada más.
- Muestra "typing" (`async with channel.typing()`) mientras espera la respuesta de Claude.
- Si Claude devuelve comandos: los envía secuencialmente con `asyncio.sleep(0.5)` entre ellos, reacciona el mensaje original con ✅ y limpia el historial.
- Si Claude devuelve una pregunta: la envía como respuesta (reply) al usuario y no limpia el historial.
- Si Claude devuelve `IGNORAR`: reacciona con ❓ y no hace nada más.
- Si hay error en la API: loguea con `messager.log()` y reacciona con ❌.

---

## Casos edge

| Caso                                      | Comportamiento esperado                               |
|-------------------------------------------|-------------------------------------------------------|
| Mensaje que no es un pedido musical       | `IGNORAR` → reacción ❓                               |
| Canción ambigua con múltiples versiones   | Claude pregunta con opciones concretas                |
| Descripción vaga pero reconocible         | Claude infiere la más probable, ejecuta sin preguntar |
| Múltiples pedidos en un mensaje           | Ejecuta todos en secuencia                            |
| Usuario no responde la aclaración         | Historial se limpia a los 2 minutos                   |
| Usuario no está en ningún canal de voz    | Reacción 💤, sin llamar a Claude ni a Jockie          |

---

## Estado

- [ ] Definir canal dedicado en el servidor
- [ ] Agregar `MUSIC_TEXT_CHANNEL_ID` y `DJ_COMMAND_PREFIX` a settings y `.env`
- [ ] Implementar `bot/listeners/music_agent.py`
- [ ] Afinar system prompt con pruebas reales
- [ ] Decidir si borrar o reaccionar los mensajes del usuario tras ejecutar
