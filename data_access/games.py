from tinydb import TinyDB, Query
from typing import List

from models.videogame import GameChannel

class GameDAO:
    def __init__(self):
        self.db = TinyDB('database.json')
        self.games_table = self.db.table('games')
        self.GameQuery = Query()
    


    def create_game(self, game: GameChannel) -> bool:
        self.games_table.insert(game.to_dict())
        return True
    


    def get_game_by_name(self, game_name: str) -> GameChannel | None:
        result = self.games_table.get(self.GameQuery.game_name == game_name)
        return GameChannel.from_dict(result) if result else None
    


    def get_game_by_message_id(self, message_id: int) -> GameChannel | None:
        result = self.games_table.get(self.GameQuery.message_id == message_id)
        return GameChannel.from_dict(result) if result else None
    


    def get_all_games(self) -> List[GameChannel]:
        results = self.games_table.all()
        return [GameChannel.from_dict(result) for result in results]
    


    def game_exists(self, game_name: str) -> bool:

        return self.get_game_by_name(game_name) is not None
    