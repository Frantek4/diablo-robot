from datetime import datetime
from typing import List, Optional
from bson.objectid import ObjectId
from config.settings import settings
from models.fixture import Fixture
from models.fixture_status import FixtureStatus
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
            {"$or": [
                {"status": FixtureStatus.LIVE},
                {"status": FixtureStatus.SCHEDULED, "match_date": {"$gt": now}}
            ]}
        ).sort("match_date", 1).limit(1)
        doc = next(result, None)
        return Fixture.from_dict(doc, doc_id=str(doc['_id'])) if doc else None

    def update_status(self, fixture_id: str, status: FixtureStatus):
        self.collection.update_one(
            {"_id": ObjectId(fixture_id)},
            {"$set": {"status": status}}
        )

    def update_score(self, fixture_id: str, home_score: int, away_score: int, status: FixtureStatus = FixtureStatus.FINISHED):
        self.collection.update_one(
            {"_id": ObjectId(fixture_id)},
            {"$set": {
                'home_score': home_score,
                'away_score': away_score,
                'status': status
            }}
        )

    def get_by_match_id(self, match_id: str) -> Optional[Fixture]:
        result = self.collection.find_one({"match_id": match_id})
        if result:
            return Fixture.from_dict(result, doc_id=str(result['_id']))
        return None

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