from typing import Optional, Tuple


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    return {
        "board": [" "] * 9,
        "player1_symbol": "X",
        "player2_symbol": "O",
    }


def render_board(match: dict) -> str:
    state = match["game_state"]
    board = state["board"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    current_turn = match["current_turn"]
    p1_id = match["player1_id"]

    cell_map = {" ": "⬜", "X": "❌", "O": "⭕"}

    rows = []
    for i in range(0, 9, 3):
        row = " ".join(cell_map.get(board[i + j], "⬜") for j in range(3))
        rows.append(row)

    current_name = p1_name if current_turn == p1_id else match["player2_name"]

    lines = [
        "⭕ Tic Tac Toe",
        "",
        f"@{p1_name} ❌  vs  @{match['player2_name']} ⭕",
        "",
        *rows,
        "",
        f"🎯 Turn: @{current_name}",
    ]
    return "\n".join(lines)


def apply_move(match: dict, user_id: int, cell: int) -> Tuple[dict, bool]:
    state = match["game_state"]
    board = state["board"]

    if board[cell] != " ":
        return match, False

    symbol = (
        state["player1_symbol"]
        if user_id == match["player1_id"]
        else state["player2_symbol"]
    )
    board[cell] = symbol
    next_turn = (
        match["player2_id"]
        if match["current_turn"] == match["player1_id"]
        else match["player1_id"]
    )
    match["current_turn"] = next_turn
    return match, True


def check_winner(board: list) -> Optional[str]:
    wins = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    for a, b, c in wins:
        if board[a] == board[b] == board[c] and board[a] != " ":
            return board[a]
    return None


def is_draw(board: list) -> bool:
    return " " not in board and check_winner(board) is None


def is_finished(match: dict) -> Tuple[bool, Optional[str]]:
    board = match["game_state"]["board"]
    winner_symbol = check_winner(board)
    if winner_symbol:
        return True, winner_symbol
    if is_draw(board):
        return True, None
    return False, None


def get_winner(match: dict) -> tuple:
    board = match["game_state"]["board"]
    state = match["game_state"]
    winner_symbol = check_winner(board)
    if winner_symbol is None:
        return None, None, True
    if winner_symbol == state["player1_symbol"]:
        return match["player1_id"], match["player1_name"], False
    else:
        return match["player2_id"], match["player2_name"], False


def render_result(match: dict) -> str:
    state = match["game_state"]
    board = state["board"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]

    cell_map = {" ": "⬜", "X": "❌", "O": "⭕"}
    rows = []
    for i in range(0, 9, 3):
        row = " ".join(cell_map.get(board[i + j], "⬜") for j in range(3))
        rows.append(row)

    winner_id, winner_name, is_draw_result = get_winner(match)

    lines = [
        "⭕ Tic Tac Toe — Result",
        "",
        *rows,
        "",
    ]
    if is_draw_result:
        lines.append("🤝 It's a Draw!")
    else:
        lines.append(f"🏆 Winner: @{winner_name}")

    return "\n".join(lines)
