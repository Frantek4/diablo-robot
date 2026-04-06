from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Fixture:
    home_team: str
    away_team: str
    match_date: datetime
    competition: str
    venue: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: str = "scheduled"
    id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "home_team": self.home_team,
            "away_team": self.away_team,
            "match_date": self.match_date.isoformat(),
            "competition": self.competition,
            "venue": self.venue,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "status": self.status
        }

    @classmethod
    def from_dict(cls, data: dict, doc_id: str = None):
        return cls(
            home_team=data["home_team"],
            away_team=data["away_team"],
            match_date=datetime.fromisoformat(data["match_date"]),
            competition=data["competition"],
            venue=data.get("venue"),
            home_score=data.get("home_score"),
            away_score=data.get("away_score"),
            status=data.get("status", "scheduled"),
            id=doc_id
        )