CHOICES = {"rock": "🪨 Rock", "paper": "📄 Paper", "scissors": "✂️ Scissors"}

WINS_AGAINST = {"rock": "scissors", "scissors": "paper", "paper": "rock"}


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    return {
        "player1_choice": None,
        "player2_choice": None,
    }


def render_board(match: dict) -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    p1_id = match["player1_id"]
    p2_id = match["player2_id"]

    p1_status = "✅" if state["player1_choice"] else "❌"
    p2_status = "✅" if state["player2_choice"] else "❌"

    lines = [
        "🪨 Rock Paper Scissors",
        "",
        f"@{p1_name} {p1_status}",
        f"@{p2_name} {p2_status}",
        "",
        "Choose your move:",
    ]
    return "\n".join(lines)


def apply_choice(match: dict, user_id: int, choice: str) -> dict:
    if user_id == match["player1_id"] and not match["game_state"]["player1_choice"]:
        match["game_state"]["player1_choice"] = choice
    elif user_id == match["player2_id"] and not match["game_state"]["player2_choice"]:
        match["game_state"]["player2_choice"] = choice
    return match


def is_finished(match: dict) -> bool:
    state = match["game_state"]
    return bool(state["player1_choice"] and state["player2_choice"])


def get_winner(match: dict) -> tuple:
    state = match["game_state"]
    c1 = state["player1_choice"]
    c2 = state["player2_choice"]

    if c1 == c2:
        return None, None, True
    elif WINS_AGAINST[c1] == c2:
        return match["player1_id"], match["player1_name"], False
    else:
        return match["player2_id"], match["player2_name"], False


def render_result(match: dict) -> str:
    state = match["game_state"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    c1 = CHOICES.get(state["player1_choice"], "?")
    c2 = CHOICES.get(state["player2_choice"], "?")

    winner_id, winner_name, is_draw = get_winner(match)

    lines = [
        "🪨 Rock Paper Scissors — Result",
        "",
        f"@{p1_name}: {c1}",
        f"@{p2_name}: {c2}",
        "",
    ]
    if is_draw:
        lines.append("🤝 It's a Draw!")
    else:
        lines.append(f"🏆 Winner: @{winner_name}")

    return "\n".join(lines)
