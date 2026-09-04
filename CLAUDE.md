# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context

This is a **single-server, non-commercial** bot built for a personal community (Club Atlético Independiente fans). It will never run in more than one Discord server, so:
- No multi-guild handling: no guild_id guards, no per-guild state, no guild lookup loops
- No copyright or scraping concerns: web scraping and RSS aggregation are for community use only
- No need to prepare for scenarios that only matter at scale (rate limits, sharding logic, multi-tenant isolation, etc.)

## Running the Bot

```bash
python main.py
```

Requires MongoDB running (see `DATABASE_URL` in `.env`). All required environment variables are validated at startup in `main.py`.

## Architecture

**Diablo Robot** is an async Discord bot (`discord.py`) for Club Atlético Independiente's server. It tracks football fixtures, posts live match commentary, aggregates news/social media, and includes an AI-powered music agent.

### Layer Structure

- **`main.py`** — Entry point: validates env vars, creates bot, starts run loop
- **`config/settings.py`** — Pydantic BaseSettings loading all env vars; `config/database.py` — MongoDB singleton
- **`bot/client.py`** — `DiabloRobot` class; `setup_hook()` loads all cogs/commands/listeners/schedulers; `on_ready()` starts scheduled tasks. **Cada comando declara en qué canales se lo puede usar** (ver `bot/config/command_access.py`); `on_message` resuelve el comando y solo lo invoca si el canal está habilitado.
- **`bot/commands/`** — Prefix commands (`!cmd`); admin-only ones check guild permissions
- **`bot/scheduled/`** — Scheduler cogs with a `tasks.loop` started via `start_scheduled_job()` in `on_ready()`
- **`bot/cogs/`** — Stateful Discord cogs (fixture event creation, event lifecycle, live match commentator)
- **`bot/listeners/`** — Event handler cogs (reactions, event announcements, music agent)
- **`bot/ui/`** — Discord UI components (buttons, views) used by cogs and listeners
- **`bot/config/messager.py`** — Centralized message dispatcher; holds typed references to all channel objects; initialized in `on_ready()` via `init_messager(bot)`
- **`data_access/`** — DAO classes wrapping raw PyMongo queries; one DAO per MongoDB collection
- **`models/`** — Plain dataclasses; `fixture.py` handles emoji formatting and change detection
- **`integrations/`** — Web scrapers (BeautifulSoup + aiohttp) for Promiedos, Olé, TycSports, DobleAmarilla, Twitter (via Nitter RSS), YouTube RSS, Instagram

### Data Flow

1. **Fixture check** (`bot/scheduled/fixture_check.py`, 1h loop): scrapes Promiedos → upserts into `fixtures` collection → `FixtureEventCreator` cog creates/updates Discord scheduled events and announces changes to `#announcements`

   Cada partido que se agenda en Discord se agenda también en un **Google Calendar** (`integrations/google_calendar.py`, vía service account), para que la gente lo tenga en el celular sin depender de Discord. Se agenda **el partido, no el evento de Discord**: el de Discord arranca 15 min antes para que la gente se junte, el del calendario arranca a la hora del partido y dura 2 h. Se escribe **solo cuando el bot tocó el evento de Discord** (lo creó, o lo editó porque `get_changes` detectó cambios); una vuelta del loop sin novedades no llama a Google. No se guarda ningún id en Mongo: el id del evento de Google sale del `match_id` de Promiedos (`"diablo" + sha1`), así que el mismo partido siempre pisa el mismo evento y escribir es idempotente. Es opcional — sin `GOOGLE_CALENDAR_ID` o `GOOGLE_SERVICE_ACCOUNT_FILE` el espejo no corre — y un error de Google se loguea pero nunca rompe el evento de Discord. El comando **`!calendario`** (`bot/commands/calendario.py`) postea en el canal donde lo corras el embed con el que la gente se suscribe, pensado para fijarlo y no tocarlo más: un botón link a Google Calendar y otro, con `custom_id` fijo registrado vía `bot.add_view()`, que contesta ephemeral con el `.ics` para iPhone/Outlook — por eso la vista sobrevive los reinicios.
