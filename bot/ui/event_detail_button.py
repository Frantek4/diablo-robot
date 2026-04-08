from zoneinfo import ZoneInfo

from discord.ui import View, Button
from discord import ButtonStyle, datetime

from config.settings import settings


class EventRedirectView(View):
    def __init__(self, guild_id: int, event_id: int, event_datetime: datetime):
        
        if event_datetime.tzinfo is None:
            event_datetime = event_datetime.replace(tzinfo=settings.TIMEZONE)
        
        self.event_datetime = event_datetime
        
        now = datetime.now(settings.TIMEZONE)
        
        time_until_event = event_datetime - now
        timeout_seconds = time_until_event.total_seconds()
        
        timeout_seconds = min(timeout_seconds, 86400)
        
        super().__init__(timeout=timeout_seconds)
        
        self.add_item(Button(
            label="Ir al Evento", 
            style=ButtonStyle.primary, 
            url=f"https://discord.com/events/{guild_id}/{event_id}"
        ))