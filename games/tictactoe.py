from typing import Optional, Tuple


def get_initial_state(player1_id: int, player2_id: int) -> dict:
    return {"board": [" "] * 9, "player1_symbol": "X", "player2_symbol": "O"}


def render_board(match: dict) -> str:
    state = match["game_state"]
    board = state["board"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    current_turn = match["current_turn"]
    p1_id = match["player1_id"]

    cell_map = {" ": "⬜", "X": "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji>", "O": "⭕"}
    rows = []
    for i in range(0, 9, 3):
        row = "  ".join(cell_map.get(board[i + j], "⬜") for j in range(3))
        rows.append(row)

    current_name = p1_name if current_turn == p1_id else p2_name
    lines = [
        "⭕ <b>Tic Tac Toe</b>",
        "",
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p1_name} <tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji>  vs  <tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p2_name} ⭕",
        "",
        *rows,
        "",
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>@{current_name}</b>, your turn! Tap a cell ⬇️",
    ]
    return "\n".join(lines)


def apply_move(match: dict, user_id: int, cell: int) -> Tuple[dict, bool]:
    state = match["game_state"]
    board = state["board"]
    if board[cell] != " ":
        return match, False
    symbol = state["player1_symbol"] if user_id == match["player1_id"] else state["player2_symbol"]
    board[cell] = symbol
    match["current_turn"] = (
        match["player2_id"] if match["current_turn"] == match["player1_id"] else match["player1_id"]
    )
    return match, True


def check_winner(board: list) -> Optional[str]:
    wins = [
        (0,1,2),(3,4,5),(6,7,8),
        (0,3,6),(1,4,7),(2,5,8),
        (0,4,8),(2,4,6),
    ]
    for a, b, c in wins:
        if board[a] == board[b] == board[c] and board[a] != " ":
            return board[a]
    return None


def is_finished(match: dict) -> Tuple[bool, Optional[str]]:
    board = match["game_state"]["board"]
    w = check_winner(board)
    if w:
        return True, w
    if " " not in board:
        return True, None
    return False, None


def get_winner(match: dict) -> tuple:
    board = match["game_state"]["board"]
    state = match["game_state"]
    w = check_winner(board)
    if w is None:
        return None, None, True
    if w == state["player1_symbol"]:
        return match["player1_id"], match["player1_name"], False
    return match["player2_id"], match["player2_name"], False


def render_result(match: dict) -> str:
    board = match["game_state"]["board"]
    p1_name = match["player1_name"]
    p2_name = match["player2_name"]
    cell_map = {" ": "⬜", "X": "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji>", "O": "⭕"}
    rows = []
    for i in range(0, 9, 3):
        row = "  ".join(cell_map.get(board[i + j], "⬜") for j in range(3))
        rows.append(row)
    winner_id, winner_name, is_draw = get_winner(match)
    lines = [
        "⭕ <b>Tic Tac Toe — Result</b>",
        "",
        *rows,
        "",
    ]
    if is_draw:
        lines.append("<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>It's a Draw!</b>")
    else:
        lines.append(f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Winner: @{winner_name}</b> <tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji>")
    return "\n".join(lines)
