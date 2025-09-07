from dataclasses import dataclass
from config.settings import settings
from utils.string_format import to_kebab_case

@dataclass
class GameChannel:
    name: str
    message_id: int
    text_channel_id: int | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GameChannel':
        text_channel_id = data.get('text_channel_id')
        
        return cls(
            name=data['game_name'],
            message_id=data['message_id'],
            text_channel_id=text_channel_id
        )
    
    def to_dict(self) -> dict:
        return {
            'game_name': self.name,
            'message_id': self.message_id,
            'text_channel_id': self.text_channel_id
        }
    
    @property
    def text_channel_name(self) -> str:
        return to_kebab_case(self.name)
    
    @property
    def message_url(self) -> str:
        return f"https://discord.com/channels/{settings.GUILD_ID}/{self.message_id}"
