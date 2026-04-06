from tinydb import TinyDB, Query
from datetime import datetime
from typing import List, Optional
from models.fixture import Fixture

class FixtureDAO:
    def __init__(self):
        self.db = TinyDB('database.json')
        self.table = self.db.table('fixtures')
        self.query = Query()

    def insert(self, fixture: Fixture) -> int:
        return self.table.insert(fixture.to_dict())

    def get_next_match(self) -> Optional[Fixture]:
        now = datetime.now().isoformat()
        
        results = self.table.search(
            (self.query.status == 'scheduled') & 
            (self.query.match_date > now)
        )
        
        if not results:
            return None
            
        results.sort(key=lambda x: x['match_date'])
        next_match_data = results[0]
        
        return Fixture.from_dict(next_match_data, doc_id=next_match_data.doc_id)

    def update_score(self, fixture_id: int, home_score: int, away_score: int, status: str = "finished"):
        self.table.update({
            'home_score': home_score,
            'away_score': away_score,
            'status': status
        }, doc_ids=[fixture_id])

    def get_fixture_by_id(self, fixture_id: int) -> Optional[Fixture]:
        result = self.table.get(doc_id=fixture_id)
        if result:
            return Fixture.from_dict(result, doc_id=result.doc_id)
        return None

    def get_fixtures_by_competition(self, competition: str) -> List[Fixture]:
        results = self.table.search(self.query.competition == competition)
        results.sort(key=lambda x: x['match_date'])
        
        return [Fixture.from_dict(item, doc_id=item.doc_id) for item in results]
