from pymongo import MongoClient
from config.settings import settings

class MongoDB:
    _client = None

    @classmethod
    def get_database(cls):
        if cls._client is None:
            cls._client = MongoClient(
                settings.DATABASE_URL,
                username=settings.DATABASE_USERNAME,
                password=settings.DATABASE_PASSWORD,
                authSource="admin",
                tz_aware=True,
            )
        return cls._client.get_default_database(default='robot_devil')

db = MongoDB.get_database()