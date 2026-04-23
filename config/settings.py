from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    TIMEZONE: ZoneInfo = ZoneInfo("America/Argentina/Buenos_Aires")
    PREFIX: str = "!"
    DISCORD_TOKEN: str
    GUILD_ID: int
    IG_USERNAME: str = ""
    IG_PASSWORD: str = ""
    GENERAL_VOICE_CHANNEL_ID: int
    TERMOS_VOICE_CHANNEL_ID: int
    GENERAL_TEXT_CHANNEL_ID: int
    ANNOUNCEMENTS_TEXT_CHANNEL_ID: int
    COMMENTATOR_TEXT_CHANNEL_ID: int
    CLUB_TEXT_CHANNEL_ID: int
    PRESS_TEXT_CHANNEL_ID: int
    GAMES_TEXT_CHANNEL_ID: int
    ROBOT_DEVIL_TEXT_CHANNEL_ID: int
    FOOTBALL_FORUM_ID: int
    GAMES_CATEGORY_ID: int
    USER_AGENT: str
    TWITTER_RSS_BRIDGE_URL: str = "http://nitter.net"
    DATABASE_URL: str = "mongodb://localhost:27017/diablo_robot"
    DATABASE_USERNAME: str
    DATABASE_PASSWORD: str

    @field_validator("TIMEZONE", mode="before")
    @classmethod
    def parse_timezone(cls, v):
        if isinstance(v, ZoneInfo):
            return v
        if isinstance(v, str):
            return ZoneInfo(v)
        raise ValueError(f"TIMEZONE inválido: {v}")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        arbitrary_types_allowed = True
        case_sensitive=False
        extra="ignore"


settings = Settings()
