from config import GAME_NAMES, DICE_EMOJI_MAP


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
    current_turn = match["current_turn"]
    game_title = GAME_NAMES.get(game, game)

    p1_status = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>{state['player1_value']}</b>" if state["player1_rolled"] else "⏳ Not Rolled"
    p2_status = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>{state['player2_value']}</b>" if state["player2_rolled"] else "⏳ Not Rolled"

    current_name = p1_name if current_turn == p1_id else p2_name
    lines = [
        f"<b>{game_title} Match</b>",
        "",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p1_name}  —  {p1_status}",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p2_name}  —  {p2_status}",
        "",
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>@{current_name}</b>, your turn! Press Roll ⬇️",
    ]
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
        f"<b>{game_title} — Result</b>",
        "",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p1_name}  →  <b>{p1_val}</b>",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p2_name}  →  <b>{p2_val}</b>",
        "",
    ]
    if is_draw:
        lines.append("<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>It's a Draw!</b>")
    else:
        lines.append(f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Winner: @{winner_name}</b> <tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji>")
    return "\n".join(lines)
