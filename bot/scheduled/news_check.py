from discord.ext import commands, tasks

from scrapers.ole_scraper import OleScraper
from scrapers.tyc_scraper import TycSportsScraper


class NewsCheckScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ole_scraper = OleScraper(bot)
        self.tyc_scraper = TycSportsScraper(bot)



    def cog_unload(self):
        self.news_scheduled_job.cancel()

    
    def start_scheduled_job(self):
        if not self.news_scheduled_job.is_running():
            self.news_scheduled_job.start()


    @tasks.loop(hours=1)
    async def news_scheduled_job(self):
        try:
            await self.ole_scraper.scrape_news()
            await self.tyc_scraper.scrape_news()

        except Exception as e:
            await self.bot.messager.log(f"Error buscando nuevas noticias: {str(e)}")



async def setup(bot):
    await bot.add_cog(NewsCheckScheduler(bot))