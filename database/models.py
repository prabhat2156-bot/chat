import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


def now_utc():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid.uuid4())


class UserModel:
    @staticmethod
    def new(user_id: int, username: str, first_name: str) -> dict:
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "total_matches": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "game_stats": {},
            "joined_at": now_utc(),
            "updated_at": now_utc(),
        }

    @staticmethod
    def game_stat_key(game: str) -> dict:
        return {"matches": 0, "wins": 0, "losses": 0, "draws": 0}


class ChallengeModel:
    @staticmethod
    def new(
        challenger_id: int,
        challenger_name: str,
        opponent_id: int,
        opponent_name: str,
        game: str,
        group_id: int,
        message_id: int,
    ) -> dict:
        return {
            "challenge_id": new_id(),
            "challenger_id": challenger_id,
            "challenger_name": challenger_name,
            "opponent_id": opponent_id,
            "opponent_name": opponent_name,
            "game": game,
            "group_id": group_id,
            "message_id": message_id,
            "status": "pending",
            "created_at": now_utc(),
            "expires_at": None,
        }


class MatchModel:
    @staticmethod
    def new(
        player1_id: int,
        player1_name: str,
        player2_id: int,
        player2_name: str,
        game: str,
        group_id: int,
        message_id: int,
        tournament_id: Optional[str] = None,
        tournament_match_id: Optional[str] = None,
    ) -> dict:
        return {
            "match_id": new_id(),
            "player1_id": player1_id,
            "player1_name": player1_name,
            "player2_id": player2_id,
            "player2_name": player2_name,
            "game": game,
            "group_id": group_id,
            "message_id": message_id,
            "status": "active",
            "current_turn": player1_id,
            "game_state": {},
            "winner_id": None,
            "loser_id": None,
            "is_draw": False,
            "forfeit": False,
            "turn_count": 0,
            "tournament_id": tournament_id,
            "tournament_match_id": tournament_match_id,
            "created_at": now_utc(),
            "finished_at": None,
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }


class TournamentModel:
    @staticmethod
    def new(
        group_id: int,
        admin_id: int,
        admin_name: str,
        games: List[str],
        size: int,
        final_format: str,
        message_id: int,
    ) -> dict:
        return {
            "tournament_id": new_id(),
            "group_id": group_id,
            "admin_id": admin_id,
            "admin_name": admin_name,
            "games": games,
            "size": size,
            "final_format": final_format,
            "players": [],
            "brackets": [],
            "current_round": 0,
            "status": "joining",
            "message_id": message_id,
            "winner_id": None,
            "winner_name": None,
            "game_usage": {},
            "created_at": now_utc(),
            "finished_at": None,
        }
