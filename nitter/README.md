# Instancia propia de Nitter

Nitter público murió el 25/08/2026 (cease-and-desist de X). El código sigue disponible y la
imagen de Docker tiene `arm64`, así que el bot usa su propia instancia en el Pi en vez de
depender de mirrors ajenos.

## Levantarlo

```bash
cd nitter
sed -i "s/REEMPLAZAR/$(openssl rand -hex 32)/" nitter.conf   # hmacKey
cp sessions.jsonl.example sessions.jsonl                     # y completalo (ver abajo)
docker compose up -d
```

Probar que sirve RSS de verdad (que devuelva `<item>` con links a `/status/`, no solo un 200):

```bash
curl -s http://127.0.0.1:19050/Independiente/rss | grep -c "/status/"
```

## Las sesiones

Nitter ya no funciona con guest accounts (X las cerró en 2024): necesita las cookies de una
cuenta real. El formato de `sessions.jsonl` es una línea JSON por cuenta:

```json
{"kind": "cookie", "username": "...", "id": "...", "auth_token": "...", "ct0": "..."}
```

**Usá una cuenta descartable**: es la que se va a quemar, no la personal.

El repo de Nitter trae `tools/create_session_browser.py`, que automatiza un Chromium con
`zendriver` para loguearse solo. No lo uso: es pesado para el Pi y loguearse por código es
justamente lo que dispara captchas y bloqueos. En su lugar está `import_firefox_session.py`,
que reusa la sesión que ya abriste a mano —el mismo enfoque que usamos con instaloader para
Instagram:

```bash
# 1. Entrá a https://x.com en Firefox con la cuenta descartable, y dejá la sesión abierta
# 2. Generá la línea:
python3 import_firefox_session.py --username lacuenta >> sessions.jsonl
# 3. Recargá Nitter:
docker compose restart nitter
```

Saca `auth_token`, `ct0` y `twid` (de donde sale el id numérico) de `cookies.sqlite`, en modo
inmutable: no toca la base aunque Firefox esté abierto. Si te falta alguna, avisa cuál.

Podés apilar varias cuentas —una línea por cada una— y Nitter las rota solo.

**Cuando la sesión se queme**, Nitter empieza a contestar HTTP 200 con un RSS sin tweets. El
bot detecta exactamente eso (`entries_have_tweets` en `integrations/twitter.py`), corta el
scaneo y te avisa en `#robot-devil`. La solución es volver a correr el script: si Firefox
sigue logueado, es un comando y un restart.

## Conectarlo al bot

En el `.env`:

```
NITTER_HOST_URL=http://127.0.0.1:19050
```

Sin esa var el bot no lee Twitter y listo; no hay mirrors ajenos a los que caerse.

## Cuánto margen de rate limit queda

`enableDebug = true` expone el estado de las sesiones con el límite que X reporta para cada
endpoint. Los dos endpoints son locales y **no llaman a X**, así que preguntar sale gratis:

```bash
curl -s http://127.0.0.1:19050/.sessions   # remaining / limit / reset por sesión y endpoint
curl -s http://127.0.0.1:19050/.health     # sesiones cargadas y pedidos desde que arrancó
```

Desde Discord es lo mismo pero sin entrar al Pi: **`!nitter`** en `#robot-devil` muestra el
margen por endpoint, cuándo se repone, cuántas cuentas leería el bot ahora mismo y cuándo es
la próxima vuelta.

Eso no es sólo para mirar: es lo que maneja el ritmo. El bot pide `/.sessions` antes de cada
vuelta y de ahí saca cuántas cuentas leer (ver `integrations/nitter.py`). Nunca baja del
colchón —el piso duro de 10 con el que Nitter descarta una sesión, o un cuarto de la ventana,
lo que sea más alto— y de lo que sobra gasta un cuarto, con techo de 3 cuentas por vuelta cada
60-150 minutos (unos 30 feeds por día contra los 54 fijos de antes). Si no hay margen no lee y no avisa nada; si `/.sessions` cambia de formato y no
lo puede parsear, baja a una cuenta por vuelta en vez de asumir que hay aire.

