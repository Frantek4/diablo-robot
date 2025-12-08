import os
from dotenv import load_dotenv
import pytz

load_dotenv()

class Settings:
    TIMEZONE = pytz.timezone(os.getenv('TIMEZONE'))

    # Discord Configuration
    PREFIX = os.getenv('PREFIX')
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    GUILD_ID = int(os.getenv('GUILD_ID'))

    # Voice
    GENERAL_VOICE_CHANNEL_ID = int(os.getenv('GENERAL_VOICE_CHANNEL_ID'))
    TERMOS_VOICE_CHANNEL_ID = int(os.getenv('TERMOS_VOICE_CHANNEL_ID'))

    # Text
    GENERAL_TEXT_CHANNEL_ID = int(os.getenv('GENERAL_TEXT_CHANNEL_ID'))

    ANNOUNCEMENTS_TEXT_CHANNEL_ID = int(os.getenv('ANNOUNCEMENTS_TEXT_CHANNEL_ID'))
    CLUB_TEXT_CHANNEL_ID = int(os.getenv('CLUB_TEXT_CHANNEL_ID'))
    PRESS_TEXT_CHANNEL_ID = int(os.getenv('PRESS_TEXT_CHANNEL_ID'))
    
    
    GAMES_TEXT_CHANNEL_ID = int(os.getenv('GAMES_TEXT_CHANNEL_ID'))
    
    ROBOT_DEVIL_TEXT_CHANNEL_ID = int(os.getenv('ROBOT_DEVIL_TEXT_CHANNEL_ID'))

    #Forums
    FOOTBALL_FORUM_ID=int(os.getenv('FOOTBALL_FORUM_ID'))

settings = Settings()