2. **Live match**: `CommentatorScheduler` (`bot/scheduled/commentator_scheduler.py`, 1min loop) queries DB for the next match; when ≤30 min away, delegates to `LiveMatchCommentator` cog (`bot/cogs/live_match_commentator.py`), which spawns an `asyncio.Task` that polls the Promiedos game-center API every 30s and posts events to `#comentador`
3. **Event lifecycle**: `EventLifecycleManager` cog (`bot/cogs/event_lifecycle_manager.py`, 5min loop) announces Discord scheduled event starts (with voice invite) and force-ends overdue active events
4. **Post-match discussion**: `EventEndForumPoster` listener (`bot/listeners/post_match_discussion.py`) opens a forum thread in `FOOTBALL_FORUM_ID` when a Discord scheduled event ends
5. **News** (`bot/scheduled/news_check.py`, 1h loop): scrapes Olé/TycSports/DobleAmarilla → deduplicates via `news` collection → posts to `#prensa` or `#club` channel
6. **Social media** (`twitter_check.py`, `youtube_check.py`, `instagram_check.py`): fetches RSS/scrapes → posts new entries to configured channels

   Twitter va contra una **instancia propia de Nitter** que corre en el Pi por Docker (`nitter/`, puerto 19050, solo en loopback). Nitter público murió el 25/08/2026 por un cease-and-desist de X: todas las instancias se apagaron, así que no hay mirrors ajenos que rotar ni catálogo que consultar. La instancia sale de `NITTER_HOST_URL`; sin esa var el bot simplemente no lee Twitter. Nitter ya no funciona con guest accounts (X las cerró en 2024): necesita cookies de una cuenta real en `nitter/sessions.jsonl` (fuera del repo), y esa cuenta se quema cada tanto. Por eso un HTTP 200 **no** alcanza para dar el feed por bueno: tiene que traer items que linkeen a `/<cuenta>/status/<id>` — cuando la sesión muere, Nitter contesta 200 con un RSS sin tweets. Si eso pasa, el scaneo corta la vuelta y avisa por `#robot-devil` en vez de seguir leyendo cuentas al pedo.

   **El ritmo lo pone el rate limit, no el reloj.** Los tweets no son urgentes y la cuenta de X es lo único que no se puede reponer, así que el scheduler va lento y consciente de lo que le queda. Los contadores no son propios ni están en Mongo: son los headers `x-rate-limit-*` que X manda en cada respuesta y que Nitter guarda por sesión y por endpoint, expuestos en `/.sessions` y `/.health` gracias a `enableDebug` — endpoints locales que **no llaman a X**, así que consultarlos es gratis. `integrations/nitter.py` los lee y de ahí sale el presupuesto de la vuelta (`budget()`): nunca baja del colchón (el piso duro de 10 con el que Nitter descarta una sesión, o un cuarto de la ventana, lo que sea más alto) y de lo que sobra gasta un cuarto, con techo de 3 cuentas. Si no hay margen no lee y **no** avisa: no gastar un pedido que va a rebotar es el bot portándose bien, no una falla. Si el formato de `/.sessions` cambia y no lo puede parsear, degrada a una cuenta por vuelta en vez de asumir que hay aire. Todo esto vive en memoria a propósito: el estado que importa ya lo lleva Nitter contra la fuente autoritativa, y guardar una copia sería tener dos verdades.

   Alrededor de eso, todo lo que se pueda desordenar se desordena, porque un pedido clavado en el mismo minuto de cada hora es el patrón más fácil de marcar que hay: el loop tiquea cada 5 min pero la vuelta real se agenda sola cada 60-150 min, entre feed y feed espera 90-240 s, y cuando sabe a qué hora se repone la ventana arranca unos minutos después y no en el segundo exacto. La primera vuelta se agenda como cualquier otra, así que reiniciar el bot no compra una lectura extra. Ante una falla de la instancia no reintenta a la hora: espera 1 h, 2 h, 4 h y 6 h por cada falla seguida (`_BACKOFF_HOURS`), avisa una vez por episodio con los números reales de la sesión y avisa de nuevo cuando vuelve. Como el flag `limited` de Nitter se limpia recién cuando le entra un pedido, si el presupuesto queda en cero más de 2 h sin que haya fallado nada, tantea con una sola cuenta para no quedarse trabado. El comando **`!nitter`** muestra todo esto en `#robot-devil`: sesiones, margen por endpoint, cuándo se repone, cuántas cuentas leería ahora y cuándo es la próxima vuelta.

   **El HTTP que devuelve Nitter no alcanza para saber qué pasó.** `rateLimitError()` (`apiutils.nim`) es un cajón de sastre: el mismo cartel "Instance has been rate limited" sale de un challenge de Cloudflare, de una cuenta bloqueada (`expiredToken`/`badToken`/`locked`), del rate limit de verdad (error 88), de un 404 transitorio, de credenciales vacías y de un `except Exception` que se traga cualquier falla de red del Pi. La causa real la escribe Nitter por stdout en `echo`s crudos que **no** dependen de `enableDebug`, así que cuando un feed rebota el bot le lee los últimos 90 s de log al contenedor (`nitter.recent_failures()`, vía `docker logs`, contenedor en `NITTER_CONTAINER`) y pega esas líneas en el aviso de `#robot-devil` en vez de afirmar una causa que no sabe. Si además el 429 llegó con margen de sobra en `/.sessions`, el aviso lo señala: eso descarta el límite de X y apunta a la sesión o a la red. Necesita que el usuario con el que corre el bot tenga acceso a `docker`; si no lo tiene, el aviso lo dice y sigue funcionando igual. Ojo con un detalle del fuente: el RSS de una cuenta usa `graphUserTweetsV2`, y `isLimited` (`auth.nim`) exime justo a ese endpoint del flag `session.limited` — o sea que ante un rate limit real Nitter **no** se autoprotege y sigue pegándole a X, así que el backoff del bot es la única defensa de la cuenta.
