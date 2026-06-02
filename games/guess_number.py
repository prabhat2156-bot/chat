import random
from typing import Optional, Tuple


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    secret = random.randint(1, 100)
    return {
        "secret": secret,
        "guesses": [],
        "last_hint": None,
    }


def render_board(match: dict) -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    current_turn = match["current_turn"]
    p1_id = match["player1_id"]

    current_name = p1_name if current_turn == p1_id else p2_name

    lines = [
        "🔢 Guess Number",
        "",
        "I'm thinking of a number between 1 and 100.",
        "Take turns guessing!",
        "",
    ]

    if state["guesses"]:
        lines.append("📋 Guesses:")
        for g in state["guesses"][-6:]:
            lines.append(f"  @{g['player']} → {g['guess']} {g['hint']}")
        lines.append("")

    lines.append(f"🎯 Turn: @{current_name}")
    lines.append("Reply with a number (1-100):")

    return "\n".join(lines)


def apply_guess(match: dict, user_id: int, guess: int) -> Tuple[dict, str, bool]:
    state = match["game_state"]
    secret = state["secret"]
    player_name = (
        match["player1_name"]
        if user_id == match["player1_id"]
        else match["player2_name"]
    )

    if guess < secret:
        hint = "📈 Higher"
        found = False
    elif guess > secret:
        hint = "📉 Lower"
        found = False
    else:
        hint = "✅ Correct!"
        found = True

    state["guesses"].append({"player": player_name, "guess": guess, "hint": hint})
    state["last_hint"] = hint

    if not found:
        next_turn = (
            match["player2_id"]
            if match["current_turn"] == match["player1_id"]
            else match["player1_id"]
        )
        match["current_turn"] = next_turn

    return match, hint, found


def get_winner_by_user(match: dict, user_id: int) -> tuple:
    if user_id == match["player1_id"]:
        return match["player1_id"], match["player1_name"], False
    return match["player2_id"], match["player2_name"], False


def render_result(match: dict) -> str:
    state = match["game_state"]
    secret = state["secret"]
    winner_id = match.get("winner_id")
    winner_name = match.get("player1_name") if winner_id == match["player1_id"] else match.get("player2_name")

    lines = [
        "🔢 Guess Number — Result",
        "",
        f"🔑 Secret Number: {secret}",
        "",
        f"🏆 Winner: @{winner_name}",
    ]
    return "\n".join(lines)
