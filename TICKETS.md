# Sistema de Bonos Automáticos — Diseño

## Objetivo

Permitir que los socios del club se anoten con anticipación para recibir sus bonos de entrada al estadio, y que el bot los obtenga automáticamente en el momento exacto en que el formulario de BoleteríaVIP se habilita, eliminando la urgencia de conectarse a tiempo.

---

## Flujo general

```
BoleteriaVIPScraper (loop cada 24 horas al mediodía)
       │ scraping https://cai.boleteriavip.com.ar/category/description/1/futbol/
       │ detecta campaña de bonos nueva para Independiente → guarda en ticket_campaigns
       ▼
TicketAnnouncer publica mensaje único en #tickets
  → botón "Sacame bono" / botón "Cancelar"
       │
  usuarios interactúan (validación: ventana no pasada, no deshabilitado)
       │
  ticket_requests en DB
       │
  T-60min ──► DM de recordatorio a cada anotado
                ("voy a buscar tu bono, no lo saques vos o nos falla a los dos")
  T-5min  ──► botones deshabilitados (edita el mensaje)
  T=0     ──► TicketClaimer dispara → formulario BoleteríaVIP + reCaptcha Enterprise
       │
  resultado DM individual (confirmación con ID de operación, o error)
```

---

## Decisiones de diseño

- **Un solo mensaje por campaña activa.** Cuando llega una nueva campaña, se publica un nuevo mensaje. El mensaje anterior queda en el historial con botones deshabilitados. Nunca se edita el contenido principal, solo el estado de los botones.
- **El flujo es completamente independiente de los eventos de Discord.** No depende de `FixtureEventCreator`. El disparador es el scraping de BoleteríaVIP.
- **Zona horaria: `America/Argentina/Buenos_Aires` hardcodeada.** No se usa `settings.TIMEZONE`. El año siempre es el actual cuando BoleteríaVIP no lo especifica.
- **Nomenclatura:** clases, funciones y variables en inglés. Nombres propios (Santoro, Pavoni, BoleteríaVIP) y comandos de Discord en español.

---

## Modelo de datos — colección `members`

```json
{
  "_id": ObjectId,
  "discord_id": "123456789",
  "name": "Juan Pérez",
  "dni": "35123456",
  "member_number": "12345",
  "email": "juan@example.com",
  "member_status": "active",
  "preferred_section": "norte",
  "status_checked_at": ISODate,
  "created_at": ISODate
}
```

- `discord_id`: clave de búsqueda principal; vincula al socio con su usuario Discord para DMs.
- `preferred_section`: `"norte"` (Santoro baja) | `"sur"` (Pavoni baja). Modificable con `!mi_tribuna`.
- `status`: actualizado por `MemberStatusChecker` (mensual y pre-partido).

---

## Modelo de datos — colección `ticket_campaigns`

Una entrada por campaña de bonos detectada en BoleteríaVIP.

```json
{
  "_id": ObjectId,
  "rival": "Racing Club",
  "match_date": ISODate,
  "opens_at": ISODate,
  "campaign_url": "https://cai.boleteriavip.com.ar/...",
  "discord_message_id": "...",
  "status": "announced",
  "scraped_at": ISODate
}
```

`status`: `"announced"` → `"done"`

---

## Modelo de datos — colección `ticket_requests`

Una entrada por socio por campaña.

```json
{
  "_id": ObjectId,
  "campaign_id": ObjectId,
  "member_id": ObjectId,
  "section_priority": ["norte", "sur"],
  "status": "pending",
  "boleteria_operation_id": null,
  "error_reason": null,
  "requested_at": ISODate,
  "processed_at": null
}
```

`status`: `"pending"` | `"claimed"` | `"failed"` | `"no_capacity"`

Al cancelar o excluir: **eliminar el documento**, no baja lógica.

---

## Comandos Discord

### `!nuevo_socio "{name}" {dni} {nro_socio} [email]`

