"""
Keyboards — ADVANCED UI VERSION

Changes:
- roll_keyboard, rps_keyboard, tictactoe_keyboard, treasure_keyboard now accept
  is_battle=True to show "Leave Match" instead of "Leave Match" (no Leave in battle rounds)
- Added leave_confirm_keyboard (replaces cancel_confirm_keyboard)
- cancel_confirm_keyboard kept as alias for backward compat
"""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import GAME_NAMES, GAME_EMOJI
from typing import List, Optional


# ─── Challenge / Match Keyboards ────────────────────────────────────────────

def game_selection_keyboard(sel_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name  = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"sel_game:{sel_id}:{game_key}")
    builder.adjust(2)
    return builder.as_markup()


def challenge_accept_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Accept Challenge", callback_data=f"challenge_accept:{challenge_id}")
    builder.button(text="<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Decline",          callback_data=f"challenge_decline:{challenge_id}")
    builder.adjust(2)
    return builder.as_markup()


def match_confirm_keyboard(confirm_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> I'm Ready! Let's Go!", callback_data=f"match_confirm:{confirm_id}")
    return builder.as_markup()


def roll_keyboard(match_id: str, game: str, is_battle: bool = False) -> InlineKeyboardMarkup:
    from config import DICE_EMOJI_MAP
    emoji = DICE_EMOJI_MAP.get(game, "🎲")
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{emoji} Roll Now!", callback_data=f"roll:{match_id}")
    if is_battle:
        builder.button(text="<tg-emoji emoji-id='5337328443962960187'>🚪</tg-emoji> Leave Match", callback_data=f"leave_match:{match_id}")
    else:
        builder.button(text="<tg-emoji emoji-id='5337328443962960187'>🚪</tg-emoji> Leave Match", callback_data=f"leave_match:{match_id}")
    builder.adjust(1)
    return builder.as_markup()


def rps_keyboard(match_id: str, is_battle: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='6325790754543241229'>🪨</tg-emoji> Rock",     callback_data=f"rps:{match_id}:rock")
    builder.button(text="<tg-emoji emoji-id='5873153278023307367'>📄</tg-emoji> Paper",    callback_data=f"rps:{match_id}:paper")
    builder.button(text="<tg-emoji emoji-id='5870462219019358212'>✂️</tg-emoji> Scissors", callback_data=f"rps:{match_id}:scissors")
    builder.button(text="<tg-emoji emoji-id='5337328443962960187'>🚪</tg-emoji> Leave Match", callback_data=f"leave_match:{match_id}")
    builder.adjust(3, 1)
    return builder.as_markup()


def tictactoe_keyboard(match_id: str, board: List[str], is_battle: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    cell_map = {" ": "⬜", "X": "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji>", "O": "⭕"}
    for i, cell in enumerate(board):
        display = cell_map.get(cell, "⬜")
        builder.button(
            text          = display,
            callback_data = f"ttt:{match_id}:{i}" if cell == " " else f"ttt_noop:{i}",
        )
    builder.button(text="<tg-emoji emoji-id='5337328443962960187'>🚪</tg-emoji> Leave Match", callback_data=f"leave_match:{match_id}")
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()


def treasure_keyboard(match_id: str, board: List[str], is_battle: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, cell in enumerate(board):
        if cell == "hidden":
            builder.button(text="<tg-emoji emoji-id='6143438580732664355'>🔲</tg-emoji>", callback_data=f"treasure:{match_id}:{i}")
        elif cell == "diamond":
            builder.button(text="<tg-emoji emoji-id='4956719506027185156'>💎</tg-emoji>", callback_data=f"treasure_noop:{i}")
        elif cell == "bomb":
            builder.button(text="<tg-emoji emoji-id='5280569974404966639'>💣</tg-emoji>", callback_data=f"treasure_noop:{i}")
    builder.button(text="<tg-emoji emoji-id='5337328443962960187'>🚪</tg-emoji> Leave Match", callback_data=f"leave_match:{match_id}")
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()


def post_match_keyboard(p1_id: int, p2_id: int, game: str, group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> Rematch!",    callback_data=f"rematch_req:{p1_id}:{p2_id}:{game}:{group_id}")
    builder.button(text="<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Choose Game", callback_data=f"choose_game:{p1_id}:{p2_id}:{group_id}")
    builder.adjust(2)
    return builder.as_markup()


def choose_game_keyboard(p1_id: int, p2_id: int, group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name  = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"newgame_req:{p1_id}:{p2_id}:{group_id}:{game_key}")
    builder.adjust(2)
    return builder.as_markup()


def rematch_accept_keyboard(req_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Accept Rematch", callback_data=f"rematch_accept:{req_id}")
    builder.button(text="<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Decline",        callback_data=f"rematch_decline:{req_id}")
    builder.adjust(2)
    return builder.as_markup()


def newgame_accept_keyboard(req_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Accept",  callback_data=f"newgame_accept:{req_id}")
    builder.button(text="<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Decline", callback_data=f"newgame_decline:{req_id}")
    builder.adjust(2)
    return builder.as_markup()


def leave_confirm_keyboard(match_id: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard for Leave Match / Forfeit."""
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='6082411364653993798'>🏳</tg-emoji>️ Yes, Forfeit",  callback_data=f"leave_confirm:{match_id}")
    builder.button(text="<tg-emoji emoji-id='5391112412445288650'>🔙</tg-emoji> No, Continue",  callback_data=f"leave_abort:{match_id}")
    builder.adjust(2)
    return builder.as_markup()


# Backward-compat alias
def cancel_confirm_keyboard(match_id: str) -> InlineKeyboardMarkup:
    return leave_confirm_keyboard(match_id)


# ─── Tournament Keyboards ────────────────────────────────────────────────────

def tournament_join_keyboard(tournament_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> Join Tournament!", callback_data=f"tournament_join:{tournament_id}")
    return builder.as_markup()


def tournament_game_select_keyboard(admin_id: int, selected_games: List[str], step: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key, game_name in GAME_NAMES.items():
        check = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji>" if game_key in selected_games else "<tg-emoji emoji-id='5440621591387980068'>☐</tg-emoji>"
        builder.button(text=f"{check} {game_name}", callback_data=f"t_game:{admin_id}:{game_key}")
    builder.adjust(2)
    if selected_games:
        builder.button(text="<tg-emoji emoji-id='4956282853882069908'>➡️</tg-emoji> Continue", callback_data=f"t_game_done:{admin_id}")
    return builder.as_markup()


def tournament_size_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in [4, 8, 16, 32, 64]:
        builder.button(text=str(s), callback_data=f"t_size:{admin_id}:{s}")
    builder.button(text="<tg-emoji emoji-id='5395444784611480792'>✏</tg-emoji>️ Custom", callback_data=f"t_size_custom:{admin_id}")
    builder.adjust(3)
    return builder.as_markup()


def tournament_final_format_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Single Match", callback_data=f"t_final:{admin_id}:single")
    builder.button(text="3️⃣ Best of 3",    callback_data=f"t_final:{admin_id}:bo3")
    builder.button(text="5️⃣ Best of 5",    callback_data=f"t_final:{admin_id}:bo5")
    builder.adjust(3)
    return builder.as_markup()


# ─── Paid Battle Form Keyboards ──────────────────────────────────────────────

def battle_form_keyboard(
    battle_id: Optional[str],
    game: Optional[str],
    rounds: Optional[int],
    amount: Optional[int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Game button
    if game:
        emoji = GAME_EMOJI.get(game, "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji>")
        gname = GAME_NAMES.get(game, game).replace(f"{emoji} ", "")
        game_label = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {emoji} {gname}"
    else:
        game_label = "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Select Game  ▶"

    rounds_label = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {rounds} Rounds" if rounds else "<tg-emoji emoji-id='6237485887635067877'>🔢</tg-emoji> Set Rounds  ▶"
    amount_label = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> ₹{amount} Bet"   if amount else "<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Set Amount  ▶"

    builder.button(text=game_label,   callback_data=f"btf_game:{battle_id}"   if battle_id else "btf_noop")
    builder.button(text=rounds_label, callback_data=f"btf_rounds:{battle_id}" if battle_id else "btf_noop")
    builder.button(text=amount_label, callback_data=f"btf_amount:{battle_id}" if battle_id else "btf_noop")

    if game and rounds and amount and battle_id:
        builder.button(text="<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> Send Challenge!", callback_data=f"btf_submit:{battle_id}")
    else:
        builder.button(text="⏳ Fill all fields to send", callback_data="btf_noop")

    if battle_id:
        builder.button(text="<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Cancel Battle", callback_data=f"btf_cancel:{battle_id}")

    builder.adjust(1)
    return builder.as_markup()


# TicTacToe excluded from paid battles (too short for multi-round)
BATTLE_GAME_NAMES = {k: v for k, v in GAME_NAMES.items() if k != "tictactoe"}


def battle_game_select_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in BATTLE_GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name  = BATTLE_GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"btf_game_sel:{battle_id}:{game_key}")
    builder.button(text="⬅️ Back to Form", callback_data=f"btf_back:{battle_id}")
    builder.adjust(2)
    return builder.as_markup()


def battle_rounds_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in range(1, 11):
        label = f"{n}" + (" <tg-emoji emoji-id='6136464120779638846'>★</tg-emoji>" if n in (3, 5, 7) else "")
        builder.button(text=label, callback_data=f"btf_rounds_sel:{battle_id}:{n}")
    builder.button(text="⬅️ Back to Form", callback_data=f"btf_back:{battle_id}")
    builder.adjust(5, 5, 1)
    return builder.as_markup()


def battle_confirm_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> I Confirm — Let's Fight!", callback_data=f"bt_confirm:{battle_id}")
    builder.button(text="<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Decline",                   callback_data=f"bt_decline:{battle_id}")
    builder.adjust(1)
    return builder.as_markup()


def battle_admin_approve_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text          = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Payment Received — Approve Battle",
        callback_data = f"bt_admin_approve:{battle_id}",
    )
    return builder.as_markup()


def battle_ready_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> I'm Ready — Let's Battle!", callback_data=f"bt_ready:{battle_id}")
    return builder.as_markup()


def battle_payout_done_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text          = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Payment Sent to Winner",
        callback_data = f"bt_payment_done:{battle_id}",
    )
    return builder.as_markup()
