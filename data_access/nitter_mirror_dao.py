from datetime import datetime, timezone
from typing import List, Optional

from config.database import db
from config.settings import settings
from models.nitter_mirror import NitterMirror, SOURCE_WIKI


def _to_local(value) -> Optional[datetime]:
    """Mongo devuelve los datetime en UTC y sin tzinfo: los vuelvo a poner en hora nuestra."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TIMEZONE)


class NitterMirrorDAO:
    def __init__(self):
        self.collection = db['nitter_mirrors']

    def upsert_candidate(self, url: str, source: str = SOURCE_WIKI) -> bool:
        """Suma el mirror al repositorio si no lo tenía. Devuelve True si es nuevo."""
        result = self.collection.update_one(
            {"_id": url},
            {
                "$set": {"kind": "mirror", "source": source},
                "$setOnInsert": {
                    "is_online": None,
                    "last_check": None,
                    "last_ok": None,
                    "last_reason": None,
                    "consecutive_failures": 0,
                    "latency_ms": None,
                    "discovered_at": datetime.now(settings.TIMEZONE),
                },
            },
            upsert=True,
        )
        return result.upserted_id is not None

    def save_result(self, url: str, is_online: bool, reason: str = None, latency_ms: float = None):
        """Guarda cómo le fue al mirror en el último intento, venga del chequeo o de un scaneo real."""
        now = datetime.now(settings.TIMEZONE)
        update = {
            "$set": {
                "kind": "mirror",
                "is_online": is_online,
                "last_check": now,
                "last_reason": reason,
                "latency_ms": latency_ms,
            },
        }
        if is_online:
            update["$set"]["last_ok"] = now
            update["$set"]["consecutive_failures"] = 0
        else:
            update["$inc"] = {"consecutive_failures": 1}

        self.collection.update_one({"_id": url}, update, upsert=True)

    def get_all(self) -> List[NitterMirror]:
        return [self._build(doc) for doc in self.collection.find({"kind": "mirror"})]

    def get_ranked(self) -> List[NitterMirror]:
        """Los que sé que andan primero, después los que nunca probé, y al final los caídos por menos fallas."""
        def rank(mirror: NitterMirror):
            if mirror.is_online:
                return (0, mirror.latency_ms if mirror.latency_ms is not None else 9999)
            if mirror.is_online is None:
                return (1, 0)
            return (2, mirror.consecutive_failures)

        return sorted(self.get_all(), key=rank)

    def count_online(self) -> int:
        return self.collection.count_documents({"kind": "mirror", "is_online": True})

    def get_state(self) -> dict:
        return self.collection.find_one({"_id": "state"}) or {}

    def save_state(self, **fields):
        """Estado del repositorio: si ya avisé que no hay mirrors, cuándo actualicé el catálogo, etc."""
        self.collection.update_one(
            {"_id": "state"},
            {"$set": {"kind": "state", **fields}},
            upsert=True,
        )

    @staticmethod
    def _build(doc: dict) -> NitterMirror:
        mirror = NitterMirror.from_doc(doc)
        mirror.last_check = _to_local(mirror.last_check)
        mirror.last_ok = _to_local(mirror.last_ok)
        return mirror