- Solo admins.
- Valida que `dni` y `nro_socio` sean numéricos.
- Upsert por `discord_id` del usuario mencionado (o quien lo ejecuta, a definir).
- Al registrar, consulta inmediatamente el estado del socio en BoleteríaVIP (ver sección de estado).
- Si está inactivo: notifica al usuario por DM explicando el estado y que no podrá obtener bonos hasta regularizar.
- Responde con confirmación en canal.

**Ejemplo:**
```
!nuevo_socio "Juan Pérez" 35123456 12345 juan@example.com
```

### `!mi_tribuna norte|sur`

- Actualiza `preferred_section` del socio que ejecuta el comando.
- Solo si el socio ya está registrado.

### `!cancelar_bono`

- Elimina el `ticket_request` del usuario para la campaña activa (si existe y está `pending`).
- Alternativo al botón Cancelar del mensaje.

---

## Integración BoleteríaVIP — Scraping de campañas

**URL de monitoreo:** `https://cai.boleteriavip.com.ar/category/description/1/futbol/`

### `BoleteriaVIPScraper` (integrations/boleteria_vip_scraper.py)

Loop de 24 horas (ejecutado al mediodía) que:

1. GET `https://cai.boleteriavip.com.ar/category/description/1/futbol/` — página pública, sin autenticación.
2. Parsea con BeautifulSoup. Itera `section.section-event` (una card por evento).
3. Para cada card:
   - Obtiene título desde `div.event-title a` (texto).
   - Descarta si el título **no** contiene `"Independiente vs"` (filtra tours del estadio y otros eventos no relacionados).
   - Extrae `campaign_url` desde el `href` del mismo `<a>` (patrón `/event/description/{id}/{slug}`).
   - Extrae rival del título: la parte después de `"Independiente vs "`.
   - Extrae fecha del partido desde `div.properties-group span` (ej: `"Sábado 4 de abril"`).
   - Extrae fecha y hora de apertura de bonos desde el texto de `div.mb-3.raw-container p`, buscando la línea `"Canje de Bonos:"` con regex:
     ```
     Canje de Bonos:\s*\w+\s+(\d{1,2}/\d{2})\s+a las\s+(\d{1,2})hs
     ```
     Ejemplo: `"MIERCOLES 01/04 a las 18hs"` → `opens_at = 01/04/{año_actual} 18:00 ART`.
   - Año: siempre `datetime.now(tz).year`. Zona horaria: `ZoneInfo("America/Argentina/Buenos_Aires")` hardcodeada.
4. Compara contra `ticket_campaigns` existentes por `campaign_url` para evitar duplicados.
5. Si es nueva: inserta en `ticket_campaigns` y dispara el anuncio en Discord.

---

## Integración BoleteríaVIP — Consulta de estado de socio

**Endpoint conocido:** `POST https://cai.boleteriavip.com.ar/socios/habilitacion`

### Flujo

```
1. GET  https://cai.boleteriavip.com.ar/socios/habilitacion/?club=cai
        → extraer __RequestVerificationToken del HTML
        → conservar cookies de sesión (aiohttp CookieJar)

2. Resolver reCaptcha Enterprise (sitekey conocido, ver sección reCaptcha)
        → action: "get_member_status"

3. POST https://www.boleteriavip.com.ar/socios/habilitacion
        Content-Type: application/x-www-form-urlencoded
        Campos:
          VenueKey         = "cai"
          SocioNro         = member_number
          NroContador      = ""   ← irrelevante para CAI, se envía vacío
          DocType          = "DNI"
          SocioNroDoc      = dni
          __RequestVerificationToken = <del GET>
          g-recaptcha-response       = <token resuelto>

4. Parsear respuesta HTML:
   - Estado:          dd#socio-info-estado-id        → "Activo" | "Inactivo"
   - Última cuota:    dd#socio-info-ultima-cuota-id  → "mayo 2026" (mes y año)
```

