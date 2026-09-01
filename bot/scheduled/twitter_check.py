from datetime import datetime

from discord.ext import commands, tasks

from config.settings import settings
from integrations.twitter import Twitter
from models.social_media import SocialMedia

# No tiene sentido machacar de madrugada: nadie tuitea y el rate limit de X se paga igual
_ACTIVE_HOURS = set(range(0, 2)) | set(range(8, 24))
# Cuántas cuentas leo por vuelta: el resto queda para las vueltas siguientes
_BATCH_SIZE = 3


class TwitterCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.twitter = Twitter(bot)
        self._cursor = 0

    def cog_unload(self):
        self.twitter_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.twitter_scheduled_job.is_running():
            self.twitter_scheduled_job.start()

    @tasks.loop(hours=1)
    async def twitter_scheduled_job(self):
        if datetime.now(settings.TIMEZONE).hour not in _ACTIVE_HOURS:
            return

        influencers = self.bot.influencer_dao.get_by_platform(SocialMedia.TWITTER)
        if not influencers:
            return

        batch = self._next_batch(influencers)

        try:
            consumed = await self.twitter.check_rss_notifications(batch)
        except Exception as e:
            await self.bot.messager.log(f"No pude escanear Twitter: {e}", level="ERROR", exc=e)
            return

        # Avanzo solo por lo que realmente leí: lo que quedó sin leer va de nuevo la vuelta que viene
        self._cursor = (self._cursor + consumed) % len(influencers)

    def _next_batch(self, influencers: list) -> list:
        """La ventana que toca esta vuelta; el cursor avanza después, y solo por lo que se leyó."""
        self._cursor %= len(influencers)
        batch = (influencers + influencers)[self._cursor:self._cursor + _BATCH_SIZE]
        return batch[:len(influencers)]


async def setup(bot):
    await bot.add_cog(TwitterCheckScheduler(bot))
