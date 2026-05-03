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
        logger.info("check_upcoming_matches: tick")
        try:
            next_match = self.bot.fixture_dao.get_next_match()
            if not next_match:
                logger.info("check_upcoming_matches: no hay próximo partido en la DB")
                return
            if not next_match.match_id or not next_match.id:
                logger.warning(f"check_upcoming_matches: partido sin match_id o id: {next_match}")
                return

            logger.info(
                f"check_upcoming_matches: próximo partido = {next_match.match_id} "
                f"({next_match.home_team} vs {next_match.away_team}), "
                f"status={next_match.status}, fecha={next_match.match_date}"
            )

            commentator = self.bot.get_cog('LiveMatchCommentator')
            if commentator is None:
                logger.error("check_upcoming_matches: LiveMatchCommentator cog no encontrado")
                return

            if next_match.match_id in commentator.active_trackers:
                logger.info(f"check_upcoming_matches: {next_match.match_id} ya está siendo trackeado")
                return

            now = datetime.now(settings.TIMEZONE)
            time_to_match = next_match.match_date - now
            logger.info(f"check_upcoming_matches: tiempo al partido = {time_to_match}")

            if time_to_match > timedelta(minutes=30):
                logger.info("check_upcoming_matches: faltan más de 30 minutos, esperando")
                return

            logger.info(f"check_upcoming_matches: arrancando tracking de {next_match.match_id}")

            if next_match.status == FixtureStatus.SCHEDULED:
                self.bot.fixture_dao.update_status(next_match.id, FixtureStatus.LIVE)
                logger.info(f"check_upcoming_matches: status actualizado a LIVE para {next_match.id}")

            await commentator.start_tracking(next_match.match_id, next_match.id)
            logger.info(f"check_upcoming_matches: start_tracking llamado para {next_match.match_id}")

        except Exception as e:
            logger.exception(f"check_upcoming_matches: excepción no manejada: {e}")
            if self.bot.messager:
                await self.bot.messager.log(f"No pude chequear los próximos partidos: {e}", level="ERROR", exc=e)


async def setup(bot):
    await bot.add_cog(CommentatorScheduler(bot))