7. **Minecraft status** (`bot/scheduled/minecraft_check.py`, 1min loop): consulta el server de Minecraft por Server List Ping (`integrations/minecraft.py`, vía `mcstatus`) a través de la VPN de WireGuard y mantiene un único mensaje "banner" editado en `#minecraft` con si está prendido y quién está jugando. El ID de ese mensaje vive en `MINECRAFT_STATUS_MESSAGE_ID` (no en Mongo); si no está seteado, el bot crea uno nuevo y loguea el ID para que se persista a mano en el `.env`
8. **Music agent** (`bot/listeners/music_agent.py`): listens on `MUSIC_TEXT_CHANNEL_ID`; translates natural-language requests into Jockie Music commands via DeepSeek API; executes them by sending messages as a proxy user account (`NOT_ROBOT_DEVIL_USER_TOKEN`); moves the proxy user to/from the requester's voice channel to make Jockie follow along
9. **Hardware monitor** (`bot/scheduled/hardware_monitor_check.py`, 1min loop): consulta un agente HTTP standalone (`hwmonitor_agent/`, corre en la PC de Minecraft, no en el bot) vía `integrations/hardware_monitor.py` a través de la VPN de WireGuard, y mantiene un banner editado en `#robot-devil` con CPU/RAM/disco/uptime/temperaturas de esa PC (forénsica de los cuelgues de hardware que sufre esa máquina). A diferencia del banner de Minecraft, cuando la PC no responde el banner **no se edita** (queda mostrando la última performance conocida antes de la caída) y en su lugar se postea un mensaje de alerta aparte (`messager.hardware_monitor_alert`) con esas últimas métricas; otro mensaje avisa cuando vuelve. El estado (online/offline, último snapshot, último heartbeat, historial de caídas) se persiste en la colección `hardware_monitor` vía `HardwareMonitorDAO`, así sobrevive reinicios del bot. El **último heartbeat** es la última vez que la PC contestó `/metrics`: el footer del banner lo muestra (clave, porque el banner queda congelado mientras la PC está caída), el aviso de caída dice hace cuánto fue, y el aviso de vuelta lo usa para calcular el downtime cuando el bot se reinició estando la PC abajo. El agente también reporta el Kernel-Power Event ID 41 más reciente del Event Log de Windows (apagado no controlado), que el banner resalta si es reciente.

   El mismo scheduler monitorea la **red** en dos tramos, porque el bot llega a esa PC **siempre por el túnel de WireGuard** (aunque las máquinas estén en la misma red local, no se asume nunca el camino LAN):
   - **Internet de la PC**: lo mide el agente en un thread aparte cada 30s y lo cachea en el campo `network` de `/metrics` — latencia/jitter/pérdida contra un host público, latencia contra el router (para separar "se cayó internet" de "se cayó la red local"), tiempo de resolución DNS, tráfico en curso y un test de velocidad de bajada periódico. Todas las latencias se miden con handshakes TCP, no ICMP (sin permisos especiales ni parsear `ping.exe`).
   - **Túnel de WireGuard**: lo mide el bot (`hardware_monitor.measure_vpn_link()`) pegándole 4 veces al endpoint liviano `GET /ping` del agente, para no contaminar la medición con el tiempo que tarda en armarse `/metrics`.

   Cuando internet se cae pero la PC sigue respondiendo, se postea un aviso aparte (con 1 chequeo de gracia para no avisar por un microcorte) y otro cuando vuelve; los microcortes y la lentitud no generan aviso pero quedan registrados en Mongo (`kind: "network_degradation"`) y el banner muestra cuántos hubo en las últimas 24 h.

