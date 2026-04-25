from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import re
from config.settings import settings

@dataclass
class Fixture:
    match_id: str
    home_team: str
    away_team: str
    match_date: datetime
    competition: str
    venue: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: str = "scheduled"
    referee: Optional[str] = None
    tv_channels: Optional[str] = None
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
            "status": self.status,
            "referee": self.referee,
            "tv_channels": self.tv_channels,
            "match_id": self.match_id
        }

    @classmethod
    def from_dict(cls, data: dict, doc_id: str = None):
        return cls(
            match_id=data["match_id"],
            home_team=data["home_team"],
            away_team=data["away_team"],
            match_date=datetime.fromisoformat(data["match_date"]),
            competition=data["competition"],
            venue=data.get("venue"),
            home_score=data.get("home_score"),
            away_score=data.get("away_score"),
            status=data.get("status", "scheduled"),
            referee=data.get("referee"),
            tv_channels=data.get("tv_channels"),
            id=doc_id
        )

    def to_description(self) -> str:
        date_str = self.match_date.strftime("%d/%m/%Y %H:%M")
        return (f"      ⚽    {self.home_team} vs {self.away_team}\n"
                f"      🏆    {self.competition}\n"
                f"      🏟️    {self.venue or 'No anunciado'}\n"
                f"      📅    {date_str}\n"
                f"      ⚖️    {self.referee or 'No anunciado'}\n"
                f"      📺    {self.tv_channels or 'No anunciado'}")

    @classmethod
    def from_description(cls, description: str) -> Optional['Fixture']:
        if not description:
            return None
        try:
            teams_match = re.search(r"⚽\s+(.*?)\s+vs\s+(.*)", description)
            comp_match = re.search(r"🏆\s+(.*)", description)
            venue_match = re.search(r"🏟️\s+(.*)", description)
            date_match = re.search(r"📅\s+(\d{2}/\d{2}/\d{4} \d{2}:\d{2})", description)
            ref_match = re.search(r"⚖️\s+(.*)", description)
            tv_match = re.search(r"📺\s+(.*)", description)

            if not (teams_match and comp_match and date_match):
                return None

            venue = venue_match.group(1).strip() if venue_match else None
            if venue == "No anunciado": venue = None
            
            ref = ref_match.group(1).strip() if ref_match else None
            if ref == "No anunciado": ref = None

            tv = tv_match.group(1).strip() if tv_match else None
            if tv == "No anunciado": tv = None

            match_dt = datetime.strptime(date_match.group(1), "%d/%m/%Y %H:%M")
            match_date = match_dt.replace(tzinfo=settings.TIMEZONE)

            return cls(
                home_team=teams_match.group(1).strip(),
                away_team=teams_match.group(2).strip(),
                match_date=match_date,
                competition=comp_match.group(1).strip(),
                venue=venue,
                referee=ref,
                tv_channels=tv
            )
        except Exception:
            return None

    def get_changes(self, other: 'Fixture') -> str:
        changes = []

        # Comparamos strings para ignorar diferencias de segundos y tzinfo
        self_date_str = self.match_date.strftime("%d/%m/%Y %H:%M")
        other_date_str = other.match_date.strftime("%d/%m/%Y %H:%M")

        if self_date_str != other_date_str:
            changes.append(f"📅: {self_date_str} -> {other_date_str}")
        if self.venue != other.venue:
            changes.append(f"🏟️: {self.venue or 'No anunciado'} -> {other.venue or 'No anunciado'}")
        if self.referee != other.referee:
            changes.append(f"⚖️: {self.referee or 'No anunciado'} -> {other.referee or 'No anunciado'}")
        if self.tv_channels != other.tv_channels:
            changes.append(f"📺: {self.tv_channels or 'No anunciado'} -> {other.tv_channels or 'No anunciado'}")

        if not changes:
            return None
        return "\n".join(changes)