Por eso no hay una constante de "cuántos feeds por hora" para tocar: si querés seguir más
cuentas, no hace falta recortar nada, el presupuesto se acomoda solo. Y si te aparecen sesiones
limitadas seguido, la solución que mejor escala no es pedir menos sino **sumar cuentas**: una
línea más en `sessions.jsonl`, Nitter rota solo llevando el rate limit de cada una por
separado, y el presupuesto del bot suma los márgenes de todas.

Cuando la instancia igual devuelve un 429, el bot no reintenta a la hora: espera 1 h, 2 h, 4 h
y 6 h por cada falla seguida, avisa una sola vez por episodio en `#robot-devil` —con los
números que dice `/.sessions`, así el aviso sirve para algo— y vuelve a avisar cuando la cosa
se normaliza.

## Por qué falló de verdad

**El HTTP que devuelve Nitter no te dice nada.** `rateLimitError()` en `apiutils.nim` es un
cajón de sastre: el mismo cartel *"Instance has been rate limited"* lo tira un challenge de
Cloudflare, una cuenta bloqueada, el rate limit posta, un 404 transitorio, las credenciales
vacías y un `except Exception` que se traga cualquier falla de red del Pi. Un microcorte de
internet te da exactamente el mismo error que una cuenta quemada.

La causa real la escribe por stdout, y esas líneas **no** dependen de `enableDebug`:

| Lo que ves en el log | Qué pasó |
|---|---|
| `[cloudflare] 403 (Just a moment...)` | Challenge: X marcó el tráfico. Esto sí es flagging |
| `Fetch error, ... errors: locked` (o `badToken`, `expiredToken`) | Cuenta bloqueada o sesión vencida → hay que rehacer `sessions.jsonl` |
| `[sessions] 429 error` / `rate limited by api:` | Rate limit de verdad: aflojar o sumar cuentas |
| `error: <excepción>, msg: ...` | Red, DNS o TLS del Pi. No tiene nada que ver con X |
| `[sessions] transient 404 (empty body)` | Hipo de X, se pasa solo |

A mano:

```bash
docker logs --since 24h nitter | grep -E "cloudflare|Fetch error|429|rate limited by api|^error:"
```

Pero no hace falta ir a mirar: **el bot le lee estas líneas al contenedor en el momento en que
le rebota un feed** (`docker logs --since 90s`) y las pega en el aviso de `#robot-devil`, así
el aviso dice la causa en vez de repetir el cartel genérico. `!nitter` muestra las de la última
hora. Para eso el usuario con el que corre el bot tiene que poder ejecutar `docker` (el mismo
que hace `docker compose up -d`); si no puede, el aviso lo aclara y todo lo demás sigue igual.
El nombre del contenedor sale de `NITTER_CONTAINER` en el `.env` (default `nitter`).

Y como de estos logs ahora dependemos, el `compose.yml` les puso techo (`max-size: 10m`,
`max-file: 3`): con `enableDebug` Nitter escribe bastante y la SD del Pi no es infinita.

## Notas

- Escucha solo en `127.0.0.1`: no queda expuesta a la red ni a internet. Es para el bot, no
  para navegar — si querés usarla desde el celular, hacelo por la VPN de WireGuard, no
  abriendo el puerto.
- Puerto `19050` (año de fundación del Rojo), fuera del rango efímero de Linux.
- Redis está capado a 128 MB con `allkeys-lru` y sin persistencia: es cache, no datos.
- El RSS se cachea 60 min (`rssMinutes`): si el bot vuelve a pedir el mismo feed dentro de la
  hora, se lo sirve Redis sin gastar un pedido a X.
- El contenedor de Nitter **no** tiene healthcheck: el único chequeo real sería pedir un RSS,
  y eso gasta rate limit de la sesión cada vez. Para saber si anda, el `curl` de más arriba.
- Consumo total esperado: ~150 MB de RAM.
