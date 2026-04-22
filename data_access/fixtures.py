from datetime import datetime
from typing import List, Optional
from bson.objectid import ObjectId
from config.settings import settings
from models.fixture import Fixture
from config.database import db

class FixtureDAO:
    def __init__(self):
        self.collection = db['fixtures']

    def insert(self, fixture: Fixture) -> str:
        result = self.collection.insert_one(fixture.to_dict())
        return str(result.inserted_id)

    def get_next_match(self) -> Optional[Fixture]:
        now = datetime.now(settings.TIMEZONE).isoformat()
        
        result = self.collection.find(
            {
                "status": "scheduled",
                "match_date": {"$gt": now}
            }
        ).sort("match_date", 1).limit(1)
        
        next_match_data = next(result, None)
        
        if not next_match_data:
            return None
            
        return Fixture.from_dict(next_match_data, doc_id=str(next_match_data['_id']))

    def update_score(self, fixture_id: str, home_score: int, away_score: int, status: str = "finished"):
        self.collection.update_one(
            {"_id": ObjectId(fixture_id)},
            {"$set": {
                'home_score': home_score,
                'away_score': away_score,
                'status': status
            }}
        )

    def get_fixture_by_id(self, fixture_id: str) -> Optional[Fixture]:
        result = self.collection.find_one({"_id": ObjectId(fixture_id)})
        if result:
            return Fixture.from_dict(result, doc_id=str(result['_id']))
        return None

    def get_fixtures_by_competition(self, competition: str) -> List[Fixture]:
        cursor = self.collection.find({"competition": competition}).sort("match_date", 1)
        return [Fixture.from_dict(item, doc_id=str(item['_id'])) for item in cursor]
    
    def upsert(self, fixture: Fixture) -> str:
        fixture_dict = fixture.to_dict()
        
        if 'id' in fixture_dict:
            del fixture_dict['id']
            
        result = self.collection.update_one(
            {"match_id": fixture.match_id},
            {"$set": fixture_dict},
            upsert=True
        )
        
        if result.upserted_id:
            return str(result.upserted_id)
            
        existing = self.collection.find_one({"match_id": fixture.match_id})
        return str(existing['_id'])