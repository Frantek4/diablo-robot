import asyncio
from bot.client import DiabloRobot
from config.settings import settings



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
            print(f"{key} no encontrado en las variables de entorno")
            passed = False
    
    return passed



async def main():
    """Main entry point for the bot"""
    if not validate():
        return
    bot = DiabloRobot()

    async with bot:
        await bot.start(settings.DISCORD_TOKEN)



if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Apagando bot manualmente")
    except Exception as e:
        print(f"El bot se rompió por un error: {e}")