from datetime import datetime
from typing import List, Optional

from config.database import db
from models.hardware_snapshot import HardwareSnapshot


class HardwareMonitorDAO:
    def __init__(self):
        self.collection = db['hardware_monitor']

    def save_latest(self, snapshot: Optional[HardwareSnapshot], is_online: bool, internet_online: bool = True):
        self.collection.update_one(
            {"_id": "latest"},
            {"$set": {
                "kind": "latest",
                "is_online": is_online,
                "internet_online": internet_online,
                "snapshot": snapshot.to_dict() if snapshot else None,
            }},
            upsert=True
        )

    def get_latest(self) -> Optional[dict]:
        return self.collection.find_one({"_id": "latest"})

    def log_transition(self, is_online: bool, snapshot: Optional[HardwareSnapshot], timestamp: datetime,
                       subject: str = "pc"):
        """subject 'pc' = se cayó/volvió la máquina; 'internet' = la máquina anda pero se cayó/volvió la línea."""
        self.collection.insert_one({
            "kind": "event",
            "subject": subject,
            "is_online": is_online,
            "snapshot": snapshot.to_dict() if snapshot else None,
            "timestamp": timestamp,
        })

    def log_degradation(self, snapshot: Optional[HardwareSnapshot], timestamp: datetime):
        """Registra un microcorte o lentitud de red sin generar aviso, para poder mirar el historial después."""
        self.collection.insert_one({
            "kind": "network_degradation",
            "snapshot": snapshot.to_dict() if snapshot else None,
            "timestamp": timestamp,
        })

    def get_recent_events(self, limit: int = 20) -> List[dict]:
        cursor = self.collection.find({"kind": "event"}).sort("timestamp", -1).limit(limit)
        return list(cursor)

    def get_recent_degradations(self, since: datetime) -> List[dict]:
        cursor = self.collection.find({"kind": "network_degradation", "timestamp": {"$gte": since}}).sort("timestamp", -1)
        return list(cursor)
