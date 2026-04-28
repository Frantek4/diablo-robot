from datetime import datetime
from config.settings import settings


def parse_datetime(value) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return to_local(dt)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone(settings.TIMEZONE)
    return dt.replace(tzinfo=settings.TIMEZONE)


def format_datetime(dt: datetime) -> str:
    return to_local(dt).strftime("%d/%m/%Y %H:%M")
