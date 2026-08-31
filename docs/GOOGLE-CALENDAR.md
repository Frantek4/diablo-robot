# Google Calendar — Espejo de los partidos

Cada partido que el bot agenda como evento de Discord se agenda también en un Google
Calendar. Lo escribe `FixtureEventCreator._sync_calendar` (`bot/cogs/fixture_event_creator.py`)
usando `integrations/google_calendar.py`.

Es opcional: si `GOOGLE_CALENDAR_ID` o `GOOGLE_SERVICE_ACCOUNT_FILE` están vacíos,
`is_enabled()` devuelve `False` y el bot sigue como siempre, sin tocar nada.

## Cómo funciona

- **Se agenda el partido, no el evento de Discord.** El evento de Discord arranca 15 minutos
  antes para que la gente se vaya juntando; el del calendario arranca a la hora del partido y
  dura 2 h (`MATCH_DURATION`). La descripción lleva el detalle del fixture (competencia, cancha,
  árbitro, TV) más el link al evento de Discord, y la cancha va además en `location`.
- **Solo se escribe cuando el bot tocó el evento de Discord**: cuando lo crea, o cuando lo edita
  porque el fixture cambió (`get_changes`). Si la vuelta del `fixture_check` no encontró nada
  nuevo, no se llama a Google. En la práctica son un par de llamadas por partido, no una por hora.
  El contrapeso: si alguien borra el evento del calendario a mano, **no vuelve solo** — vuelve
  recién cuando cambie algo del partido, o si borrás también el evento de Discord (ahí el bot lo
  recrea y reescribe el calendario).
- El id del evento en Google se deriva del `match_id` de Promiedos (`"diablo" + sha1(match_id)`),
  que es el único formato que Google acepta (base32hex: `a-v` y `0-9`). O sea que **no hace falta
  guardar el id en Mongo**: el mismo partido siempre pisa el mismo evento del calendario.
  Por eso la escritura es un `PUT` (pisar) con fallback a `POST` (crear) si todavía no existía.
- Solo se agendan los partidos dentro de los próximos 7 días, igual que los eventos de Discord.
- Si Google contesta cualquier cosa, se loguea con `messager.log(..., level="ERROR")` en `#robot-devil`
  y el fixture sigue su curso: un problema con el calendario nunca rompe el evento de Discord.

---

# Instructivo: cómo sacar las credenciales

Son unos 10 minutos. Se hace una sola vez y no vence: las credenciales de una service account
no expiran como un OAuth de usuario, que es justamente por qué usamos esto y no un login normal.

Necesitás una cuenta de Google (la misma de siempre sirve; no hace falta Workspace ni tarjeta).

## Parte 1 — Crear el proyecto y habilitar la API

