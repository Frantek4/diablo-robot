from models.influencer import AttentionLevel, InfluencerModel
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

    def get_by_platform_and_attention(self, platform: SocialMedia, attention: AttentionLevel) -> list:
        return list(self.collection.find({"platform": platform.value, "attention": attention.value}))

    def set_account_id(self, name: str, platform: SocialMedia, account_id: str):
        """El id numérico se resuelve una sola vez en la vida: guardarlo evita volver a pasar por
        el buscador de Instagram cada vez que el bot arranca."""
        self.collection.update_one(
            {"name": name, "platform": platform.value},
            {"$set": {"account_id": account_id}}
        )
