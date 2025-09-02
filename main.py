import asyncio
from bot.client import DiabloRobot
from config.settings import settings

async def main():
    """Main entry point for the bot"""
    if not settings.DISCORD_TOKEN:
        print("DISCORD_TOKEN no encontrado en las variables de entorno")
        return
    
    if not settings.GUILD_ID:
        print("GUILD_ID no encontrado en las variables de entorno")
        return
        
    if not settings.ROBOT_DEVIL_TEXT_CHANNEL_ID:
        print("ROBOT_DEVIL_TEXT_CHANNEL_ID no encontrado en las variables de entorno")
        return
        
    if not settings.MATCH_VOICE_CHANNEL_ID:
        print("MATCH_VOICE_CHANNEL_ID no encontrado en las variables de entorno")
        return
    
    if not settings.MATCH_VOICE_CHANNEL_NAME:
        print("MATCH_VOICE_CHANNEL_NAME no encontrado en las variables de entorno")
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