from datetime import datetime
from typing import List

from config.database import db
from models.self_destruct_message import SelfDestructMessage


class SelfDestructMessageDAO:
    def __init__(self):
        self.collection = db['self_destruct_messages']

    def insert(self, message: SelfDestructMessage) -> bool:
        self.collection.insert_one(message.to_dict())
        return True

    def get_due(self, now: datetime) -> List[SelfDestructMessage]:
        cursor = self.collection.find({"delete_at": {"$lte": now}})
        return [SelfDestructMessage.from_dict(result) for result in cursor]

    def delete_by_message_id(self, message_id: int) -> None:
        self.collection.delete_one({"message_id": message_id})
