import random
from typing import Tuple


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    cells = ["diamond"] * 7 + ["bomb"] * 2
    random.shuffle(cells)
    return {
        "cells": cells,
        "revealed": ["hidden"] * 9,
        "diamonds_found": {str(player1_id): 0, str(player2_id): 0},
    }


def render_board(match: dict) -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    current_turn = match["current_turn"]
    p1_id = match["player1_id"]
    current_name = p1_name if current_turn == p1_id else p2_name

    p1_d = state["diamonds_found"].get(str(match["player1_id"]), 0)
    p2_d = state["diamonds_found"].get(str(match["player2_id"]), 0)

    lines = [
        "💎 <b>Treasure Hunt</b>",
        "",
        f"👤 @{p1_name}  —  💎 x<b>{p1_d}</b>",
        f"👤 @{p2_name}  —  💎 x<b>{p2_d}</b>",
        "",
        "⚠️ <i>Watch out for bombs! 💣 = instant loss</i>",
        "",
        f"🎯 <b>@{current_name}</b>, pick a cell!",
    ]
    return "\n".join(lines)


def apply_reveal(match: dict, user_id: int, cell_idx: int) -> Tuple[dict, str, bool]:
    state = match["game_state"]
    if state["revealed"][cell_idx] != "hidden":
        return match, "already_revealed", False

    actual = state["cells"][cell_idx]
    state["revealed"][cell_idx] = actual

    if actual == "bomb":
        return match, "bomb", True

    state["diamonds_found"][str(user_id)] = state["diamonds_found"].get(str(user_id), 0) + 1
    match["current_turn"] = (
        match["player2_id"] if match["current_turn"] == match["player1_id"] else match["player1_id"]
    )

    if all(r != "hidden" for r in state["revealed"]):
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
        "💎 <b>Treasure Hunt — Result</b>",
        "",
        f"👤 @{p1_name}  →  💎 x<b>{p1_d}</b>",
        f"👤 @{p2_name}  →  💎 x<b>{p2_d}</b>",
        "",
    ]
    if reason == "bomb":
        lines.append("💣 <b>BOOM!</b> A bomb was triggered!\n")
    if match.get("is_draw"):
        lines.append("🤝 <b>It's a Draw!</b>")
    else:
        lines.append(f"🏆 <b>Winner: @{winner_name}</b> 🎉")
    return "\n".join(lines)
