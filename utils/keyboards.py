from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import GAME_NAMES, GAME_EMOJI, NATIVE_DICE_GAMES, CUSTOM_GAMES
from typing import List, Optional


def game_selection_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key in list(GAME_NAMES.keys()):
        emoji = GAME_EMOJI[game_key]
        name = GAME_NAMES[game_key].replace(f"{emoji} ", "")
        builder.button(
            text=f"{emoji} {name}",
            callback_data=f"sel_game:{challenge_id}:{game_key}",
        )
    builder.adjust(2)
    return builder.as_markup()


def challenge_accept_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Accept", callback_data=f"challenge_accept:{challenge_id}")
    builder.button(text="❌ Decline", callback_data=f"challenge_decline:{challenge_id}")
    builder.adjust(2)
    return builder.as_markup()


def roll_keyboard(match_id: str, game: str) -> InlineKeyboardMarkup:
    from config import DICE_EMOJI_MAP
    emoji = DICE_EMOJI_MAP.get(game, "🎲")
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{emoji} Roll", callback_data=f"roll:{match_id}")
    return builder.as_markup()


def rps_keyboard(match_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪨 Rock", callback_data=f"rps:{match_id}:rock")
    builder.button(text="📄 Paper", callback_data=f"rps:{match_id}:paper")
    builder.button(text="✂️ Scissors", callback_data=f"rps:{match_id}:scissors")
    builder.adjust(3)
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
    builder.adjust(3)
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
    builder.adjust(3)
    return builder.as_markup()


def rematch_keyboard(
    player1_id: int, player2_id: int, game: str, group_id: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Rematch",
        callback_data=f"rematch:{player1_id}:{player2_id}:{game}:{group_id}",
    )
    return builder.as_markup()


def tournament_join_keyboard(tournament_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Join Tournament",
        callback_data=f"tournament_join:{tournament_id}",
    )
    return builder.as_markup()


def tournament_game_select_keyboard(
    admin_id: int, selected_games: List[str], step: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for game_key, game_name in GAME_NAMES.items():
        check = "✅" if game_key in selected_games else "☐"
        builder.button(
            text=f"{check} {game_name}",
            callback_data=f"t_game:{admin_id}:{game_key}",
        )
    builder.adjust(2)
    if selected_games:
        builder.button(
            text="➡️ Continue",
            callback_data=f"t_game_done:{admin_id}",
        )
    return builder.as_markup()


def tournament_size_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    sizes = [4, 8, 16, 32, 64]
    builder = InlineKeyboardBuilder()
    for s in sizes:
        builder.button(
            text=str(s),
            callback_data=f"t_size:{admin_id}:{s}",
        )
    builder.button(
        text="✏️ Custom",
        callback_data=f"t_size_custom:{admin_id}",
    )
    builder.adjust(3)
    return builder.as_markup()


def tournament_final_format_keyboard(admin_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Single Match", callback_data=f"t_final:{admin_id}:single")
    builder.button(text="3️⃣ Best of 3", callback_data=f"t_final:{admin_id}:bo3")
    builder.button(text="5️⃣ Best of 5", callback_data=f"t_final:{admin_id}:bo5")
    builder.adjust(3)
    return builder.as_markup()
