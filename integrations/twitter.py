import asyncio
import json
from datetime import datetime, timedelta, timezone
from os.path import expanduser

import aiohttp

from config.settings import settings
from integrations.social_errors import AccountFlagged, ClientOutdated, Throttled, dig
from integrations.x_api import HomeQuery, RateWindow, XClient
from models.social_media import SocialMedia

# Los tweets viejos no se postean igual, así que no tiene sentido mirar más atrás
_LOOKBACK_DAYS = 7
_TEXT_CHARS = 400
_QUOTE_CHARS = 200
# Cuántas cuentas desconocidas guardo de cada vuelta, para mostrarlas en `!twitter`
_UNKNOWN_SHOWN = 5


def session_path() -> str:
    return expanduser(f"~/.config/diablo-robot/x-session-{settings.X_USERNAME}.json")


class Twitter:
    """Lee la home "Siguiendo" de la cuenta del bot y postea lo de las cuentas de la tabla.

    Un pedido por vuelta, sea cual sea la cantidad de cuentas: la lista de qué se lee la lleva X
    (a quién sigue la cuenta) y la de dónde se postea la lleva Mongo (`influencers`, con su canal
    y su descripción). Un tweet de alguien que no está en la tabla se ignora.
    """

    def __init__(self, bot):
        self.bot = bot
        self.dao = bot.twitter_state_dao
        self._client: XClient | None = None

    @property
    def window(self) -> RateWindow | None:
        """Lo último que X dijo del rate limit de la home. Lo guarda el scheduler en Mongo."""
        return self._client.window if self._client else None

    def _get_client(self) -> XClient:
        if self._client is not None:
            return self._client
        try:
            with open(session_path(), encoding="utf-8") as f:
                session = json.loads(f.readline())
        except FileNotFoundError:
            # Sin sesión no sale ningún pedido, pero tampoco tiene sentido despertarse cada vuelta a
            # descubrir lo mismo: es un freno como cualquier otro, hasta que alguien la genere
            raise AccountFlagged(f"no hay sesión guardada en {session_path()}", session_dead=True)
        self._client = XClient(session["auth_token"], session["ct0"],
                               settings.X_USER_AGENT or settings.USER_AGENT)
        return self._client

    async def follow(self, screen_name: str) -> str:
        """Sigue una cuenta desde la del bot y devuelve su id numérico, para guardarlo en la tabla.
        Son dos pedidos: el id (X no sigue por usuario) y el follow."""
        client = self._get_client()
        async with aiohttp.ClientSession() as session:
            try:
                user_id = await client.user_id(session, screen_name)
                await client.follow(session, user_id)
            except AccountFlagged:
                self.reset()
                raise
        return user_id

    def reset(self):
        """La próxima vuelta relee las cookies del disco, por si rehicieron la sesión."""
        self._client = None

    async def read_home(self) -> dict:
        """Una vuelta: un pedido a la home. Devuelve lo que vio, para mostrarlo en `!twitter`."""
        client = self._get_client()
        state = self.dao.get()
        query = (HomeQuery(state["home_query_id"], state["home_features"])
                 if state.get("home_query_id") and state.get("home_features") is not None else None)

        async with aiohttp.ClientSession() as session:
            try:
                if query is None:
                    query = await client.discover_home_query(session)
                    state["home_query_verified"] = False
                    self.dao.save(home_query_id=query.query_id, home_features=query.features,
                                  home_query_verified=False)
                response = await client.home_latest(session, query)
            except AccountFlagged:
                self.reset()
                raise
            except Throttled as e:
                if not e.stale_query:
                    raise
                if not state.get("home_query_verified"):
                    # Lo rechazó recién buscado: buscarlo otra vez va a dar lo mismo. Lo que cambió
                    # es la forma del pedido, y eso se arregla en el código, no esperando
                    raise ClientOutdated(f"X rechaza el pedido a la home aun con el queryId recién "
                                         f"sacado de x.com ({e.reason})") from e
                # Se busca de nuevo en la próxima vuelta, no ahora: reintentar en el acto es
                # mandarle a X un segundo pedido justo después de uno que rechazó
                self.dao.save(home_query_id=None, home_features=None, home_query_verified=False)
                raise

        if not state.get("home_query_verified"):
            self.dao.save(home_query_verified=True)

        routing = {i["name"].lower(): i for i in self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)}
        cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        tweets = _timeline_tweets(response)
        matched, posted, unknown = 0, 0, {}

        for tweet in reversed(tweets):
            # El autor es el que aparece en la home: en un RT, la cuenta que seguimos y no la original
            author = _screen_name(tweet) or ""
            influencer = routing.get(author.lower())
            if influencer is None:
                unknown[author] = None
                continue
            matched += 1

            post = _to_post(tweet)
            if not post or post["date"] < cutoff or self.bot.news_dao.exists(post["url"]):
                continue

            await self.bot.messager.news(
                type=influencer["source"],
                title=f"{influencer['description']} en Twitter",
                description=post["description"],
                url=post["url"],
                image_url=post["image_url"],
                publisher=f"Twitter • {influencer['name']}",
                color="#00acee",
            )
            self.bot.news_dao.insert(post["url"])
            posted += 1
            await asyncio.sleep(1)

        return {"seen": len(tweets), "matched": matched, "posted": posted,
                "unknown": [name for name in unknown if name][:_UNKNOWN_SHOWN]}


