from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import GAME_NAMES, GAME_EMOJI
from typing import List, Optional


# ─── Challenge / Match Keyboards ────────────────────────────────────────────

def game_selection_keyboard(sel_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"sel_game:{sel_id}:{game_key}")
    builder.adjust(2)
    return builder.as_markup()


def challenge_accept_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Accept", callback_data=f"challenge_accept:{challenge_id}")
    builder.button(text="❌ Decline", callback_data=f"challenge_decline:{challenge_id}")
    builder.adjust(2)
    return builder.as_markup()


def match_confirm_keyboard(confirm_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚡ I'm Ready!", callback_data=f"match_confirm:{confirm_id}")
    return builder.as_markup()


def roll_keyboard(match_id: str, game: str) -> InlineKeyboardMarkup:
    from config import DICE_EMOJI_MAP
    emoji = DICE_EMOJI_MAP.get(game, "🎲")
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{emoji} Roll", callback_data=f"roll:{match_id}")
    builder.button(text="🚫 Forfeit", callback_data=f"cancel_match:{match_id}")
    builder.adjust(1)
    return builder.as_markup()


def rps_keyboard(match_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪨 Rock", callback_data=f"rps:{match_id}:rock")
    builder.button(text="📄 Paper", callback_data=f"rps:{match_id}:paper")
    builder.button(text="✂️ Scissors", callback_data=f"rps:{match_id}:scissors")
    builder.button(text="🚫 Forfeit", callback_data=f"cancel_match:{match_id}")
    builder.adjust(3, 1)
    return builder.as_markup()


def tictactoe_keyboard(match_id: str, board: List[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    cell_map = {" ": "⬜", "X": "❌", "O": "⭕"}
    for i, cell in enumerate(board):
        display = cell_map.get(cell, "⬜")
        builder.button(
            text=display,
            callback_data=f"ttt:{match_id}:{i}" if cell == " " else f"ttt_noop:{i}",
        )
    builder.button(text="🚫 Forfeit", callback_data=f"cancel_match:{match_id}")
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()


def treasure_keyboard(match_id: str, board: List[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, cell in enumerate(board):
        if cell == "hidden":
            builder.button(text="🔲", callback_data=f"treasure:{match_id}:{i}")
        elif cell == "diamond":
            builder.button(text="💎", callback_data=f"treasure_noop:{i}")
        elif cell == "bomb":
            builder.button(text="💣", callback_data=f"treasure_noop:{i}")
    builder.button(text="🚫 Forfeit", callback_data=f"cancel_match:{match_id}")
    builder.adjust(3, 3, 3, 1)
    return builder.as_markup()


def post_match_keyboard(p1_id: int, p2_id: int, game: str, group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Rematch", callback_data=f"rematch_req:{p1_id}:{p2_id}:{game}:{group_id}")
    builder.button(text="🎮 Choose Game", callback_data=f"choose_game:{p1_id}:{p2_id}:{group_id}")
    builder.adjust(2)
    return builder.as_markup()


def choose_game_keyboard(p1_id: int, p2_id: int, group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"newgame_req:{p1_id}:{p2_id}:{group_id}:{game_key}")
    builder.adjust(2)
    return builder.as_markup()


def rematch_accept_keyboard(req_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Accept Rematch", callback_data=f"rematch_accept:{req_id}")
    builder.button(text="❌ Decline", callback_data=f"rematch_decline:{req_id}")
    builder.adjust(2)
    return builder.as_markup()


def newgame_accept_keyboard(req_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Accept", callback_data=f"newgame_accept:{req_id}")
    builder.button(text="❌ Decline", callback_data=f"newgame_decline:{req_id}")
    builder.adjust(2)
    return builder.as_markup()


def cancel_confirm_keyboard(match_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💀 Yes, Forfeit", callback_data=f"cancel_confirm:{match_id}")
    builder.button(text="⬅️ Continue Playing", callback_data=f"cancel_abort:{match_id}")
    builder.adjust(2)
    return builder.as_markup()


# ─── Tournament Keyboards ────────────────────────────────────────────────────

def tournament_join_keyboard(tournament_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Join Tournament", callback_data=f"tournament_join:{tournament_id}")
    return builder.as_markup()


def tournament_game_select_keyboard(admin_id: int, selected_games: List[str], step: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key, game_name in GAME_NAMES.items():
        check = "✅" if game_key in selected_games else "☐"
        builder.button(text=f"{check} {game_name}", callback_data=f"t_game:{admin_id}:{game_key}")
    builder.adjust(2)
    if selected_games:
        builder.button(text="➡️ Continue", callback_data=f"t_game_done:{admin_id}")
    return builder.as_markup()


def tournament_size_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in [4, 8, 16, 32, 64]:
        builder.button(text=str(s), callback_data=f"t_size:{admin_id}:{s}")
    builder.button(text="✏️ Custom", callback_data=f"t_size_custom:{admin_id}")
    builder.adjust(3)
    return builder.as_markup()


def tournament_final_format_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Single", callback_data=f"t_final:{admin_id}:single")
    builder.button(text="3️⃣ Best of 3", callback_data=f"t_final:{admin_id}:bo3")
    builder.button(text="5️⃣ Best of 5", callback_data=f"t_final:{admin_id}:bo5")
    builder.adjust(3)
    return builder.as_markup()


# ─── Paid Battle Form Keyboards ──────────────────────────────────────────────

def battle_form_keyboard(battle_id: str, game: Optional[str], rounds: Optional[int], amount: Optional[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    game_label = f"✅ {GAME_NAMES.get(game, game)}" if game else "🎮 Select Game ▶"
    rounds_label = f"✅ Rounds: {rounds}" if rounds else "🔢 Set Rounds ▶"
    amount_label = f"✅ Amount: ₹{amount}" if amount else "💰 Set Amount ▶"

    builder.button(text=game_label, callback_data=f"btf_game:{battle_id}")
    builder.button(text=rounds_label, callback_data=f"btf_rounds:{battle_id}")
    builder.button(text=amount_label, callback_data=f"btf_amount:{battle_id}")

    all_set = game and rounds and amount
    if all_set:
        builder.button(text="⚔️ Send Challenge", callback_data=f"btf_submit:{battle_id}")
    else:
        builder.button(text="⏳ Fill all fields to send", callback_data="btf_noop")

    builder.button(text="❌ Cancel", callback_data=f"btf_cancel:{battle_id}")
    builder.adjust(1)
    return builder.as_markup()


def battle_game_select_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"btf_game_sel:{battle_id}:{game_key}")
    builder.button(text="⬅️ Back", callback_data=f"btf_back:{battle_id}")
    builder.adjust(2)
    return builder.as_markup()


def battle_rounds_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in range(1, 11):
        builder.button(text=str(n), callback_data=f"btf_rounds_sel:{battle_id}:{n}")
    builder.button(text="⬅️ Back", callback_data=f"btf_back:{battle_id}")
    builder.adjust(5, 5, 1)
    return builder.as_markup()


def battle_confirm_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm", callback_data=f"bt_confirm:{battle_id}")
    builder.button(text="❌ Decline", callback_data=f"bt_decline:{battle_id}")
    builder.adjust(2)
    return builder.as_markup()


def battle_admin_approve_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Payment Received — Approve Battle", callback_data=f"bt_admin_approve:{battle_id}")
    return builder.as_markup()


def battle_ready_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚡ I'm Ready!", callback_data=f"bt_ready:{battle_id}")
    return builder.as_markup()


def battle_next_round_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Same Game", callback_data=f"bt_next_same:{battle_id}")
    builder.button(text="🎮 Choose Different Game", callback_data=f"bt_next_pick:{battle_id}")
    builder.adjust(2)
    return builder.as_markup()


def battle_next_game_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in GAME_NAMES:
        emoji = GAME_EMOJI[game_key]
        name = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(text=f"{emoji} {name}", callback_data=f"bt_next_game:{battle_id}:{game_key}")
    builder.adjust(2)
    return builder.as_markup()


def battle_next_accept_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Accept Game", callback_data=f"bt_next_accept:{battle_id}")
    builder.button(text="❌ Decline (Same Game)", callback_data=f"bt_next_decline:{battle_id}")
    builder.adjust(2)
    return builder.as_markup()


def battle_payout_done_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Payment Sent to Winner", callback_data=f"bt_payment_done:{battle_id}")
    return builder.as_markup()
