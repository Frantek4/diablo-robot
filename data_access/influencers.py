from tinydb import TinyDB, Query

from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia

class InfluencerDAO:
    def __init__(self):
        self.table = TinyDB('database.json').table('influencers')

    def insert(self, model: InfluencerModel) -> bool:
        if self.exists(model.name, model.platform):
            return False  # Usuario ya existe para esa plataforma
            
        self.table.insert({
            'name': model.name,
            'description': model.description,
            'source': model.source.value,
            'platform': model.platform.value
        })
        return True

    def exists(self, name: str, platform: SocialMedia) -> bool:
        query = Query()
        result = self.table.search((query.name == name) & (query.platform == platform.value))
        return len(result) > 0

    def get_by_source(self, source: NewsSource) -> list:
        query = Query()
        return self.table.search(query.source == source.value)

    def get_by_platform(self, platform: SocialMedia) -> list:
        query = Query()
        return self.table.search(query.platform == platform.value)