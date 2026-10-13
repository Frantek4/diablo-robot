import asyncio
from datetime import datetime, timedelta

import aiohttp

from config.settings import settings
from integrations.instagram_api import InstagramClient, feed_media, media_to_post
from integrations.social_errors import AccountFlagged, dig
from models.social_media import SocialMedia

# Los posts viejos no se postean igual, así que no tiene sentido mirar más atrás
_LOOKBACK_DAYS = 7
# Cuántas cuentas desconocidas guardo de cada vuelta, para mostrarlas en `!instagram`
_UNKNOWN_SHOWN = 5


class Instagram:
    """Lee la home de la cuenta del bot y postea lo de las cuentas de la tabla.

    Un pedido por vuelta, sea cual sea la cantidad de cuentas: la lista de qué se lee la lleva
    Instagram (a quién sigue la cuenta) y la de dónde se postea la lleva Mongo (`influencers`). Un
    post de alguien que no está en la tabla —sugeridos incluidos— se ignora.
    """

    def __init__(self, bot):
        self.bot = bot
        self._client: InstagramClient | None = None

    def _get_client(self) -> InstagramClient:
        if self._client is None:
            self._client = InstagramClient.from_session_file()
        return self._client

    def reset(self):
        """La próxima vuelta relee la sesión del disco, por si la rehicieron."""
        self._client = None

    async def read_home(self) -> dict:
        """Una vuelta: un pedido a la home. Devuelve lo que vio, para mostrarlo en `!instagram`."""
        client = self._get_client()
        async with aiohttp.ClientSession() as session:
            try:
                response = await client.home(session)
            except AccountFlagged:
                self.reset()
                raise

        routing = {i["name"].lower(): i for i in self.bot.influencer_dao.get_by_platform(SocialMedia.INSTAGRAM)}
        cutoff = datetime.now(settings.TIMEZONE) - timedelta(days=_LOOKBACK_DAYS)
        media = feed_media(response)
        matched, posted, unknown = 0, 0, {}

        # La home de Instagram no viene en orden cronológico: se postea del más viejo al más nuevo
        for item in sorted(media, key=lambda m: int(m.get("taken_at") or 0)):
            author = dig(item, "user", "username")
            influencer = routing.get(author.lower())
            if influencer is None:
                unknown[author] = None
                continue
            matched += 1

            post = media_to_post(item)
            if post["date"] < cutoff or self.bot.news_dao.exists(post["url"]):
                continue

            await self.bot.messager.news(
                type=influencer["source"],
                title=f"{influencer['description']} en Instagram",
                description=post["caption"],
                url=post["url"],
                image_url=post["image_url"],
                publisher=f"Instagram • @{author}",
                color="#E1306C",
            )
            self.bot.news_dao.insert(post["url"])
            posted += 1
            await asyncio.sleep(1)

        return {"seen": len(media), "matched": matched, "posted": posted,
                "unknown": list(unknown)[:_UNKNOWN_SHOWN]}

    async def follow(self, username: str) -> str:
        """Sigue una cuenta desde la del bot y devuelve su id numérico, para guardarlo en la tabla.
        Son dos pedidos: la ficha del perfil (de ahí sale el id) y el follow."""
        client = self._get_client()
        async with aiohttp.ClientSession() as session:
            try:
                user_id = await client.user_id(session, username)
                await client.follow(session, user_id)
            except AccountFlagged:
                self.reset()
                raise
        return user_id
