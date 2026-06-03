import random
from typing import Tuple


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    return {"secret": random.randint(1, 100), "guesses": [], "last_hint": None}


def render_board(match: dict) -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    current_turn = match["current_turn"]
    current_name = p1_name if current_turn == match["player1_id"] else p2_name

    lines = [
        "🔢 <b>Guess the Number</b>",
        "",
        "🎯 I'm thinking of a number between <b>1 and 100</b>.",
        "Take turns guessing — I'll give hints!",
        "",
    ]
    if state["guesses"]:
        lines.append("📋 <b>Recent Guesses:</b>")
        for g in state["guesses"][-6:]:
            lines.append(f"  • @{g['player']} guessed <b>{g['guess']}</b> → {g['hint']}")
        lines.append("")
    lines.append(f"🎯 <b>@{current_name}</b>, your turn! Type a number (1-100):")
    return "\n".join(lines)


def apply_guess(match: dict, user_id: int, guess: int) -> Tuple[dict, str, bool]:
    state = match["game_state"]
    secret = state["secret"]
    player_name = match["player1_name"] if user_id == match["player1_id"] else match["player2_name"]

    if guess < secret:
        hint = "📈 Higher!"
        found = False
    elif guess > secret:
        hint = "📉 Lower!"
        found = False
    else:
        hint = "✅ <b>Correct!</b>"
        found = True

    state["guesses"].append({"player": player_name, "guess": guess, "hint": hint})
    state["last_hint"] = hint

    if not found:
        match["current_turn"] = (
            match["player2_id"] if match["current_turn"] == match["player1_id"] else match["player1_id"]
        )
    return match, hint, found


def get_winner_by_user(match: dict, user_id: int) -> tuple:
    if user_id == match["player1_id"]:
        return match["player1_id"], match["player1_name"], False
    return match["player2_id"], match["player2_name"], False


def render_result(match: dict) -> str:
    state = match["game_state"]
    secret = state["secret"]
    winner_id = match.get("winner_id")
    winner_name = match["player1_name"] if winner_id == match["player1_id"] else match["player2_name"]
    lines = [
        "🔢 <b>Guess the Number — Result</b>",
        "",
        f"🔑 Secret Number: <b>{secret}</b>",
        "",
        f"🏆 <b>Winner: @{winner_name}</b> 🎉",
    ]
    return "\n".join(lines)
