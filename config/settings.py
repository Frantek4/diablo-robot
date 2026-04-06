import os
from dotenv import load_dotenv
import pytz

load_dotenv()

class Settings:
    def _get_required(self, key: str) -> str:
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"CRITICAL ERROR: Environment variable '{key}' is missing. The bot cannot start without it.")
        return value

    def _get_int(self, key: str) -> int:
        value = self._get_required(key)
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"CRITICAL ERROR: Environment variable '{key}' must be an integer. Got: '{value}'")

    TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'America/Argentina/Buenos_Aires'))

    # Discord Configuration
    PREFIX = os.getenv('PREFIX', '!')
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') # Validated in main.py but checked here via _get_required if needed

    def __init__(self):
        self.DISCORD_TOKEN = self._get_required('DISCORD_TOKEN')
        self.GUILD_ID = self._get_int('GUILD_ID')
        
        # Instagram
        self.IG_USERNAME = self._get_required('IG_USERNAME')
        self.IG_PASSWORD = self._get_required('IG_PASSWORD')
        self.RECAPTCHA_API_KEY = os.getenv('RECAPTCHA_API_KEY')
        self.RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY')

        # Channels
        self.GENERAL_VOICE_CHANNEL_ID = self._get_int('GENERAL_VOICE_CHANNEL_ID')
        self.TERMOS_VOICE_CHANNEL_ID = self._get_int('TERMOS_VOICE_CHANNEL_ID')
        self.GENERAL_TEXT_CHANNEL_ID = self._get_int('GENERAL_TEXT_CHANNEL_ID')
        self.ANNOUNCEMENTS_TEXT_CHANNEL_ID = self._get_int('ANNOUNCEMENTS_TEXT_CHANNEL_ID')
        self.CLUB_TEXT_CHANNEL_ID = self._get_int('CLUB_TEXT_CHANNEL_ID')
        self.PRESS_TEXT_CHANNEL_ID = self._get_int('PRESS_TEXT_CHANNEL_ID')
        self.GAMES_TEXT_CHANNEL_ID = self._get_int('GAMES_TEXT_CHANNEL_ID')
        self.ROBOT_DEVIL_TEXT_CHANNEL_ID = self._get_int('ROBOT_DEVIL_TEXT_CHANNEL_ID')
        self.GAMES_CATEGORY_ID = self._get_int('GAMES_CATEGORY_ID')
        self.FOOTBALL_FORUM_ID = self._get_int('FOOTBALL_FORUM_ID')
        self.COMMENTATOR_TEXT_CHANNEL_ID = self._get_int('COMMENTATOR_TEXT_CHANNEL_ID')
        self.USER_AGENT = self._get_required('USER_AGENT')

settings = Settings()