from models.influencer import InfluencerModel
from models.news_source import NewsSource
from models.social_media import SocialMedia
from config.database import db

class InfluencerDAO:
    def __init__(self):
        self.collection = db['influencers']

    def insert(self, model: InfluencerModel) -> bool:
        if self.exists(model.name, model.platform):
            return False
            
        self.collection.insert_one({
            'account_id': model.account_id,
            'name': model.name,
            'description': model.description,
            'source': model.source.value,
            'platform': model.platform.value,
            'attention': model.attention.value,
        })
        return True

    def exists(self, name: str, platform: SocialMedia) -> bool:
        query = {
            "name": name,
            "platform": platform.value
        }
        return self.collection.count_documents(query, limit=1) > 0

    def get_by_source(self, source: NewsSource) -> list:
        return list(self.collection.find({"source": source.value}))

    def get_by_platform(self, platform: SocialMedia) -> list:
        return list(self.collection.find({"platform": platform.value}))

    def set_account_id(self, name: str, platform: SocialMedia, account_id: str):
        """El id numérico de la cuenta en su red, que sale al seguirla. El usuario se puede cambiar;
        el id no."""
        self.collection.update_one(
            {"name": name, "platform": platform.value},
            {"$set": {"account_id": account_id}}
        )
