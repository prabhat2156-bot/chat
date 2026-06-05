CHOICES = {"rock": "<tg-emoji emoji-id='6325790754543241229'>🪨</tg-emoji> Rock", "paper": "<tg-emoji emoji-id='5873153278023307367'>📄</tg-emoji> Paper", "scissors": "<tg-emoji emoji-id='5870462219019358212'>✂️</tg-emoji> Scissors"}
WINS_AGAINST = {"rock": "scissors", "scissors": "paper", "paper": "rock"}


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    return {"player1_choice": None, "player2_choice": None}


def render_board(match: dict) -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    p1_status = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Chosen</b>" if state["player1_choice"] else "⏳ Choosing..."
    p2_status = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Chosen</b>" if state["player2_choice"] else "⏳ Choosing..."
    lines = [
        "<tg-emoji emoji-id='6325790754543241229'>🪨</tg-emoji> <b>Rock Paper Scissors</b>",
        "",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p1_name}  —  {p1_status}",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p2_name}  —  {p2_status}",
        "",
        "<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> <b>Both pick secretly — reveal when both choose!</b>",
    ]
    return "\n".join(lines)


def apply_choice(match: dict, user_id: int, choice: str) -> dict:
    if user_id == match["player1_id"] and not match["game_state"]["player1_choice"]:
        match["game_state"]["player1_choice"] = choice
    elif user_id == match["player2_id"] and not match["game_state"]["player2_choice"]:
        match["game_state"]["player2_choice"] = choice
    return match


def is_finished(match: dict) -> bool:
    s = match["game_state"]
    return bool(s["player1_choice"] and s["player2_choice"])


def get_winner(match: dict) -> tuple:
    s = match["game_state"]
    c1, c2 = s["player1_choice"], s["player2_choice"]
    if c1 == c2:
        return None, None, True
    elif WINS_AGAINST[c1] == c2:
        return match["player1_id"], match["player1_name"], False
    else:
        return match["player2_id"], match["player2_name"], False


def render_result(match: dict) -> str:
    s = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    c1 = CHOICES.get(s["player1_choice"], "?")
    c2 = CHOICES.get(s["player2_choice"], "?")
    winner_id, winner_name, is_draw = get_winner(match)
    lines = [
        "<tg-emoji emoji-id='6325790754543241229'>🪨</tg-emoji> <b>Rock Paper Scissors — Result</b>",
        "",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p1_name}  →  <b>{c1}</b>",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p2_name}  →  <b>{c2}</b>",
        "",
    ]
    if is_draw:
        lines.append("<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>It's a Draw!</b>")
    else:
        lines.append(f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Winner: @{winner_name}</b> <tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji>")
    return "\n".join(lines)
