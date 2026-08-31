from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings
from pydantic import field_validator

from utils.duration_format import parse_duration


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
    MUSIC_TEXT_CHANNEL_ID: int
    ANNOUNCEMENTS_TEXT_CHANNEL_ID: int
    COMMENTATOR_TEXT_CHANNEL_ID: int
    CLUB_TEXT_CHANNEL_ID: int
    PRESS_TEXT_CHANNEL_ID: int
    GAMES_TEXT_CHANNEL_ID: int
    ROBOT_DEVIL_TEXT_CHANNEL_ID: int
    MINECRAFT_TEXT_CHANNEL_ID: int
    FOOTBALL_FORUM_ID: int
    GAMES_CATEGORY_ID: int
    USER_AGENT: str
    TWITTER_RSS_BRIDGE_URL: str = "https://nitter.net"
    NITTER_INSTANCES_URL: str = "https://raw.githubusercontent.com/wiki/zedeus/nitter/Instances.md"
    NITTER_PROBE_ACCOUNT: str = "Independiente"
    DATABASE_URL: str = "mongodb://localhost:27017/diablo_robot"
    DATABASE_USERNAME: str
    DATABASE_PASSWORD: str
    DJ_COMMAND_PREFIX: str = "m!"
    NOT_ROBOT_DEVIL_USER_TOKEN: str
    NOT_ROBOT_DEVIL_USER_ID: int
    IDLE_VOICE_CHANNEL_ID: int
    DEEPSEEK_API_KEY: str = ""
    TPLINK_ROUTER_HOST: str = "http://192.168.0.1"
    TPLINK_ROUTER_PASSWORD: str = ""
    WIREGUARD_ENDPOINT_HOST: str = ""
    WIREGUARD_ALLOWED_IPS: str = "192.168.0.0/24, 10.5.5.0/24"
    WIREGUARD_MTU: int = 1420
    WIREGUARD_DNS: str = ""
    SECRET_MESSAGE_TTL: str = "1h"
    MINECRAFT_SERVER_HOST: str = "e-cai.mc"
    MINECRAFT_SERVER_PORT: int = 25565
    MINECRAFT_STATUS_MESSAGE_ID: int | None = None
    HARDWARE_MONITOR_HOST: str = ""
    HARDWARE_MONITOR_PORT: int = 8788
    HARDWARE_MONITOR_TOKEN: str = ""
    HARDWARE_MONITOR_STATUS_MESSAGE_ID: int | None = None
    GOOGLE_CALENDAR_ID: str = ""
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""

    @field_validator("TIMEZONE", mode="before")
    @classmethod
    def parse_timezone(cls, v):
        if isinstance(v, ZoneInfo):
            return v
        if isinstance(v, str):
            return ZoneInfo(v)
        raise ValueError(f"TIMEZONE inválido: {v}")

    @field_validator("SECRET_MESSAGE_TTL")
    @classmethod
    def validate_secret_message_ttl(cls, v):
        parse_duration(v)
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        arbitrary_types_allowed = True
        case_sensitive=False
        extra="ignore"


settings = Settings()
