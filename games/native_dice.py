from config import GAME_NAMES, DICE_EMOJI_MAP, DICE_MAX_VALUE, GAME_EMOJI


def get_initial_state(game: str, player1_id: int, player2_id: int) -> dict:
    return {
        "player1_rolled": False,
        "player2_rolled": False,
        "player1_value": None,
        "player2_value": None,
    }


def render_board(match: dict) -> str:
    game = match["game"]
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    p1_id = match["player1_id"]
    p2_id = match["player2_id"]
    current_turn = match["current_turn"]

    game_title = GAME_NAMES.get(game, game)

    p1_status = (
        f"✅ {state['player1_value']}" if state["player1_rolled"] else "❌ Not Rolled"
    )
    p2_status = (
        f"✅ {state['player2_value']}" if state["player2_rolled"] else "❌ Not Rolled"
    )

    lines = [
        f"{game_title} Match",
        "",
        f"@{p1_name} {p1_status}",
        f"@{p2_name} {p2_status}",
        "",
    ]

    if not state["player1_rolled"] or not state["player2_rolled"]:
        current_name = p1_name if current_turn == p1_id else p2_name
        lines.append(f"🎯 Turn: @{current_name}")

    return "\n".join(lines)


def apply_roll(match: dict, user_id: int, value: int) -> dict:
    state = match["game_state"]
    if user_id == match["player1_id"] and not state["player1_rolled"]:
        state["player1_rolled"] = True
        state["player1_value"] = value
        match["current_turn"] = match["player2_id"]
    elif user_id == match["player2_id"] and not state["player2_rolled"]:
        state["player2_rolled"] = True
        state["player2_value"] = value
        match["current_turn"] = match["player1_id"]
    return match


def is_finished(match: dict) -> bool:
    state = match["game_state"]
    return state["player1_rolled"] and state["player2_rolled"]


def get_winner(match: dict) -> tuple:
    state = match["game_state"]
    v1 = state["player1_value"]
    v2 = state["player2_value"]

    if v1 > v2:
        return match["player1_id"], match["player1_name"], False
    elif v2 > v1:
        return match["player2_id"], match["player2_name"], False
    else:
        return None, None, True


def render_result(match: dict) -> str:
    game = match["game"]
    state = match["game_state"]
    game_title = GAME_NAMES.get(game, game)
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    p1_val = state["player1_value"]
    p2_val = state["player2_value"]

    winner_id, winner_name, is_draw = get_winner(match)

    lines = [
        f"{game_title} Match — Result",
        "",
        f"@{p1_name}: {p1_val}",
        f"@{p2_name}: {p2_val}",
        "",
    ]

    if is_draw:
        lines.append("🤝 It's a Draw!")
    else:
        lines.append(f"🏆 Winner: @{winner_name}")

    return "\n".join(lines)