El campo de última cuota es útil para validar si el socio cumple el requisito del partido específico (cada evento especifica en su descripción qué cuota debe estar al día).

---

## Integración BoleteríaVIP — Formulario de bonos

### Ingeniería reversa *(pendiente)*

El formulario de obtención de bonos sigue el mismo patrón que el de estado de socio (CSRF + reCaptcha Enterprise). Hay que inspeccionar el tráfico de red para documentar:

- URL del endpoint de submit.
- Campos específicos (sección, partido, cantidad).
- Mensajes de respuesta para éxito, cupo agotado, socio inactivo, datos inválidos.

Se asume que el sitekey de reCaptcha Enterprise es el mismo: `6LdTzOErAAAAALKbc1fXj1X70bPRHI1HVVjjWUyn`.

---

## Integración BoleteríaVIP — reCaptcha Enterprise

BoleteríaVIP usa **reCaptcha Enterprise** (no v2 ni v3 estándar).

**Datos conocidos del endpoint de estado:**
- Sitekey: `6LdTzOErAAAAALKbc1fXj1X70bPRHI1HVVjjWUyn`
- Action: `get_member_status` (el formulario de bonos tendrá su propia action)
- Renderizado con `grecaptcha.enterprise.render`

### `CaptchaSolver` (integrations/captcha_solver.py)

BoleteríaVIP dispara **desafíos visuales** (selección de imágenes de tránsito, bicicletas, etc.) — no es score-only. Un browser headless recibe los mismos desafíos y no puede resolverlos solo. Se requiere un servicio externo con workers humanos o AI.

A ~30 solves por partido el costo es negligible (~$0.05/partido):

