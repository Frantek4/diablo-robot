from dataclasses import dataclass
from datetime import datetime


@dataclass
class SelfDestructMessage:
    user_id: int
    message_id: int
    delete_at: datetime

    @classmethod
    def from_dict(cls, data: dict) -> 'SelfDestructMessage':
        return cls(
            user_id=data['user_id'],
            message_id=data['message_id'],
            delete_at=data['delete_at'],
        )

    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'message_id': self.message_id,
            'delete_at': self.delete_at,
        }
