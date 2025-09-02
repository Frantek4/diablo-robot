import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TIMEZONE = os.getenv('TIMEZONE')
    # Discord Configuration
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    GUILD_ID = int(os.getenv('GUILD_ID'))
    MATCH_VOICE_CHANNEL_ID = int(os.getenv('MATCH_VOICE_CHANNEL_ID'))
    MATCH_VOICE_CHANNEL_NAME = os.getenv('MATCH_VOICE_CHANNEL_NAME')
    ROBOT_DEVIL_TEXT_CHANNEL_ID = int(os.getenv('ROBOT_DEVIL_TEXT_CHANNEL_ID'))
    PREFIX = os.getenv('PREFIX')
    

settings = Settings()