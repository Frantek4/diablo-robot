import logging
from discord.ext import commands, tasks

from integrations.doble_amarilla import DobleAmarillaScraper
from integrations.ole import OleScraper
from integrations.tyc import TycSportsScraper

logger = logging.getLogger(__name__)


class NewsCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ole_scraper = OleScraper(bot)
        self.tyc_scraper = TycSportsScraper(bot)
        self.doble_amarilla_scraper = DobleAmarillaScraper(bot)

    def cog_unload(self):
        self.news_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.news_scheduled_job.is_running():
            self.news_scheduled_job.start()

    @tasks.loop(hours=1)
    async def news_scheduled_job(self):
        await self.ole_scraper.scrape_news()
        await self.tyc_scraper.scrape_news()
        await self.doble_amarilla_scraper.scrape_news()


async def setup(bot):
    await bot.add_cog(NewsCheckScheduler(bot))