# Lo que sigue está portado de `parser.nim` de Nitter (`parseGraphTimeline`, `parseGraphTweet`,
# `parseGraphUser`), recortado a lo que lleva un embed. Las entradas de la home tienen la misma forma
# que las de un perfil. X sirve dos formas de tweet según el endpoint: la vieja, con todo adentro de `legacy`, y la de los endpoints V2, con `details`,
# `url_entities` y `media_entities`. Se leen las dos

def _timeline_tweets(response: dict) -> list[dict]:
    """Los tweets de la home, sin los promocionados. Si la respuesta traía tweets y no pude leer ninguno,
    X cambió el formato: eso tiene que verse, no pasar por "no hay nada nuevo"."""
    instructions = (dig(response, "data", "home", "home_timeline_urt", "instructions")
                    or dig(response, "data", "home", "timeline_response", "timeline", "instructions") or [])

    results = []
    for instruction in instructions:
        for entry in instruction.get("entries") or []:
            entry_id = entry.get("entryId") or entry.get("entry_id") or ""
            if entry_id.startswith("tweet"):
                result = _entry_tweet(entry.get("content"))
                if result:
                    results.append(result)
            elif "-conversation-" in entry_id:
                for item in dig(entry, "content", "items") or []:
                    result = _entry_tweet(item.get("item"))
                    if result:
                        results.append(result)

    tweets = [tweet for tweet in (_unwrap(result) for result in results) if tweet]
    if results and not tweets:
        raise ClientOutdated("X devolvió tweets en un formato que no sé leer: hay que actualizar el parser")
    return tweets


def _entry_tweet(content) -> dict | None:
    return (dig(content, "content", "tweet_results", "result")
            or dig(content, "itemContent", "tweet_results", "result")
            or dig(content, "content", "tweetResult", "result"))


def _unwrap(result: dict) -> dict | None:
    """El tweet en sí, o None si es un tombstone o algo que no se puede mostrar."""
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet") or {}
    if "legacy" not in result and "details" not in result:
        return None
    return result


def _to_post(tweet: dict) -> dict | None:
    """Un retweet se postea como el tweet original, con su link: así el mismo tweet retuiteado por
    dos cuentas que seguimos se deduplica solo."""
    date = _date(tweet)
    retweeted = _retweeted(tweet)
    shown = retweeted or tweet
    author = _screen_name(shown)
    if not author or date is None:
        return None

    parts = []
    if retweeted:
        parts.append(f"🔁 RT de @{author}")
    parts.append(_text(shown, _TEXT_CHARS))

    quote = _quoted(shown)
    if quote:
        parts.append(f"\n> **{_display_name(quote)}**\n> {_text(quote, _QUOTE_CHARS)}")

    return {
        "url": f"https://x.com/{author}/status/{shown.get('rest_id')}",
        "date": date,
        "description": "\n".join(parts),
        "image_url": _first_image(shown) or (_first_image(quote) if quote else None),
    }


def _retweeted(tweet: dict) -> dict | None:
    for path in (("legacy", "retweeted_status_result", "result"),
                 ("legacy", "repostedStatusResults", "result"),
                 ("repostedStatusResults", "result")):
        result = dig(tweet, *path)
        if isinstance(result, dict):
            return _unwrap(result)
    return None


def _quoted(tweet: dict) -> dict | None:
    for path in (("quoted_status_result", "result"), ("quotedPostResults", "result"),
                 ("quoted_tweet_results", "result")):
        result = dig(tweet, *path)
        if isinstance(result, dict):
            return _unwrap(result)
    return None


def _user(tweet: dict) -> dict:
    core = tweet.get("core") or {}
    return dig(core, "user_results", "result") or dig(core, "user_result", "result") or {}


def _screen_name(tweet: dict) -> str | None:
    user = _user(tweet)
    return dig(user, "core", "screen_name") or dig(user, "legacy", "screen_name")


def _display_name(tweet: dict) -> str:
    user = _user(tweet)
    return dig(user, "core", "name") or dig(user, "legacy", "name") or f"@{_screen_name(tweet)}"


def _date(tweet: dict) -> datetime | None:
    millis = dig(tweet, "details", "created_at_ms")
    if millis:
        return datetime.fromtimestamp(int(millis) / 1000, timezone.utc)
    created = dig(tweet, "legacy", "created_at")
    try:
        return datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y") if created else None
    except ValueError:
        return None


def _text(tweet: dict, limit: int) -> str:
    """El texto con los t.co cambiados por el link de verdad, y sin el link de su propia foto ni
    las menciones de respuesta, que X deja afuera de `display_text_range`."""
    note = dig(tweet, "note_tweet", "note_tweet_results", "result")
    if note and note.get("text"):
        text, urls = note["text"], dig(note, "entity_set", "urls") or []
    else:
        source = tweet.get("details") or tweet.get("legacy") or {}
        text = source.get("full_text", "")
        span = source.get("display_text_range")
        if isinstance(span, list) and len(span) == 2:
            text = text[span[0]:span[1]]
        urls = tweet.get("url_entities") or dig(tweet, "legacy", "entities", "urls") or []

    for url in urls:
        if url.get("url"):
            text = text.replace(url["url"], url.get("expanded_url") or url["url"])
    text = text.strip()
    return text[:limit] + "..." if len(text) > limit else text


def _first_image(tweet: dict) -> str | None:
    """La primera foto, o la miniatura del primer video o gif."""
    for entity in tweet.get("media_entities") or []:
        info = dig(entity, "media_results", "result", "media_info") or {}
        image = info.get("original_img_url") or dig(info, "preview_image", "original_img_url")
        if image:
            return image
    for media in dig(tweet, "legacy", "extended_entities", "media") or []:
        if media.get("media_url_https"):
            return media["media_url_https"]
    return None

