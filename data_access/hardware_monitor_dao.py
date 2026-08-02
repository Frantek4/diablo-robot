from datetime import datetime
from typing import List, Optional

from config.database import db
from models.hardware_snapshot import HardwareSnapshot


class HardwareMonitorDAO:
    def __init__(self):
        self.collection = db['hardware_monitor']

    def save_latest(self, snapshot: Optional[HardwareSnapshot], is_online: bool):
        self.collection.update_one(
            {"_id": "latest"},
            {"$set": {
                "kind": "latest",
                "is_online": is_online,
                "snapshot": snapshot.to_dict() if snapshot else None,
            }},
            upsert=True
        )

    def get_latest(self) -> Optional[dict]:
        return self.collection.find_one({"_id": "latest"})

    def log_transition(self, is_online: bool, snapshot: Optional[HardwareSnapshot], timestamp: datetime):
        self.collection.insert_one({
            "kind": "event",
            "is_online": is_online,
            "snapshot": snapshot.to_dict() if snapshot else None,
            "timestamp": timestamp,
        })

    def get_recent_events(self, limit: int = 20) -> List[dict]:
        cursor = self.collection.find({"kind": "event"}).sort("timestamp", -1).limit(limit)
        return list(cursor)
