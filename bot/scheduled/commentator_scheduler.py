from datetime import datetime, timedelta
from discord.ext import commands, tasks
from config.settings import settings
from models.fixture_status import FixtureStatus


class CommentatorScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.check_upcoming_matches.cancel()

    def start_scheduled_job(self):
        if not self.check_upcoming_matches.is_running():
            self.check_upcoming_matches.start()

    @tasks.loop(minutes=1)
    async def check_upcoming_matches(self):
        try:
            next_match = self.bot.fixture_dao.get_next_match()
            if not next_match or not next_match.match_id or not next_match.id:
                return

            commentator = self.bot.get_cog('LiveMatchCommentator')
            if commentator is None:
                await self.bot.messager.log("No encontré el cog LiveMatchCommentator.", level="ERROR")
                return

            if next_match.match_id in commentator.active_trackers:
                return

            now = datetime.now(settings.TIMEZONE)
            if next_match.match_date - now > timedelta(minutes=30):
                return

            if next_match.status == FixtureStatus.SCHEDULED:
                self.bot.fixture_dao.update_status(next_match.id, FixtureStatus.LIVE)

            await commentator.start_tracking(next_match.match_id, next_match.id)

        except Exception as e:
            await self.bot.messager.log(f"No pude chequear los próximos partidos: {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(CommentatorScheduler(bot))
