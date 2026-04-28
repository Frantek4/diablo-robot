from enum import Enum

from models.news_source import NewsSource
from models.social_media import SocialMedia


class AttentionLevel(str, Enum):
    HIGH = "high"
    LOW = "low"


class InfluencerModel:
    def __init__(self, account_id: str, name: str, description: str, platform: SocialMedia, source: NewsSource, attention: AttentionLevel = AttentionLevel.HIGH):
        self.account_id = account_id
        self.name = name
        self.description = description
        self.source = source
        self.platform = platform
        self.attention = attention
