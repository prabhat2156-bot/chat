import uuid
from datetime import datetime, timezone
from typing import Optional, List


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
            "battle_wins": 0,
            "battle_losses": 0,
            "battle_draws": 0,
            "total_battles": 0,
            "game_stats": {},
            "joined_at": now_utc(),
            "updated_at": now_utc(),
        }


class ChallengeModel:
    @staticmethod
    def new(
        challenger_id: int, challenger_name: str,
        opponent_id: int, opponent_name: str,
        game: str, group_id: int, message_id: int,
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
        player1_id: int, player1_name: str,
        player2_id: int, player2_name: str,
        game: str, group_id: int, message_id: int,
        tournament_id: Optional[str] = None,
        tournament_match_id: Optional[str] = None,
        battle_id: Optional[str] = None,
        battle_round: Optional[int] = None,
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
            "battle_id": battle_id,
            "battle_round": battle_round,
            "created_at": now_utc(),
            "finished_at": None,
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }


class BattlePaidModel:
    @staticmethod
    def new(
        group_id: int,
        challenger_id: int, challenger_name: str,
        opponent_id: Optional[int], opponent_username: str,
        form_message_id: int,
        fee_percent: float,
    ) -> dict:
        battle_id = new_id()
        return {
            "battle_id": battle_id,
            "group_id": group_id,
            # Players
            "challenger_id": challenger_id,
            "challenger_name": challenger_name,
            "opponent_id": opponent_id,
            "opponent_username": opponent_username,
            "opponent_name": opponent_username,
            # Form fields
            "game": None,
            "total_rounds": None,
            "amount": None,
            # Fee
            "fee_percent": fee_percent,
            "fee_per_player": 0,
            "total_per_player": 0,
            "prize_pool": 0,
            # Confirmation
            "challenger_confirmed": False,
            "opponent_confirmed": False,
            # Payment & Admin
            "admin_approved": False,
            "approving_admin_id": None,
            "approving_admin_name": None,
            # Ready
            "challenger_ready": False,
            "opponent_ready": False,
            # Rounds
            "current_round": 0,
            "current_round_game": None,
            "current_match_id": None,
            "p1_wins": 0,
            "p2_wins": 0,
            "round_draws": 0,
            "round_results": [],
            "next_game_proposed": None,
            "next_game_proposer_id": None,
            # Final
            "winner_id": None,
            "winner_name": None,
            "winner_upi": None,
            # Messages
            "form_message_id": form_message_id,
            "confirm_message_id": None,
            "payment_message_id": None,
            "ready_message_id": None,
            # Status
            "status": "form_filling",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }


class TournamentModel:
    @staticmethod
    def new(
        group_id: int, admin_id: int, admin_name: str,
        games: List[str], size: int, final_format: str, message_id: int,
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