### Key Patterns

- All DAOs follow: `insert()`, `get_*()`, `exists()`, `upsert()`, `update_*()` — raw PyMongo, no ORM
- Adding a new command: create file in `bot/commands/`, add `await bot.load_extension('bot.commands.filename')` in `bot/client.py`
- **Alcance de un comando**: por defecto solo se puede usar en `#robot-devil`. Para habilitarlo en otros canales se declara en el decorador: `@commands.command(name="x", extras={"channels": (settings.GENERAL_TEXT_CHANNEL_ID, ...)})` (o `ANY_CHANNEL`, como `!ayuda`). Los permisos van aparte, con los checks de siempre (`@commands.has_permissions(...)`). `!ayuda` lista la **intersección** de las dos cosas: los comandos habilitados en el canal donde se pregunta y que además el que pregunta tiene permisos para correr (`filter_commands` corre los checks), así que un comando bien declarado aparece y desaparece de la ayuda solo
- Adding a new scheduled task: create file in `bot/scheduled/` with a `setup(bot)` function that adds a cog with `start_scheduled_job()`; load it in `client.py` and call `start_scheduled_job()` in `on_ready()`
- Discord channel IDs are env vars loaded via settings object on `config/settings.py` and accessed through the messager
- **Logging**: all errors and warnings in async code must use `await messager.log(msg, level="CRITICAL"|"ERROR"|"WARNING", exc=e)` — it posts to `ROBOT_DEVIL_TEXT_CHANNEL` and also calls the standard Python logger (visible via `journalctl`). Only use `logger.*` directly in sync helper methods where `await` is not possible. Messages should be written in first person, informally but informatively — e.g. `"No pude scrapear Olé"`, `"Le di el rol X a Y"`, `"No tengo permisos para..."` — not bureaucratic passive constructions.

### MongoDB Collections

