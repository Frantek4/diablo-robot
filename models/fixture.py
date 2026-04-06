from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import re
from config.settings import settings

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
            "tv_channels": self.tv_channels
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
            referee=data.get("referee"),
            tv_channels=data.get("tv_channels"),
            id=doc_id
        )

    def to_description(self) -> str:
        """Genera una descripción legible para el evento de Discord"""
        date_str = self.match_date.strftime("%d/%m/%Y %H:%M")
        return (f"      ⚽    {self.home_team} vs {self.away_team}\n"
                f"      🏆    {self.competition}\n"
                f"      🏟️    {self.venue or 'No anunciado'}\n"
                f"      📅    {date_str}\n"
                f"      ⚖️    {self.referee or 'No anunciado'}\n"
                f"      📺    {self.tv_channels or 'No anunciado'}")

    @classmethod
    def from_description(cls, description: str) -> Optional['Fixture']:
        """Reconstruye un objeto Fixture desde la descripción del evento"""
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
            match_date = settings.TIMEZONE.localize(match_dt)

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
        """Compara dos fixtures y devuelve un texto con las diferencias"""
        changes = []
        if self.match_date != other.match_date:
            changes.append(f"- El horario cambió de {self.match_date.strftime('%H:%M')} a {other.match_date.strftime('%H:%M')}")
        if self.venue != other.venue:
            changes.append(f"- El estadio cambió de {self.venue or 'No anunciado'} a {other.venue or 'No anunciado'}")
        if self.referee != other.referee:
            changes.append(f"- El árbitro cambió de {self.referee or 'No anunciado'} a {other.referee or 'No anunciado'}")
        if self.tv_channels != other.tv_channels:
            changes.append(f"- La transmisión cambió de {self.tv_channels or 'No anunciado'} a {other.tv_channels or 'No anunciado'}")
        if not changes:
            return "Actualización de información del partido."
        return "\n".join(changes)