**1.** Entrá a [console.cloud.google.com](https://console.cloud.google.com/) con tu cuenta de Google.
Si es la primera vez, aceptá los términos.

**2.** Arriba a la izquierda, al lado del logo, está el **selector de proyecto**. Clickealo →
**"Proyecto nuevo"** → nombre `diablo-robot` → **Crear**. Esperá unos segundos y asegurate de que
el selector ahora diga `diablo-robot`.

> Todo lo que sigue tiene que hacerse **con ese proyecto seleccionado**. Es el error más común:
> habilitar la API en un proyecto y crear la service account en otro.

**3.** En el buscador de arriba escribí **"Google Calendar API"** y entrá al resultado del
Marketplace. Apretá **"Habilitar"**. (Alternativa por menú: ☰ → *APIs y servicios* → *Biblioteca*
→ buscar → *Habilitar*.)

Si más adelante el bot loguea un `HTTP 403`, casi siempre es este paso que quedó sin hacer.

## Parte 2 — Crear la service account y bajar el JSON

Una *service account* es un "usuario robot": tiene un mail propio y una llave privada, y no
necesita que nadie apriete un botón de login nunca más.

**4.** ☰ → **APIs y servicios** → **Credenciales**.

**5.** Arriba: **"+ Crear credenciales"** → **"Cuenta de servicio"**.

**6.** Completá:
- *Nombre*: `diablo-robot-calendar`
- El *ID* se autocompleta. Anotá el mail que muestra abajo, con la pinta
  `diablo-robot-calendar@diablo-robot.iam.gserviceaccount.com` — lo vas a necesitar en la Parte 3.
- **Crear y continuar**.

**7.** Los dos pasos siguientes (*"Otorgar acceso al proyecto"* y *"Otorgar acceso a usuarios"*)
son **opcionales: salteálos**. Apretá *Continuar* y después **Listo**.

> No hace falta ningún rol de IAM. El permiso para escribir en el calendario no se da acá, se da
> compartiendo el calendario en la Parte 3. Si le das roles de IAM no rompe nada, pero no sirve.

**8.** Ahora aparece en la lista de cuentas de servicio. Clickeá encima del mail para entrar.

**9.** Pestaña **"Claves"** → **"Agregar clave"** → **"Crear clave nueva"** → tipo **JSON** →
**Crear**. Se te baja un archivo tipo `diablo-robot-a1b2c3d4e5f6.json`.

> Ese archivo es la llave. **No lo subas al repo.** Si se te pierde, no se recupera: se borra
> esa clave desde la misma pantalla y se crea otra.

**10.** Abrilo con cualquier editor y confirmá que adentro hay un campo `"client_email"` con el
mail de la Parte 6. Ese es el mail que vas a compartir en el próximo paso.

## Parte 3 — Crear el calendario y darle permiso al robot

**11.** Entrá a [calendar.google.com](https://calendar.google.com/) con **tu** cuenta (la tuya,
no la del robot — el calendario es tuyo, el robot solo escribe en él).

**12.** En la columna izquierda, al lado de **"Otros calendarios"**, apretá el **+** →
**"Crear un calendario"**. Nombre: `Independiente`. Zona horaria: *Buenos Aires*. **Crear
calendario**.

**13.** Esperá a que aparezca en la lista de la izquierda, pasale el mouse por encima →
**⋮** → **"Configuración y uso compartido"**.

**14.** Bajá hasta **"Compartir con determinadas personas o grupos"** → **"Agregar personas"**:
- Pegá el `client_email` de la Parte 10.
- En permisos elegí **"Hacer cambios en los eventos"** (no alcanza con "Ver todos los detalles").
- **Enviar**. Puede quejarse de que no puede mandarle la invitación por mail a esa dirección:
  es normal, la service account no tiene inbox. El permiso queda igual.

> Si este paso falta o quedó en solo lectura, el bot recibe un **`HTTP 404`** (Google no te dice
> "no tenés permiso", te dice que el calendario no existe).

**15.** En la misma pantalla, bajá hasta **"Integrar calendario"** y copiá el
**"ID del calendario"**. Tiene la pinta `c_a1b2c3...@group.calendar.google.com`.

## Parte 4 — Configurar el bot

**16.** Copiá el JSON al Pi y dejalo solo legible por el usuario del bot:

```bash
scp diablo-robot-a1b2c3d4e5f6.json frantek@pi:/home/frantek/dev/discord/diablo-robot/google-calendar.json
chmod 600 /home/frantek/dev/discord/diablo-robot/google-calendar.json
```

**17.** Agregá al `.env`:

```
GOOGLE_CALENDAR_ID=c_a1b2c3...@group.calendar.google.com
GOOGLE_SERVICE_ACCOUNT_FILE=/home/frantek/dev/discord/diablo-robot/google-calendar.json
```

**18.** Instalá la dependencia nueva y reiniciá:

```bash
pip install -r requirements.txt
sudo systemctl restart diablo-robot
```

Como el calendario se escribe solo cuando el bot crea o edita un evento, el primer partido
aparece cuando el `fixture_check` cree el próximo evento. Si querés verlo ya, borrá a mano el
evento de Discord del próximo partido: en la vuelta siguiente el bot lo recrea y de paso lo
agenda.

## Parte 5 — Repartir el calendario en el server

**19.** Primero hacelo público, si no el botón no le va a andar a nadie más que a vos:
*Configuración y uso compartido* → **"Permisos de acceso a eventos"** → tildá
**"Ponerlo a disposición del público"** con *"Ver todos los detalles del evento"*.

**20.** Parate en el canal donde lo quieras dejar fijado y escribí **`!calendario`**. El bot postea
un embed con dos botones y borra tu mensaje; solo te queda fijarlo.

- **"Agregar a mi Google Calendar"** es un link directo (`google_calendar.subscribe_url()`): abre
  el diálogo de suscripción de Google con la cuenta que la persona ya tenga abierta. Un click y listo.
- **"iPhone, Outlook y otros"** lo maneja el bot: contesta por privado (ephemeral) con la dirección
  `.ics` y los pasos de cada app. Fuera de Google los calendarios suscritos se refrescan cada varias
  horas, así que ahí un cambio de horario tarda en aparecer.

El mensaje se puede dejar fijado **para siempre**: el botón de Google es un link y lo resuelve
Discord solo, y el otro tiene un `custom_id` fijo que se registra con `bot.add_view()` en el `setup()`
del comando, así que sigue andando después de cada reinicio del bot.

`!calendario` pide permiso de **Gestionar mensajes** (el mismo que necesitás para fijar) y se puede
correr en cualquier canal. Si el calendario no está configurado, te lo dice y no postea nada.

## Si algo falla

Todo sale por `#robot-devil` con el prefijo `[ERROR]`:

| Mensaje | Qué pasó |
|---|---|
| `HTTP 403` + `requiredAccessLevel` | El calendario existe y lo alcanza, pero la service account no tiene permiso de escritura. Es lo que pasa si el calendario es público pero te olvidaste del paso 14, o si lo compartiste en solo lectura |
| `HTTP 403` + `accessNotConfigured` | La Calendar API no está habilitada en ese proyecto (Parte 1, paso 3) |
| `HTTP 404` | El calendario es privado **y** no está compartido con la service account, o el `GOOGLE_CALENDAR_ID` está mal copiado |
| `HTTP 401` | El JSON está mal, o le borraron la clave a la service account |
| `No llegué a Google Calendar` | El Pi se quedó sin internet, o Google tardó más de 10 s |
| No aparece nada, ni error | `GOOGLE_CALENDAR_ID` o `GOOGLE_SERVICE_ACCOUNT_FILE` vacíos: el espejo está apagado |
