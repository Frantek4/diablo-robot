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

Con eso entra al repositorio de mirrors como `source=self` y **rankea antes que cualquier
pública**, andando o no. `!nitter` la muestra marcada como "la mía".

## Notas

- Escucha solo en `127.0.0.1`: no queda expuesta a la red ni a internet. Es para el bot, no
  para navegar — si querés usarla desde el celular, hacelo por la VPN de WireGuard, no
  abriendo el puerto.
- Puerto `19050` (año de fundación del Rojo), fuera del rango efímero de Linux.
- Redis está capado a 128 MB con `allkeys-lru` y sin persistencia: es cache, no datos.
- Consumo total esperado: ~150 MB de RAM.
