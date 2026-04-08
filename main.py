import asyncio
import logging
from bot.client import DiabloRobot
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def validate() -> bool:
    passed = True
    required_keys = [
        'TIMEZONE', 'PREFIX', 'DISCORD_TOKEN', 'GUILD_ID', 'IG_USERNAME', 'IG_PASSWORD',
        'GENERAL_VOICE_CHANNEL_ID', 'TERMOS_VOICE_CHANNEL_ID', 'GENERAL_TEXT_CHANNEL_ID',
        'ANNOUNCEMENTS_TEXT_CHANNEL_ID', 'CLUB_TEXT_CHANNEL_ID', 'PRESS_TEXT_CHANNEL_ID',
        'GAMES_TEXT_CHANNEL_ID', 'ROBOT_DEVIL_TEXT_CHANNEL_ID', 'FOOTBALL_FORUM_ID', 'USER_AGENT'
    ]

    for key in required_keys:
        if not getattr(settings, key, None):
            logger.error(f"Variable de entorno requerida no encontrada: {key}")
            passed = False

    if passed:
        logger.info("Todas las variables de entorno validadas correctamente")

    return passed


async def main():
    """Main entry point for the bot"""
    if not validate():
        logger.critical("Validación fallida. Abortando inicio del bot.")
        return
    bot = DiabloRobot()

    async with bot:
        await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Apagando bot manualmente (KeyboardInterrupt)")
    except Exception as e:
        logger.critical(f"El bot se rompió por un error inesperado: {e}", exc_info=True)