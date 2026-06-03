import logging
import random
import math
from typing import List, Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.mongodb import get_db
from database.models import TournamentModel, now_utc
from utils.keyboards import (
    tournament_join_keyboard,
    tournament_game_select_keyboard,
    tournament_size_keyboard,
    tournament_final_format_keyboard,
)
from config import GAME_NAMES, GAME_EMOJI

logger = logging.getLogger(__name__)
router = Router()


class TournamentSetup(StatesGroup):
    selecting_games = State()
    selecting_size = State()
    custom_size_input = State()
    selecting_final = State()


_admin_setup_data = {}


async def _is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


@router.message(Command("tournament"))
async def cmd_tournament(message: Message, state: FSMContext):
    if message.chat.type == "private":
        await message.answer("❌ This bot only works in groups.")
        return

    db = get_db()
    user = message.from_user
    group_id = message.chat.id

    if not await _is_group_admin(message.bot, group_id, user.id):
        await message.answer("❌ Only group admins can create tournaments.")
        return

    active_t = await db.tournaments.find_one(
        {"group_id": group_id, "status": {"$in": ["joining", "active"]}}
    )
    if active_t:
        await message.answer("❌ There is already an active tournament in this group.")
        return

    _admin_setup_data[user.id] = {
        "selected_games": [],
        "group_id": group_id,
        "admin_name": user.username or user.first_name,
    }

    await state.set_state(TournamentSetup.selecting_games)
    await message.answer(
        "🏆 <b>Tournament Setup</b>\n\nStep 1: Select games for the tournament.\n(You can select multiple games)",
        parse_mode="HTML",
        reply_markup=tournament_game_select_keyboard(user.id, [], "select"),
    )


