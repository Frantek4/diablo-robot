from datetime import datetime
from typing import Optional

from config.database import db
from models.chess_tournament import ChessTournament


class ChessTournamentDAO:
    """Qué torneo de Lichess corresponde a qué evento de Discord. Los torneos semanales repiten
    nombre, así que el evento no se puede encontrar por nombre como con los partidos."""

    def __init__(self):
        self.collection = db['chess_tournaments']

    def get(self, lichess_id: str) -> Optional[dict]:
        return self.collection.find_one({"_id": lichess_id})

    def get_upcoming(self, now: datetime) -> list[dict]:
        return list(self.collection.find({"starts_at": {"$gt": now}}))

    def upsert(self, tournament: ChessTournament, discord_event_id: int):
        self.collection.update_one(
            {"_id": tournament.lichess_id},
            {"$set": {
                "system": tournament.system,
                "name": tournament.name,
                "starts_at": tournament.starts_at,
                "ends_at": tournament.ends_at,
                "description": tournament.to_description(),
                "discord_event_id": discord_event_id,
            }},
            upsert=True,
        )

    def delete(self, lichess_id: str):
        self.collection.delete_one({"_id": lichess_id})
