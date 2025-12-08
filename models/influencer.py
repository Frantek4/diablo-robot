from models.news_source import NewsSource
from models.social_media import SocialMedia

class InfluencerModel:
    def __init__(self, name: str, description: str, platform: SocialMedia, source: NewsSource):
        self.name = name
        self.description = description
        self.source = source
        self.platform = platform
