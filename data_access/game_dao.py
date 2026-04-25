from typing import List
from models.videogame import GameChannel
from config.database import db

class GameDAO:
    def __init__(self):
        self.collection = db['games']

    def create_game(self, game: GameChannel) -> bool:
        self.collection.insert_one(game.to_dict())
        return True

    def get_game_by_name(self, game_name: str) -> GameChannel | None:
        result = self.collection.find_one({"game_name": game_name})
        return GameChannel.from_dict(result) if result else None

    def get_game_by_message_id(self, message_id: int) -> GameChannel | None:
        result = self.collection.find_one({"message_id": message_id})
        return GameChannel.from_dict(result) if result else None

    def get_all_games(self) -> List[GameChannel]:
        cursor = self.collection.find()
        return [GameChannel.from_dict(result) for result in cursor]

    def game_exists(self, game_name: str) -> bool:
        return self.collection.count_documents({"game_name": game_name}, limit=1) > 0