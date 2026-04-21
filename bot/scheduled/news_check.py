import logging
from discord.ext import commands, tasks

from integrations.ole import OleScraper
from integrations.tyc import TycSportsScraper

logger = logging.getLogger(__name__)


class NewsCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ole_scraper = OleScraper(bot)
        self.tyc_scraper = TycSportsScraper(bot)

    def cog_unload(self):
        self.news_scheduled_job.cancel()

    def start_scheduled_job(self):
        if not self.news_scheduled_job.is_running():
            logger.info("Starting NewsCheckScheduler (hourly for OLE and TYC)")
            self.news_scheduled_job.start()
        else:
            logger.info("NewsCheckScheduler already running")

    @tasks.loop(hours=1)
    async def news_scheduled_job(self):
        logger.info("NewsCheckScheduler: Starting hourly news check cycle (OLE + TYC)")
        try:
            logger.info("Checking OLE news")
            await self.ole_scraper.scrape_news()
            
            logger.info("Checking TYC Sports news")
            await self.tyc_scraper.scrape_news()
            
            logger.info("Hourly news check cycle completed")

        except Exception as e:
            logger.error(f"Error in news check cycle: {str(e)}", exc_info=True)
            await self.bot.messager.log(f"Error buscando nuevas noticias: {str(e)}")


async def setup(bot):
    await bot.add_cog(NewsCheckScheduler(bot))