from database.mongodb import get_db
from database.models import UserModel, now_utc
from typing import Optional


async def get_or_create_user(user_id: int, username: str, first_name: str) -> dict:
    db = get_db()
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        user = UserModel.new(user_id, username or str(user_id), first_name or "Unknown")
        await db.users.insert_one(user)
    else:
        update = {}
        if username and user.get("username") != username:
            update["username"] = username
        if first_name and user.get("first_name") != first_name:
            update["first_name"] = first_name
        if update:
            update["updated_at"] = now_utc()
            await db.users.update_one({"user_id": user_id}, {"$set": update})
            user.update(update)
    return user


async def record_match_result(
    player1_id: int,
    player1_name: str,
    player2_id: int,
    player2_name: str,
    game: str,
    winner_id: Optional[int],
    is_draw: bool = False,
):
    db = get_db()
    await get_or_create_user(player1_id, player1_name, player1_name)
    await get_or_create_user(player2_id, player2_name, player2_name)

    game_key = f"game_stats.{game}"

    p1_win = winner_id == player1_id
    p2_win = winner_id == player2_id

    p1_update = {
        "$inc": {
            "total_matches": 1,
            "wins": 1 if p1_win else 0,
            "losses": 1 if p2_win and not is_draw else 0,
            "draws": 1 if is_draw else 0,
            f"{game_key}.matches": 1,
            f"{game_key}.wins": 1 if p1_win else 0,
            f"{game_key}.losses": 1 if p2_win and not is_draw else 0,
            f"{game_key}.draws": 1 if is_draw else 0,
        },
        "$set": {"updated_at": now_utc()},
    }
    p2_update = {
        "$inc": {
            "total_matches": 1,
            "wins": 1 if p2_win else 0,
            "losses": 1 if p1_win and not is_draw else 0,
            "draws": 1 if is_draw else 0,
            f"{game_key}.matches": 1,
            f"{game_key}.wins": 1 if p2_win else 0,
            f"{game_key}.losses": 1 if p1_win and not is_draw else 0,
            f"{game_key}.draws": 1 if is_draw else 0,
        },
        "$set": {"updated_at": now_utc()},
    }

    await db.users.update_one({"user_id": player1_id}, p1_update)
    await db.users.update_one({"user_id": player2_id}, p2_update)


async def get_active_match_for_user(user_id: int) -> Optional[dict]:
    db = get_db()
    return await db.matches.find_one(
        {
            "$or": [{"player1_id": user_id}, {"player2_id": user_id}],
            "status": "active",
        }
    )


async def get_active_challenge_for_user(user_id: int) -> Optional[dict]:
    db = get_db()
    return await db.challenges.find_one(
        {
            "$or": [{"challenger_id": user_id}, {"opponent_id": user_id}],
            "status": "pending",
        }
    )


async def get_match_by_id(match_id: str) -> Optional[dict]:
    db = get_db()
    return await db.matches.find_one({"match_id": match_id})


async def get_challenge_by_id(challenge_id: str) -> Optional[dict]:
    db = get_db()
    return await db.challenges.find_one({"challenge_id": challenge_id})
