import random
from typing import Tuple, Optional


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    cells = ["diamond"] * 7 + ["bomb"] * 2
    random.shuffle(cells)
    return {
        "cells": cells,
        "revealed": ["hidden"] * 9,
        "diamonds_found": {str(player1_id): 0, str(player2_id): 0},
    }


def render_board(match: dict, show_labels: bool = True) -> str:
    state = match["game_state"]
    revealed = state["revealed"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    current_turn = match["current_turn"]
    p1_id = match["player1_id"]

    current_name = p1_name if current_turn == p1_id else p2_name

    p1_diamonds = state["diamonds_found"].get(str(match["player1_id"]), 0)
    p2_diamonds = state["diamonds_found"].get(str(match["player2_id"]), 0)

    lines = [
        "💎 Treasure Hunt",
        "",
        f"@{p1_name} 💎 x{p1_diamonds}",
        f"@{p2_name} 💎 x{p2_diamonds}",
        "",
    ]

    if show_labels:
        lines.append(f"🎯 Turn: @{current_name}")
        lines.append("Choose a cell to reveal!")

    return "\n".join(lines)


def apply_reveal(match: dict, user_id: int, cell_idx: int) -> Tuple[dict, str, bool]:
    state = match["game_state"]

    if state["revealed"][cell_idx] != "hidden":
        return match, "already_revealed", False

    actual = state["cells"][cell_idx]
    state["revealed"][cell_idx] = actual

    if actual == "bomb":
        return match, "bomb", True

    player_key = str(user_id)
    state["diamonds_found"][player_key] = state["diamonds_found"].get(player_key, 0) + 1

    next_turn = (
        match["player2_id"]
        if match["current_turn"] == match["player1_id"]
        else match["player1_id"]
    )
    match["current_turn"] = next_turn

    all_revealed = all(r != "hidden" for r in state["revealed"])
    if all_revealed:
        return match, "all_revealed", True

    return match, "diamond", False


def get_winner_by_bomb(match: dict, loser_id: int) -> tuple:
    if loser_id == match["player1_id"]:
        return match["player2_id"], match["player2_name"], False
    return match["player1_id"], match["player1_name"], False


def get_winner_by_diamonds(match: dict) -> tuple:
    state = match["game_state"]
    p1_d = state["diamonds_found"].get(str(match["player1_id"]), 0)
    p2_d = state["diamonds_found"].get(str(match["player2_id"]), 0)
    if p1_d > p2_d:
        return match["player1_id"], match["player1_name"], False
    elif p2_d > p1_d:
        return match["player2_id"], match["player2_name"], False
    else:
        return None, None, True


def render_result(match: dict, reason: str = "") -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    p1_d = state["diamonds_found"].get(str(match["player1_id"]), 0)
    p2_d = state["diamonds_found"].get(str(match["player2_id"]), 0)
    winner_id = match.get("winner_id")
    winner_name = p1_name if winner_id == match["player1_id"] else p2_name

    lines = [
        "💎 Treasure Hunt — Result",
        "",
        f"@{p1_name}: 💎 x{p1_d}",
        f"@{p2_name}: 💎 x{p2_d}",
        "",
    ]
    if reason == "bomb":
        lines.append("💣 BOOM! A bomb was found!")
        lines.append("")
    if match.get("is_draw"):
        lines.append("🤝 It's a Draw!")
    else:
        lines.append(f"🏆 Winner: @{winner_name}")

    return "\n".join(lines)
