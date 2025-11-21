from discord.ui import View, Button
from discord import ButtonStyle, datetime
import pytz

from config.settings import settings


class EventRedirectView(View):
    def __init__(self, guild_id: int, event_id: int, event_datetime: datetime):
        
        if event_datetime.tzinfo is None:
            local_tz = settings.TIMEZONE
            event_datetime = local_tz.localize(event_datetime)
        
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