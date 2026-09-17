import asyncio
import random
from datetime import datetime, timedelta, timezone

import instaloader
from instaloader.exceptions import (
    AbortDownloadException,
    BadResponseException,
    ConnectionException,
    LoginRequiredException,
    ProfileNotExistsException,
    QueryReturnedBadRequestException,
    QueryReturnedNotFoundException,
    TooManyRequestsException,
)

from config.settings import settings
from models.social_media import SocialMedia

# Cuánto espero entre cuenta y cuenta. Ahora cada cuenta es un solo pedido, así que el hueco es lo
# único que separa una lectura de la siguiente: un intervalo fijo (los 3s de antes) es un metrónomo
_BETWEEN_ACCOUNTS_SECONDS = (45, 180)
# Los posts viejos no se postean igual, así que no tiene sentido mirar más atrás
_LOOKBACK_DAYS = 7
# Una página del feed son 12 posts. Cortando antes, nunca se pide la página 2
_MAX_POSTS = 5


class AccountFlagged(Exception):
    """Instagram dijo, con todas las letras, que este cliente le parece un bot.

    Es el único error que no se reintenta nunca solo: un checkpoint, un challenge, un
    `feedback_required` o una patada al login no se arreglan esperando, y volver a pedir con la
    cuenta ya marcada es lo que la termina de hundir.
    """

    def __init__(self, reason: str, consumed: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.consumed = consumed


class ProfileMissing(Exception):
    """Esa cuenta no está (la borraron, se cambió el nombre, se puso privada).

    Es de una cuenta sola y no dice nada de la nuestra: se saltea y se sigue. Que llegue a existir
    como excepción aparte es el punto: Instagram devuelve lo mismo cuando la sesión dejó de servir.
    """


class Throttled(Exception):
    """Instagram frenó, pero sin acusar a la cuenta: un 429, un 400 suelto, la conexión cortada.

    Se espera y se vuelve, con el reloj cada vez más largo, pero no se apaga el scaneo.
    """

    def __init__(self, reason: str, consumed: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.consumed = consumed


class _StopInsteadOfWaiting(instaloader.RateController):
    """instaloader, cuando cree que hay que esperar, duerme — adentro de un thread y sin avisar.

    Al volumen que leemos, un tiempo de espera distinto de cero nunca significa "vamos rápido":
    significa que algo ya salió mal y instaloader se anotó un castigo. Mejor cortar la vuelta y que
    se vea en `#robot-devil`, en lugar de tener un thread dormido veinte minutos.
    """

    def sleep(self, secs: float):
        raise Throttled(f"instaloader me quiere hacer esperar {round(secs)}s antes del próximo pedido")


class Instagram:
    def __init__(self, bot):
        self.bot = bot
        self._loader: instaloader.Instaloader | None = None
        self._profiles: dict[str, instaloader.Profile] = {}
        # Si la sesión sirve o no, averiguado una sola vez por vuelta: la respuesta vale para todas
        # las cuentas de esa vuelta y no hay por qué pagar el pedido una vez por cuenta
        self._session_alive: bool | None = None

    def _get_loader(self) -> instaloader.Instaloader:
        if self._loader is not None:
            return self._loader

        loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
            # Un solo intento. El default son tres: ante un 429 instaloader vuelve a pedir dos veces
            # más contra un servidor que ya dijo que no, que es justo lo que no hay que hacer
            max_connection_attempts=1,
            # Cinco minutos colgado adentro de un thread no le sirven a nadie
            request_timeout=30.0,
            rate_controller=lambda ctx: _StopInsteadOfWaiting(ctx),
            # Nunca tocar `i.instagram.com`: es la API privada de la app, y instaloader le manda un
            # fingerprint de iPad hardcodeado en el código. No hace falta — el feed que pedimos ya
            # trae la URL de la imagen, así que apagarlo no cuesta nada y saca de encima el header
            # más fácil de marcar que tenemos
            iphone_support=False,
            # La sesión la hizo un navegador; el User-Agent tiene que seguir siendo el de ese
            # navegador. Cookies de Firefox viajando con un User-Agent de Chrome es una
            # contradicción que se ve del otro lado
            user_agent=settings.IG_USER_AGENT or None,
        )

        try:
            loader.load_session_from_file(settings.IG_USERNAME)
        except FileNotFoundError:
            raise RuntimeError(
                f"No hay sesión de Instagram guardada. "
                f"Ejecutá 'instaloader --load-cookies firefox --sessionfile ~/.config/instaloader/session-{settings.IG_USERNAME}' "
                f"en el servidor para generarla desde un navegador de verdad."
            )

        self._loader = loader
        return loader

    async def check_notifications(self, influencers: list[dict]) -> int:
        """Lee las cuentas que le pasen y devuelve cuántas alcanzó a leer.

        Devolver el número importa: el scheduler mueve el cursor de la rotación sólo por lo que se
        leyó de verdad, así que una vuelta cortada a la mitad no saltea a nadie.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        consumed = 0
        self._session_alive = None

        for index, influencer in enumerate(influencers):
            if index:
                await asyncio.sleep(random.uniform(*_BETWEEN_ACCOUNTS_SECONDS))
            try:
                await self._process_influencer(influencer, cutoff)
            except (AccountFlagged, Throttled) as e:
                # Lo que alcancé a leer antes de chocar; el scheduler mueve el cursor sólo por eso,
                # así una vuelta cortada a la mitad no deja cuentas sin leer para siempre
                e.consumed = consumed
                raise
            except ProfileMissing as e:
                # Ya está confirmado que la sesión sirve, así que esto es de esta cuenta sola
                self._profiles.pop(influencer["name"], None)
                await self.bot.messager.log(
                    f"No encontré la cuenta de Instagram @{influencer['name']}: {e}",
                    level="WARNING",
                )
            consumed += 1

        return consumed

    async def _process_influencer(self, influencer: dict, cutoff: datetime):
        username = influencer["name"]
        loop = asyncio.get_running_loop()

        try:
            posts = await loop.run_in_executor(None, self._fetch_recent_posts, influencer, cutoff)
        except (AbortDownloadException, LoginRequiredException) as e:
            # La sesión murió o Instagram puso un checkpoint. Se tira el loader entero: seguir con
            # el mismo estado en memoria sólo sirve para repetir el pedido que nos marcó
            self._reset()
            raise AccountFlagged(str(e)) from e
        except Throttled:
            self._profiles.pop(username, None)
            raise
        except (ProfileNotExistsException, QueryReturnedNotFoundException) as e:
            # Va antes que ConnectionException a propósito: `QueryReturnedNotFoundException` hereda
            # de ella, y "esa cuenta no existe" es lo contrario de un freno de Instagram
            raise await self._explain(username, e, missing=True) from e
        except (BadResponseException, KeyError, TypeError) as e:
            # Instagram contestó algo que no se parece a un feed. Con la sesión muerta, el pedido
            # vuelve sin `data` y el parseo se rompe justo así
            raise await self._explain(username, e, missing=False) from e
        except (TooManyRequestsException, QueryReturnedBadRequestException, ConnectionException) as e:
            self._profiles.pop(username, None)
            raise Throttled(str(e)) from e

        for post in reversed(posts):
            url = f"https://www.instagram.com/p/{post['shortcode']}/"

            if self.bot.news_dao.exists(url):
                continue

            await self.bot.messager.news(
                type=influencer["source"],
                title=f"{influencer['description']} en Instagram",
                description=post["caption"],
                url=url,
                image_url=post["image_url"],
                publisher=f"Instagram • @{username}",
                color="#E1306C",
            )
            self.bot.news_dao.insert(url)
            await asyncio.sleep(1)

    async def _explain(self, username: str, error: Exception, missing: bool) -> Exception:
        """Instagram dice «esa cuenta no existe» tanto cuando la cuenta no existe como cuando la
        sesión dejó de servir: sin sesión válida la búsqueda vuelve vacía y el resultado es idéntico
        hasta en el texto. Y las dos salidas son opuestas — una cuenta borrada se saltea y se sigue,
        una sesión muerta tiene que frenar todo—, así que la diferencia no se adivina: se pregunta.
        `test_login()` es un pedido y contesta con qué usuario estamos entrando, o con nada.

        Sin eso pasaba lo que pasó: la sesión se cayó y el bot recorrió la rueda entera avisando
        diez veces que diez cuentas que existen no existían, sin frenar nunca.
        """
        if self._session_alive is None:
            loop = asyncio.get_running_loop()
            self._session_alive = await loop.run_in_executor(None, self._check_session)

        if not self._session_alive:
            self._reset()
            return AccountFlagged(
                f"la sesión de @{settings.IG_USERNAME} dejó de servir: Instagram me contestó "
                f"«{error}» para @{username}, pero además no reconoce con qué cuenta entro"
            )
        return ProfileMissing(str(error)) if missing else error

    def _check_session(self) -> bool:
        """Devuelve si la sesión sigue siendo la nuestra. Ante la duda, no: no poder confirmar que
        sirve es motivo de sobra para dejar de pedir."""
        try:
            who = self._get_loader().test_login()
        except Throttled:
            raise
        except Exception:
            return False
        return bool(who) and who.lower() == settings.IG_USERNAME.lower()

    def _profile(self, influencer: dict) -> instaloader.Profile:
        """Una cuenta leída = un pedido, y ese pedido es el feed.

        Librado a sí mismo, instaloader gasta tres pedidos por cuenta y por vuelta: `from_username`
        pega en `fbsearch` —el endpoint del buscador, o sea que el bot "escribe" las mismas diez
        cuentas en la lupa cada hora—, después `get_posts()` pide la ficha del perfil, y recién ahí
        pide el feed. Estando logueados el feed se pide por username, así que los dos primeros no
        aportan nada.

        Entonces: el id se resuelve una sola vez en la vida y se guarda en Mongo, el perfil se arma
        a mano con ese id y se le marca la ficha como ya leída para que `get_posts()` no la pida.
        Eso además saca del medio un camino feo de instaloader: si la ficha del perfil falla, él
        solo dispara una búsqueda extra (`TopSearchResults`) para sugerir cuentas parecidas — pide
        más justo cuando Instagram lo está frenando.
        """
        username = influencer["name"]
        cached = self._profiles.get(username)
        if cached is not None:
            return cached

        loader = self._get_loader()
        account_id = influencer.get("account_id")

        if account_id:
            profile = instaloader.Profile(loader.context, {"username": username, "id": str(account_id)})
        else:
            profile = instaloader.Profile.from_username(loader.context, username)
            self.bot.influencer_dao.set_account_id(username, SocialMedia.INSTAGRAM, str(profile.userid))

        # El nodo que armamos alcanza para pedir el feed; marcarlo completo es lo que evita el
        # pedido de la ficha. Si algún día instaloader necesitara más, `_fetch_recent_posts` tira
        # el perfil del cache y la vuelta siguiente lo resuelve por el camino largo
        profile._has_full_metadata = True
        self._profiles[username] = profile
        return profile

    def _fetch_recent_posts(self, influencer: dict, cutoff: datetime) -> list:
        profile = self._profile(influencer)

        results = []
        for post in profile.get_posts():
            post_dt = post.date_utc.replace(tzinfo=timezone.utc)
            if post_dt < cutoff:
                break

            caption = post.caption or ""
            if len(caption) > 400:
                caption = caption[:400] + "..."

            results.append({
                "shortcode": post.shortcode,
                "caption": caption,
                "image_url": post.url,
            })

            if len(results) >= _MAX_POSTS:
                break

        return results

    def _reset(self):
        self._loader = None
        self._profiles.clear()
        self._session_alive = None
