from datetime import datetime, date
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


def parse_date_ddmmyyyy(text: str) -> date | None:
    """Parses 'weekday DD/M/YYYY' or plain 'DD/M/YYYY'. Returns None if unparseable."""
    part = text.strip().split()[-1]
    try:
        return datetime.strptime(part, "%d/%m/%Y").date()
    except ValueError:
        return None


def is_recent(d: date, days: int = 7) -> bool:
    today = datetime.now(settings.TIMEZONE).date()
    return (today - d).days <= days
