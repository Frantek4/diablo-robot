from models.news_source import NewsSource
from models.social_media import SocialMedia

class InfluencerModel:
    def __init__(self, account_id: str, name: str, description: str, platform: SocialMedia, source: NewsSource):
        self.account_id = account_id
        self.name = name
        self.description = description
        self.source = source
        self.platform = platform
