from datetime import datetime, timedelta
from typing import Optional

from config.database import db


class InstagramStateDAO:
    """El freno de Instagram vive en Mongo, no en memoria.

    Con Nitter el estado podía ser volátil porque el contador autoritativo lo llevaba él
    (`/.sessions`) contra la fuente real, y guardar una copia habría sido tener dos verdades. Acá
    no hay contador: Instagram no dice nunca cuánto margen queda, sólo avisa cuando ya marcó la
    cuenta. La única verdad que tenemos es lo que hicimos nosotros, así que la llevamos nosotros —
    y tiene que sobrevivir a un reinicio, porque un bot que se reinicia y vuelve a leer como si
    nada es exactamente la forma de perder la cuenta.
    """

    def __init__(self):
        self.collection = db['instagram_state']

    def get(self) -> dict:
        return self.collection.find_one({"_id": "state"}) or {}

    def save(self, **fields):
        self.collection.update_one({"_id": "state"}, {"$set": fields}, upsert=True)

    def block(self, reason: str, when: datetime):
        """Instagram acusó a la cuenta. Se frena hasta que un humano diga que revisó."""
        self.save(blocked=True, blocked_reason=reason, blocked_at=when)
        self.log_event("blocked", reason, when)

    def unblock(self, when: datetime):
        self.save(blocked=False, blocked_reason=None, blocked_at=None,
                  backoff_step=0, last_failure=None, next_run_at=when)
        self.log_event("unblocked", "reanudado a mano", when)

    def log_event(self, kind: str, reason: Optional[str], when: datetime):
        """Historial, para poder mirar después si esto viene pasando seguido o fue una vez."""
        self.collection.insert_one({"kind": kind, "reason": reason, "timestamp": when})

    def recent_events(self, days: int = 30, limit: int = 5) -> list:
        cutoff = datetime.now().astimezone() - timedelta(days=days)
        return list(self.collection.find({"kind": {"$ne": None}, "timestamp": {"$gte": cutoff}})
                    .sort("timestamp", -1).limit(limit))
