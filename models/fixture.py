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

    def to_description(self) -> str:
        """Genera una descripción legible para el evento de Discord"""
        return (f"🏆 {self.competition}\n"
                f"🤝 {self.home_team} vs {self.away_team}\n"
                f"🏟️ {self.venue or 'A confirmar'}\n"
                f"⏰ {self.match_date.isoformat()}")

    @classmethod
    def from_description(cls, description: str) -> Optional['Fixture']:
        """Reconstruye un objeto Fixture desde la descripción del evento"""
        if not description:
            return None
        try:
            lines = description.split('\n')
            comp = lines[0].replace("🏆 ", "")
            teams = lines[1].replace("🤝 ", "").split(" vs ")
            venue = lines[2].replace("🏟️ ", "")
            if venue == "A confirmar": venue = None
            date_iso = lines[3].replace("⏰ ", "")
            return cls(
                home_team=teams[0],
                away_team=teams[1],
                match_date=datetime.fromisoformat(date_iso),
                competition=comp,
                venue=venue
            )
        except Exception:
            return None

    def get_changes(self, other: 'Fixture') -> str:
        """Compara dos fixtures y devuelve un texto con las diferencias"""
        changes = []
        if self.match_date != other.match_date:
            changes.append(f"- El horario cambió de {self.match_date.strftime('%H:%M')} a {other.match_date.strftime('%H:%M')}")
        if self.venue != other.venue:
            changes.append(f"- El estadio cambió de {self.venue or 'A confirmar'} a {other.venue or 'A confirmar'}")
        if not changes:
            return "Actualización de información del partido."
        return "\n".join(changes)