| Servicio | Costo aprox. | Enterprise | Notas |
|----------|--------------|------------|-------|
| [Capsolver](https://capsolver.com) | ~$1.5/1000 | Sí | Recomendado |
| [2Captcha](https://2captcha.com) | ~$3/1000 | Sí (`enterprise=1`) | |

```
1. POST al servicio con: sitekey + URL de la página + enterprise=true + action
2. Polling hasta recibir el token (10-60 segundos según queue del servicio)
3. Incluir token como campo g-recaptcha-response en el POST al formulario
4. Si Capsolver falla (timeout, error de servicio) o BoleteríaVIP rechaza el token
   → reintentar el solve completo hasta MAX_CAPTCHA_RETRIES veces antes de marcar como failed
```

**Variables de entorno:** `CAPTCHA_API_KEY`, `CAPTCHA_SERVICE` (`"capsolver"` | `"2captcha"`).

### `BoleteriaVIPClient` (integrations/boleteria_vip.py)

```python
class MemberStatus:
    active: bool
    raw_html: str  # para debug si parseo falla

class ClaimResult:
    success: bool
    operation_id: str | None
    error: str | None  # "CAPACITY_FULL" | "INACTIVE_MEMBER" | "INVALID_DATA" | "GENERIC"

class BoleteriaVIPClient:
    async def check_member_status(self, member) -> MemberStatus: ...
    async def claim_ticket(self, campaign, member, section) -> ClaimResult: ...
```

Ambos métodos comparten el mismo helper privado `_get_csrf_token(url)` que hace el GET inicial y devuelve el token + las cookies de sesión.

### Lógica de fallback de sección

```python
sections = [member.preferred_section, opposite_section(member.preferred_section)]
for section in sections:
    result = await client.claim_ticket(campaign, member, section)
    if result.success or result.error != "CAPACITY_FULL":
        break
```

### Tabla de respuestas del claim

| Caso | Detección | Acción |
|------|-----------|--------|
| Éxito | `operation_id` presente | DM con confirmación e ID |
| Cupo agotado en sección preferida | `"CAPACITY_FULL"` (primera sección) | Marcar sección como exhausted, reintentar con sección alternativa |
| Cupo agotado en ambas secciones | `"CAPACITY_FULL"` en ambas | DM avisando que las dos tribunas se llenaron, `status = "no_capacity"` |
| Socio inactivo | `"INACTIVE_MEMBER"` | DM de error, no reintentar |
| Datos inválidos | `"INVALID_DATA"` | DM de error, no reintentar |
| Error genérico | cualquier otro | DM de error, loguear con messager |

### Propagación de sección exhausted

Cuando cualquier batch o request individual recibe `CAPACITY_FULL` para una sección, esa sección se marca como exhausted en un estado compartido entre todas las tasks concurrentes. Todos los requests pendientes o en cola que apuntaban a esa sección se redirigen inmediatamente a la sección alternativa sin intentar el request — si esa también está exhausted, se marcan directamente como `"no_capacity"` sin hacer ninguna llamada.

`"no_capacity"` es un estado terminal distinto de `"failed"` — no indica un error del sistema sino que el estadio se llenó. El DM debe dejarlo claro.

**Mensaje DM de capacidad agotada (ejemplo):**
> No pude sacarte el bono para el partido vs [rival]. Las dos tribunas (Santoro baja y Pavoni baja) ya no tenían lugares disponibles cuando intenté. Volaron los cupos.

---

## Scheduled: `TicketClaimer` (bot/scheduled/ticket_claimer.py)

Loop que corre cada minuto y evalúa campañas en estado `"announced"`:

### T-60 minutos: recordatorio DM

Para cada solicitud `pending` de la campaña, envía DM:

> Hola [nombre], en una hora voy a buscar tu bono para el partido vs [rival]. **No intentes sacarlo vos mismo o nos va a fallar a los dos** — los dos requests simultáneos sobre el mismo socio generan un error en BoleteríaVIP. Quedá tranquilo que lo gestiono yo.

### T-5 minutos: deshabilitar botones

- Edita el mensaje en #tickets para deshabilitar los botones "Sacame bono" y "Cancelar".
- Ningún usuario puede anotarse ni cancelar a partir de este punto.

### T=0: claiming

El proceso tiene dos fases. **No se envía ningún DM hasta que ambas fases terminan.**

#### Fase 1 — batch por sección

BoleteríaVIP permite incluir hasta 6 miembros en un solo request, siempre que sean de la misma sección. Se agrupan todos los `ticket_requests` pendientes por `section_priority[0]` (sección preferida) y se submiten en batches de hasta 6, con un captcha por batch. Esto minimiza drásticamente la cantidad de captchas necesarios.

- Todos los batches de ambas secciones se lanzan simultáneamente con `asyncio.gather`.
- Los batches de > 6 miembros en la misma sección se subdividen en sub-batches de hasta 6, también concurrentes.

#### Fase 2 — reintento individual de fallidos

Los requests de cualquier batch que hayan fallado se reintentan **uno por uno, secuencialmente**. Esto aísla si el error es transitorio (se resuelve) o es atribuible a un socio específico (datos inválidos, estado no detectado, etc.).

Los errores de negocio (`INACTIVE_MEMBER`, `INVALID_DATA`, `CAPACITY_FULL`) no se reintentan en ninguna fase — son definitivos. `CAPACITY_FULL` sí dispara el fallback de sección (intentar con la sección alternativa), tanto en fase 1 como en fase 2.

#### Cierre

Una vez que ambas fases terminan: actualizar DB, enviar todos los DMs, marcar la campaña como `"done"`.

**Sobre reintentos de captcha:** `claim_ticket` tiene reintentos internos de captcha (`CAPTCHA_MAX_RETRIES`). La fase 2 es un reintento de nivel superior, sobre el request completo (nuevo captcha + nuevo POST).

---

## Interacción del usuario — `TicketView` (bot/views/ticket_view.py)

View persistente registrada en `setup_hook()` para sobrevivir reinicios.

### Botón "Sacame bono"

Validaciones al presionar:
1. El usuario tiene registro en `members` → si no: efímero explicando cómo registrarse.
2. `members.status = "active"` → si no: efímero notificando el estado inactivo.
3. La ventana de la campaña no pasó (`now < campaign.opens_at`) → si no: efímero diciendo que la ventana ya cerró.
4. Los botones no están deshabilitados (T-5min activo) → si no: ignorar silenciosamente.
5. No tiene ya un `ticket_request` para esta campaña → si ya tiene: efímero confirmando que ya está anotado.

Si pasa todo: inserta `ticket_request` con `status = "pending"`, responde en efímero con confirmación.

### Botón "Cancelar"

- Elimina el `ticket_request` para esta campaña (si existe y está `pending`).
- Si no existe: efímero indicando que no estaba anotado.
- Solo válido antes del lock (T-5 min).

---

## `MemberStatusChecker` (bot/scheduled/member_status_checker.py)

Usa `BoleteriaVIPClient.check_member_status()` para ambos chequeos.

### Chequeo mensual — día 1

- Loop diario; ejecuta lógica solo cuando `now.day == 1`.
- Para **todos** los socios en `members`, llama a `check_member_status()`.
- Si cambia a `inactive`: actualiza DB + DM al usuario.
- Actualiza `status_checked_at`.

### Chequeo pre-bonos — 24-48 horas antes de apertura

- Detecta campañas con `opens_at` dentro de las próximas 24-48 horas.
- Consulta solo los socios con `status = "inactive"` que tienen `ticket_request` `pending` en esa campaña — los activos no se re-chequean, ya que el estado activo al comienzo del mes se mantiene por todo el mes.
- Si siguen inactivos: DM notificando exclusión, eliminar su `ticket_request`.
- Si ahora están activos (regularizaron): actualizar `status = "active"` en DB, no hacer nada más (conservan su lugar en la campaña).

**Mensaje DM de exclusión:**
> Hola [nombre], tu membresía aparece como **inactiva** en el sistema del club. No voy a poder gestionar tu bono para el partido vs [rival] del [fecha]. Si creés que es un error, comunicate con la secretaría. Cuando esté activa de nuevo podés volver a anotarte.

---

## Variables de entorno nuevas

```
TICKETS_TEXT_CHANNEL_ID=...
CAPTCHA_API_KEY=...
CAPTCHA_SERVICE=capsolver
CAPTCHA_MAX_RETRIES=3
```

---

## Archivos a crear

```
bot/
  commands/
    members.py               # !nuevo_socio, !mi_tribuna, !cancelar_bono
  cogs/
    ticket_announcer.py      # publica/actualiza mensaje en #tickets al detectar campaña
  scheduled/
    ticket_claimer.py        # T-60min DM, T-5min lock, T=0 claim
    member_status_checker.py # chequeo día 10 y pre-partido
  views/
    ticket_view.py           # View persistente con botones

data_access/
  members_dao.py
  ticket_requests_dao.py
  ticket_campaigns_dao.py

integrations/
  boleteria_vip_scraper.py   # scraping de campañas (categoría futbol)
  boleteria_vip.py           # HTTP client: check_member_status + claim_ticket
  captcha_solver.py          # wrapper para servicio de reCaptcha Enterprise
```

---

## Pendientes antes de implementar

1. **Endpoint de submit de bonos**: inspeccionar tráfico de red del formulario `/event/description/{id}/...` para documentar URL de submit, campos (sección, cantidad, DNI, nro. socio) y estructura de respuesta (éxito, cupo agotado, socio inactivo, datos inválidos).

4. **Captcha service**: contratar Capsolver antes de implementar `CaptchaSolver`.

5. **Cantidad de tickets por solicitud**: diseño actual asume 1 por socio por batch. ¿Se expone la opción de pedir más de 1 individualmente?
