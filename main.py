import asyncio
from bot.client import DiabloRobot
from config.settings import settings



def validate() -> bool:
    passed = True

    if not settings.TIMEZONE:
        print("DISCORD_TOKEN no encontrado en las variables de entorno")
        passed = False
    

    if not settings.PREFIX:
        print("PREFIX no encontrado en las variables de entorno")
        passed = False

    if not settings.DISCORD_TOKEN:
        print("DISCORD_TOKEN no encontrado en las variables de entorno")
        passed = False
    
    if not settings.GUILD_ID:
        print("GUILD_ID no encontrado en las variables de entorno")
        passed = False
    

    if not settings.GENERAL_CATEGORY_ID:
        print("GENERAL_CATEGORY_ID no encontrado en las variables de entorno")
        passed = False

    if not settings.GENERAL_CATEGORY_NAME:
        print("GENERAL_CATEGORY_NAME no encontrado en las variables de entorno")
        passed = False

    if not settings.GAMES_CATEGORY_ID:
        print("GAMES_CATEGORY_ID no encontrado en las variables de entorno")
        passed = False

    if not settings.GAMES_CATEGORY_NAME:
        print("GAMES_CATEGORY_NAME no encontrado en las variables de entorno")
        passed = False

        
    if not settings.GENERAL_VOICE_CHANNEL_ID:
        print("GENERAL_VOICE_CHANNEL_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.GENERAL_VOICE_CHANNEL_NAME:
        print("GENERAL_VOICE_CHANNEL_NAME no encontrado en las variables de entorno")
        passed = False

    if not settings.TERMOS_VOICE_CHANNEL_ID:
        print("TERMOS_VOICE_CHANNEL_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.TERMOS_VOICE_CHANNEL_NAME:
        print("TERMOS_VOICE_CHANNEL_NAME no encontrado en las variables de entorno")
        passed = False


    if not settings.GENERAL_TEXT_CHANNEL_ID:
        print("GENERAL_TEXT_CHANNEL_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.GENERAL_TEXT_CHANNEL_NAME:
        print("GENERAL_TEXT_CHANNEL_NAME no encontrado en las variables de entorno")
        passed = False

    if not settings.ANNOUNCEMENTS_TEXT_CHANNEL_ID:
        print("ANNOUNCEMENTS_TEXT_CHANNEL_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.ANNOUNCEMENTS_TEXT_CHANNEL_NAME:
        print("ANNOUNCEMENTS_TEXT_CHANNEL_NAME no encontrado en las variables de entorno")
        passed = False

    if not settings.GAMES_TEXT_CHANNEL_ID:
        print("GAMES_TEXT_CHANNEL_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.GAMES_TEXT_CHANNEL_NAME:
        print("GAMES_TEXT_CHANNEL_NAME no encontrado en las variables de entorno")
        passed = False
    
    if not settings.ROBOT_DEVIL_TEXT_CHANNEL_ID:
        print("ROBOT_DEVIL_TEXT_CHANNEL_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.ROBOT_DEVIL_TEXT_CHANNEL_NAME:
        print("ROBOT_DEVIL_TEXT_CHANNEL_NAME no encontrado en las variables de entorno")
        passed = False

    if not settings.FOOTBALL_FORUM_ID:
        print("FOOTBALL_FORUM_ID no encontrado en las variables de entorno")
        passed = False
    
    if not settings.FOOTBALL_FORUM_NAME:
        print("FOOTBALL_FORUM_NAME no encontrado en las variables de entorno")
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