| Collection | Purpose |
|---|---|
| `fixtures` | Match data: teams, date, score, status, competition |
| `games` | Game channels: game_name, message_id, text_channel_id |
| `news` | URL deduplication to prevent duplicate news posts |
| `influencers` | Social media accounts: platform, account_id, source type |
| `hardware_monitor` | Latest hardware + network snapshot, online/offline transition log (PC e internet) y registro de microcortes de red de la PC de Minecraft (see `HardwareMonitorDAO`) |

### Teams Tracked

Defined in `models/team_url.py` as an enum with Promiedos URLs: Profesional Masculino, Reserva Masculino, Femenino, Selección Nacional, Selección Sub-20.

## Environment Variables

All defined in `config/settings.py`. Required vars are also validated at startup in `main.py`. Key ones:

- `DISCORD_TOKEN`, `GUILD_ID` — Discord auth
- `DATABASE_URL`, `DATABASE_USERNAME`, `DATABASE_PASSWORD` — MongoDB
- `USER_AGENT` — HTTP user-agent string for scrapers
- `NITTER_HOST_URL` — URL de la instancia propia de Nitter (ej. `http://127.0.0.1:19050`). Si falta, el scaneo de Twitter no corre. Ver `nitter/README.md` para levantarla; `NITTER_CONTAINER` — nombre del contenedor (default `nitter`), para leerle los logs con `docker logs` cuando un feed rebota
- `IG_USERNAME`, `IG_PASSWORD` — Instagram credentials for instaloader (optional)
- `DEEPSEEK_API_KEY` — DeepSeek API key for the music agent (optional)
- `GOOGLE_CALENDAR_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE` — calendario donde se espejan los partidos y ruta al JSON de la service account que lo escribe (ambos opcionales; si falta alguno el espejo no corre)
- `NOT_ROBOT_DEVIL_USER_TOKEN`, `NOT_ROBOT_DEVIL_USER_ID` — Proxy user account used by the music agent to send Jockie commands as a real user
- `DJ_COMMAND_PREFIX` — Jockie Music command prefix (default: `m!`)
- Channel IDs: `GENERAL_TEXT_CHANNEL_ID`, `ANNOUNCEMENTS_TEXT_CHANNEL_ID`, `CLUB_TEXT_CHANNEL_ID`, `PRESS_TEXT_CHANNEL_ID`, `COMMENTATOR_TEXT_CHANNEL_ID`, `GAMES_TEXT_CHANNEL_ID`, `ROBOT_DEVIL_TEXT_CHANNEL_ID`, `MUSIC_TEXT_CHANNEL_ID`, `MINECRAFT_TEXT_CHANNEL_ID`
- `MINECRAFT_SERVER_HOST`, `MINECRAFT_SERVER_PORT` — cómo alcanzar el server de Minecraft dentro de la VPN de WireGuard (default `e-cai.mc:25565`); `MINECRAFT_STATUS_MESSAGE_ID` — ID del mensaje-banner en `#minecraft` que el scheduler edita en vez de recrear (opcional; si falta, el bot crea uno y loguea el ID a mano)
- `HARDWARE_MONITOR_HOST`, `HARDWARE_MONITOR_PORT` — cómo alcanzar el agente de hardware (`hwmonitor_agent/`) en la PC de Minecraft dentro de la VPN de WireGuard (default puerto `8788`); `HARDWARE_MONITOR_TOKEN` — token compartido enviado como header `X-Auth-Token` (debe matchear `HWMON_TOKEN` del agente); `HARDWARE_MONITOR_STATUS_MESSAGE_ID` — ID del mensaje-banner en `#robot-devil` (opcional; mismo mecanismo manual que `MINECRAFT_STATUS_MESSAGE_ID`)
- `GENERAL_VOICE_CHANNEL_ID`, `TERMOS_VOICE_CHANNEL_ID`, `IDLE_VOICE_CHANNEL_ID` — Voice channels used for events and proxy user idle state
- `GAMES_CATEGORY_ID` — Category ID for game channels
- `FOOTBALL_FORUM_ID` — Forum channel for match discussion