@router.callback_query(F.data.startswith("t_game:"))
async def cb_tournament_game_select(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    admin_id, game = int(parts[1]), parts[2]

    if callback.from_user.id != admin_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    data = _admin_setup_data.get(admin_id)
    if not data:
        await callback.answer("❌ Session expired. Use /tournament again.", show_alert=True)
        return

    selected = data["selected_games"]
    if game in selected:
        selected.remove(game)
    else:
        selected.append(game)

    _admin_setup_data[admin_id]["selected_games"] = selected

    await callback.message.edit_reply_markup(
        reply_markup=tournament_game_select_keyboard(admin_id, selected, "select")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("t_game_done:"))
async def cb_tournament_game_done(callback: CallbackQuery, state: FSMContext):
    admin_id = int(callback.data.split(":")[1])

    if callback.from_user.id != admin_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    data = _admin_setup_data.get(admin_id)
    if not data or not data["selected_games"]:
        await callback.answer("❌ Please select at least one game.", show_alert=True)
        return

    await state.set_state(TournamentSetup.selecting_size)
    selected_names = ", ".join(GAME_NAMES[g] for g in data["selected_games"])

    await callback.message.edit_text(
        f"🏆 <b>Tournament Setup</b>\n\n"
        f"✅ Games: {selected_names}\n\n"
        f"Step 2: Select tournament size:",
        parse_mode="HTML",
        reply_markup=tournament_size_keyboard(admin_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("t_size:"))
async def cb_tournament_size(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    admin_id, size = int(parts[1]), int(parts[2])

    if callback.from_user.id != admin_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    _admin_setup_data[admin_id]["size"] = size
    await state.set_state(TournamentSetup.selecting_final)

    data = _admin_setup_data[admin_id]
    selected_names = ", ".join(GAME_NAMES[g] for g in data["selected_games"])

    await callback.message.edit_text(
        f"🏆 <b>Tournament Setup</b>\n\n"
        f"✅ Games: {selected_names}\n"
        f"✅ Size: {size} players\n\n"
        f"Step 3: Final match format:",
        parse_mode="HTML",
        reply_markup=tournament_final_format_keyboard(admin_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("t_size_custom:"))
async def cb_tournament_size_custom(callback: CallbackQuery, state: FSMContext):
    admin_id = int(callback.data.split(":")[1])

    if callback.from_user.id != admin_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    await state.set_state(TournamentSetup.custom_size_input)
    await callback.message.edit_text(
        "Enter the custom tournament size (minimum 4, must be even):",
    )
    await callback.answer()


@router.message(TournamentSetup.custom_size_input)
async def msg_custom_size(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = _admin_setup_data.get(user_id)
    if not data:
        await state.clear()
        return

    try:
        size = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Please enter a valid number.")
        return

    if size < 4:
        await message.answer("❌ Minimum size is 4 players.")
        return
    if size % 2 != 0:
        await message.answer("❌ Size must be an even number.")
        return

    _admin_setup_data[user_id]["size"] = size
    await state.set_state(TournamentSetup.selecting_final)

    selected_names = ", ".join(GAME_NAMES[g] for g in data["selected_games"])
    await message.answer(
        f"🏆 <b>Tournament Setup</b>\n\n"
        f"✅ Games: {selected_names}\n"
        f"✅ Size: {size} players\n\n"
        f"Step 3: Final match format:",
        parse_mode="HTML",
        reply_markup=tournament_final_format_keyboard(user_id),
    )


@router.callback_query(F.data.startswith("t_final:"))
async def cb_tournament_final(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    admin_id, final_format = int(parts[1]), parts[2]

    if callback.from_user.id != admin_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    data = _admin_setup_data.get(admin_id)
    if not data:
        await callback.answer("❌ Session expired.", show_alert=True)
        return

    await state.clear()

    db = get_db()
    group_id = data["group_id"]
    games = data["selected_games"]
    size = data["size"]
    admin_name = data["admin_name"]

    format_names = {"single": "Single Match", "bo3": "Best of 3", "bo5": "Best of 5"}
    format_display = format_names.get(final_format, final_format)

    join_msg = await callback.message.edit_text(
        _render_join_board(0, size, games, format_display),
        parse_mode="HTML",
        reply_markup=tournament_join_keyboard("PLACEHOLDER"),
    )

    tournament = TournamentModel.new(
        group_id=group_id,
        admin_id=admin_id,
        admin_name=admin_name,
        games=games,
        size=size,
        final_format=final_format,
        message_id=join_msg.message_id,
    )
    await db.tournaments.insert_one(tournament)

    await callback.message.bot.edit_message_reply_markup(
        chat_id=group_id,
        message_id=join_msg.message_id,
        reply_markup=tournament_join_keyboard(tournament["tournament_id"]),
    )

    del _admin_setup_data[admin_id]
    await callback.answer()


def _render_join_board(current: int, total: int, games: List[str], final_format: str) -> str:
    game_names = " + ".join(GAME_NAMES.get(g, g) for g in games)
    lines = [
        "🏆 <b>Tournament</b>",
        "",
        f"🎮 Games: {game_names}",
        f"🏁 Final: {final_format}",
        "",
        f"Players: {current}/{total}",
    ]
    return "\n".join(lines)


@router.callback_query(F.data.startswith("tournament_join:"))
async def cb_tournament_join(callback: CallbackQuery):
    db = get_db()
    tournament_id = callback.data.split(":")[1]
    user = callback.from_user

    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    if not tournament:
        await callback.answer("❌ Tournament not found.", show_alert=True)
        return

    if tournament["status"] != "joining":
        await callback.answer("❌ Tournament is no longer accepting players.", show_alert=True)
        return

    players = tournament["players"]

    if any(p["user_id"] == user.id for p in players):
        await callback.answer("❌ You already joined.", show_alert=True)
        return

    players.append({
        "user_id": user.id,
        "username": user.username or user.first_name,
        "first_name": user.first_name,
    })

    if len(players) >= tournament["size"]:
        await db.tournaments.update_one(
            {"tournament_id": tournament_id},
            {"$set": {"players": players, "status": "active"}},
        )
        try:
            await callback.message.edit_text(
                "🎉 <b>Tournament Full!</b>\nStarting...",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass
        await _start_tournament(tournament_id, callback.message.bot)
    else:
        await db.tournaments.update_one(
            {"tournament_id": tournament_id},
            {"$set": {"players": players}},
        )
        format_names = {"single": "Single Match", "bo3": "Best of 3", "bo5": "Best of 5"}
        format_display = format_names.get(tournament["final_format"], tournament["final_format"])
        try:
            await callback.message.edit_text(
                _render_join_board(len(players), tournament["size"], tournament["games"], format_display),
                parse_mode="HTML",
                reply_markup=tournament_join_keyboard(tournament_id),
            )
        except Exception:
            pass
        await callback.answer(f"✅ Joined! ({len(players)}/{tournament['size']})")


async def _start_tournament(tournament_id: str, bot: Bot):
    db = get_db()
    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    if not tournament:
        return

    players = tournament["players"]
    random.shuffle(players)

    brackets = _generate_brackets(players)

    await db.tournaments.update_one(
        {"tournament_id": tournament_id},
        {"$set": {"brackets": brackets, "current_round": 0}},
    )

    board_msg = await bot.send_message(
        chat_id=tournament["group_id"],
        text=_render_tournament_board(brackets, players),
        parse_mode="HTML",
    )

    await db.tournaments.update_one(
        {"tournament_id": tournament_id},
        {"$set": {"board_message_id": board_msg.message_id}},
    )

    await _start_round_matches(tournament_id, bot)


def _generate_brackets(players: list) -> list:
    rounds = []
    current = players[:]

    while len(current) > 1:
        round_matches = []
        for i in range(0, len(current), 2):
            if i + 1 < len(current):
                match = {
                    "match_id": None,
                    "player1": current[i],
                    "player2": current[i + 1],
                    "winner": None,
                    "status": "pending",
                }
                round_matches.append(match)
            else:
                round_matches.append({
                    "match_id": None,
                    "player1": current[i],
                    "player2": None,
                    "winner": current[i],
                    "status": "bye",
                })
        rounds.append(round_matches)
        current = [None] * len(round_matches)

    return rounds


def _render_tournament_board(brackets: list, players: list) -> str:
    round_names = _get_round_names(len(brackets))
    lines = ["🏆 <b>Tournament Bracket</b>", ""]

    for r_idx, (round_matches, r_name) in enumerate(zip(brackets, round_names)):
        lines.append(f"<b>{r_name}</b>")
        for m in round_matches:
            p1 = m["player1"]
            p2 = m["player2"]
            winner = m["winner"]
            status = m["status"]

            if status == "bye":
                p1_name = p1["username"] if p1 else "?"
                lines.append(f"  ⏭️ @{p1_name} (bye)")
            elif status == "finished" and winner:
                p1_name = p1["username"] if p1 else "?"
                p2_name = p2["username"] if p2 else "?"
                w_name = winner["username"] if winner else "?"
                lines.append(f"  ✅ @{p1_name} vs @{p2_name} → @{w_name}")
            elif status == "active":
                p1_name = p1["username"] if p1 else "?"
                p2_name = p2["username"] if p2 else "?"
                lines.append(f"  ⚔️ @{p1_name} vs @{p2_name} (playing)")
            elif status == "pending":
                p1_name = p1["username"] if p1 else "?"
                p2_name = p2["username"] if p2 else "?"
                lines.append(f"  ⏳ @{p1_name} vs @{p2_name}")
            else:
                lines.append(f"  ⏳ TBD vs TBD")
        lines.append("")

    return "\n".join(lines)


def _get_round_names(total_rounds: int) -> list:
    if total_rounds == 1:
        return ["Final"]
    elif total_rounds == 2:
        return ["Semi Finals", "Final"]
    elif total_rounds == 3:
        return ["Quarter Finals", "Semi Finals", "Final"]
    else:
        names = []
        for i in range(total_rounds):
            remaining = total_rounds - i
            if remaining == 1:
                names.append("Final")
            elif remaining == 2:
                names.append("Semi Finals")
            elif remaining == 3:
                names.append("Quarter Finals")
            else:
                names.append(f"Round of {2 ** remaining}")
        return names


async def _start_round_matches(tournament_id: str, bot: Bot):
    from handlers.match import start_match

    db = get_db()
    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    if not tournament:
        return

    current_round = tournament["current_round"]
    if current_round >= len(tournament["brackets"]):
        return

    round_matches = tournament["brackets"][current_round]
    games = tournament["games"]
    game_usage = tournament.get("game_usage", {})

    for idx, tm in enumerate(round_matches):
        if tm["status"] in ("finished", "bye"):
            if tm["status"] == "bye":
                pass
            continue

        if tm["status"] == "pending" and tm["player1"] and tm["player2"]:
            game = _pick_game(games, game_usage)
            game_usage[game] = game_usage.get(game, 0) + 1

            is_final = (current_round == len(tournament["brackets"]) - 1)
            final_format = tournament["final_format"] if is_final else "single"

            tournament_match_id = f"{tournament_id}_{current_round}_{idx}"

            p1 = tm["player1"]
            p2 = tm["player2"]

            match_id = await start_match(
                bot=bot,
                group_id=tournament["group_id"],
                player1_id=p1["user_id"],
                player1_name=p1["username"],
                player2_id=p2["user_id"],
                player2_name=p2["username"],
                game=game,
                tournament_id=tournament_id,
                tournament_match_id=tournament_match_id,
            )

            await db.tournaments.update_one(
                {"tournament_id": tournament_id},
                {
                    "$set": {
                        f"brackets.{current_round}.{idx}.status": "active",
                        f"brackets.{current_round}.{idx}.match_id": match_id,
                        f"brackets.{current_round}.{idx}.game": game,
                        "game_usage": game_usage,
                    }
                },
            )

    await db.tournaments.update_one(
        {"tournament_id": tournament_id},
        {"$set": {"game_usage": game_usage}},
    )

    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    await _update_board(tournament, bot)


def _pick_game(games: list, usage: dict) -> str:
    if not games:
        return "dice"
    if len(games) == 1:
        return games[0]

    min_use = min(usage.get(g, 0) for g in games)
    least_used = [g for g in games if usage.get(g, 0) == min_use]
    return random.choice(least_used)


async def on_tournament_match_finished(
    tournament_id: str,
    tournament_match_id: str,
    winner_id: Optional[int],
    bot: Bot,
):
    if not tournament_id or not tournament_match_id:
        return

    db = get_db()
    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    if not tournament:
        return

    parts = tournament_match_id.split("_")
    if len(parts) < 3:
        return
    round_idx = int(parts[-2])
    match_idx = int(parts[-1])

    brackets = tournament["brackets"]
    if round_idx >= len(brackets) or match_idx >= len(brackets[round_idx]):
        return

    tm = brackets[round_idx][match_idx]

    p1 = tm.get("player1")
    p2 = tm.get("player2")

    winner_obj = None
    if winner_id == p1["user_id"]:
        winner_obj = p1
    elif p2 and winner_id == p2["user_id"]:
        winner_obj = p2

    if not winner_obj:
        return

    await db.tournaments.update_one(
        {"tournament_id": tournament_id},
        {
            "$set": {
                f"brackets.{round_idx}.{match_idx}.winner": winner_obj,
                f"brackets.{round_idx}.{match_idx}.status": "finished",
            }
        },
    )

    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    brackets = tournament["brackets"]

    round_done = all(
        m["status"] in ("finished", "bye") for m in brackets[round_idx]
    )

    if round_done:
        next_round_idx = round_idx + 1
        if next_round_idx >= len(brackets):
            await _finish_tournament(tournament_id, bot)
        else:
            winners = []
            for m in brackets[round_idx]:
                if m.get("winner"):
                    winners.append(m["winner"])

            for idx, w in enumerate(winners):
                pair_idx = idx // 2
                is_p1 = idx % 2 == 0
                if pair_idx < len(brackets[next_round_idx]):  # FIX: removed wrong outer guard
                    field = "player1" if is_p1 else "player2"
                    await db.tournaments.update_one(
                        {"tournament_id": tournament_id},
                        {"$set": {f"brackets.{next_round_idx}.{pair_idx}.{field}": w}},
                    )

            await db.tournaments.update_one(
                {"tournament_id": tournament_id},
                {"$set": {"current_round": next_round_idx}},
            )

            tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
            await _update_board(tournament, bot)
            await _start_round_matches(tournament_id, bot)
    else:
        tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
        await _update_board(tournament, bot)


async def _finish_tournament(tournament_id: str, bot: Bot):
    db = get_db()
    tournament = await db.tournaments.find_one({"tournament_id": tournament_id})
    if not tournament:
        return

    brackets = tournament["brackets"]
    last_round = brackets[-1] if brackets else []
    champion = None
    for m in last_round:
        if m.get("winner"):
            champion = m["winner"]
            break

    if not champion:
        return

    await db.tournaments.update_one(
        {"tournament_id": tournament_id},
        {
            "$set": {
                "status": "finished",
                "winner_id": champion["user_id"],
                "winner_name": champion["username"],
                "finished_at": now_utc(),
            }
        },
    )

    games_display = " + ".join(GAME_NAMES.get(g, g) for g in tournament["games"])
    num_players = len(tournament["players"])

    champion_text = (
        f"━━━━━━━━━━━━━━\n\n"
        f"👑 <b>TOURNAMENT CHAMPION</b>\n\n"
        f"🏆 @{champion['username']}\n\n"
        f"🎮 Tournament Game Set:\n{games_display}\n\n"
        f"👥 Participants: {num_players}\n\n"
        f"━━━━━━━━━━━━━━"
    )

    try:
        await bot.send_message(
            chat_id=tournament["group_id"],
            text=champion_text,
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _update_board(tournament: dict, bot: Bot):
    board_msg_id = tournament.get("board_message_id")
    if not board_msg_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=tournament["group_id"],
            message_id=board_msg_id,
            text=_render_tournament_board(tournament["brackets"], tournament["players"]),
            parse_mode="HTML",
        )
    except Exception:
        pass
