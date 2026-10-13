import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from config.database import db


class SocialStateDAO:
    """El freno de un scaneo de redes (Instagram, X) vive en Mongo, no en memoria.

    Ninguna de las dos plataformas avisa antes de marcar la cuenta: cuando lo dicen, ya pasó. La
    única verdad que tenemos es lo que hicimos nosotros, así que la llevamos nosotros — y tiene que
    sobrevivir a un reinicio, porque un bot que se reinicia y vuelve a leer como si nada es
    exactamente la forma de perder la cuenta. Una colección por plataforma: el freno de una no
    tiene por qué frenar a la otra.
    """

    def __init__(self, collection: str):
        self.collection = db[collection]

    def get(self) -> dict:
        return self.collection.find_one({"_id": "state"}) or {}

    def save(self, **fields):
        self.collection.update_one({"_id": "state"}, {"$set": fields}, upsert=True)

    def block(self, reason: str, when: datetime, kind: str = "account"):
        """Se frena hasta que un humano diga que revisó. `kind` dice qué hay que revisar:
        "session" (sesión vencida: hay que rehacerla), "account" (checkpoint, bloqueo), "outdated"
        (la plataforma cambió y hay que tocar código) o "manual"."""
        self.save(blocked=True, blocked_reason=reason, blocked_at=when, blocked_kind=kind)
        self.log_event("blocked", reason, when)

    def unblock(self, when: datetime):
        self.save(blocked=False, blocked_reason=None, blocked_at=None, blocked_kind=None,
                  backoff_step=0, last_failure=None, next_run_at=when)
        self.log_event("unblocked", "reanudado a mano", when)

    def stale_session(self, session_file: str) -> bool:
        """¿El freno fue por sesión vencida y la sesión en disco sigue siendo la misma de entonces?

        Reanudar así es mandarle a la plataforma otro pedido con las cookies que ya rechazó, que es
        de lo más marcable que hay. Si el archivo se rehízo después del freno, se puede seguir.
        """
        state = self.get()
        if state.get("blocked_kind") != "session":
            return False
        blocked_at = state.get("blocked_at")
        if not os.path.exists(session_file) or not isinstance(blocked_at, datetime):
            return True
        if blocked_at.tzinfo is None:
            blocked_at = blocked_at.replace(tzinfo=timezone.utc)
        return os.path.getmtime(session_file) <= blocked_at.timestamp()

    def log_event(self, kind: str, reason: Optional[str], when: datetime):
        """Historial, para poder mirar después si esto viene pasando seguido o fue una vez."""
        self.collection.insert_one({"kind": kind, "reason": reason, "timestamp": when})

    def recent_events(self, days: int = 30, limit: int = 5) -> list:
        cutoff = datetime.now().astimezone() - timedelta(days=days)
        return list(self.collection.find({"kind": {"$ne": None}, "timestamp": {"$gte": cutoff}})
                    .sort("timestamp", -1).limit(limit))
