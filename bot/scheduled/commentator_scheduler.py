import logging
from datetime import datetime, timedelta
from discord.ext import commands, tasks
from config.settings import settings
from models.fixture_status import FixtureStatus

logger = logging.getLogger(__name__)


class CommentatorScheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.check_upcoming_matches.cancel()

    def start_scheduled_job(self):
        logger.info("CommentatorScheduler.start_scheduled_job() llamado")
        if not self.check_upcoming_matches.is_running():
            self.check_upcoming_matches.start()
            logger.info("Loop check_upcoming_matches iniciado")
        else:
            logger.info("Loop check_upcoming_matches ya estaba corriendo")

    @tasks.loop(minutes=1)
    async def check_upcoming_matches(self):
        try:
            next_match = self.bot.fixture_dao.get_next_match()
            if not next_match:
                return
            if not next_match.match_id or not next_match.id:
                logger.warning(f"check_upcoming_matches: partido sin match_id o id: {next_match}")
                return

            commentator = self.bot.get_cog('LiveMatchCommentator')
            if commentator is None:
                logger.error("check_upcoming_matches: LiveMatchCommentator cog no encontrado")
                return

            if next_match.match_id in commentator.active_trackers:
                return

            now = datetime.now(settings.TIMEZONE)
            time_to_match = next_match.match_date - now

            if time_to_match > timedelta(minutes=30):
                return

            # Si ya estaba LIVE (y no es este tick el que lo pone en LIVE), es que el bot
            # se reinició a mitad del partido: retomamos sin reanunciar todo lo ya visto.
            resume = next_match.status == FixtureStatus.LIVE

            if next_match.status == FixtureStatus.SCHEDULED:
                self.bot.fixture_dao.update_status(next_match.id, FixtureStatus.LIVE)

            logger.info(f"check_upcoming_matches: arrancando tracking de {next_match.match_id} (resume={resume})")
            await commentator.start_tracking(next_match.match_id, next_match.id, resume=resume)

        except Exception as e:
            logger.exception(f"check_upcoming_matches: excepción no manejada: {e}")
            if self.bot.messager:
                await self.bot.messager.log(f"No pude chequear los próximos partidos: {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(CommentatorScheduler(bot))
