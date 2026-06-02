import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command

from database.mongodb import get_db
from database.models import MatchModel, now_utc
from utils.keyboards import (
    roll_keyboard,
    rps_keyboard,
    tictactoe_keyboard,
    treasure_keyboard,
    rematch_keyboard,
)
from utils import timeout_manager
from utils.db_helpers import record_match_result, get_active_match_for_user
from config import (
    NATIVE_DICE_GAMES,
    GAME_NAMES,
    TURN_TIMEOUT,
    TURN_WARNING_TIMEOUT,
    DICE_EMOJI_MAP,
)
import games.native_dice as dice_game
import games.rps as rps_game
import games.tictactoe as ttt_game
import games.guess_number as guess_game
import games.treasure_hunt as treasure_game

logger = logging.getLogger(__name__)
router = Router()


async def start_match(
    bot: Bot,
    group_id: int,
    player1_id: int,
    player1_name: str,
    player2_id: int,
    player2_name: str,
    game: str,
    tournament_id: str = None,
    tournament_match_id: str = None,
) -> str:
    db = get_db()

    game_state = {}
    if game in NATIVE_DICE_GAMES:
        game_state = dice_game.get_initial_state(game, player1_id, player2_id)
    elif game == "rps":
        game_state = rps_game.get_initial_state(player1_id, player2_id)
    elif game == "tictactoe":
        game_state = ttt_game.get_initial_state(player1_id, player2_id)
    elif game == "guess":
        game_state = guess_game.get_initial_state(player1_id, player2_id)
    elif game == "treasure":
        game_state = treasure_game.get_initial_state(player1_id, player2_id)

    match = MatchModel.new(
        player1_id=player1_id,
        player1_name=player1_name,
        player2_id=player2_id,
        player2_name=player2_name,
        game=game,
        group_id=group_id,
        message_id=0,
        tournament_id=tournament_id,
        tournament_match_id=tournament_match_id,
    )
    match["game_state"] = game_state

    board_text, reply_markup = _build_board(match)

    msg = await bot.send_message(
        chat_id=group_id,
        text=board_text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )
    match["message_id"] = msg.message_id
    await db.matches.insert_one(match)

    if game == "guess":
        pass

    _schedule_turn_timeout(match["match_id"], bot)

    return match["match_id"]


def _build_board(match: dict):
    game = match["game"]
    if game in NATIVE_DICE_GAMES:
        text = dice_game.render_board(match)
        markup = roll_keyboard(match["match_id"], game)
    elif game == "rps":
        text = rps_game.render_board(match)
        markup = rps_keyboard(match["match_id"])
    elif game == "tictactoe":
        text = ttt_game.render_board(match)
        markup = ttt_game_keyboard(match)
    elif game == "guess":
        text = guess_game.render_board(match)
        markup = None
    elif game == "treasure":
        text = treasure_game.render_board(match)
        markup = treasure_keyboard(match["match_id"], match["game_state"]["revealed"])
    else:
        text = "Match started."
        markup = None
    return text, markup


def ttt_game_keyboard(match: dict):
    return tictactoe_keyboard(match["match_id"], match["game_state"]["board"])


def _schedule_turn_timeout(match_id: str, bot: Bot):
    timeout_manager.cancel_all_for_match(match_id)
    timeout_manager.set_timeout(
        f"turn_warn_{match_id}",
        TURN_TIMEOUT,
        _turn_timeout_warn,
        match_id,
        bot,
    )


async def _turn_timeout_warn(match_id: str, bot: Bot):
    db = get_db()
    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        return

    current_id = match["current_turn"]
    current_name = (
        match["player1_name"]
        if current_id == match["player1_id"]
        else match["player2_name"]
    )

    await db.matches.update_one(
        {"match_id": match_id}, {"$set": {"timeout_warned": True}}
    )

    try:
        await bot.send_message(
            chat_id=match["group_id"],
            text=f"⚠️ @{current_name} has 60 more seconds to make a move or you forfeit!",
        )
    except Exception:
        pass

    timeout_manager.set_timeout(
        f"turn_forfeit_{match_id}",
        TURN_WARNING_TIMEOUT,
        _turn_forfeit,
        match_id,
        bot,
    )


async def _turn_forfeit(match_id: str, bot: Bot):
    db = get_db()
    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        return

    current_id = match["current_turn"]
    loser_name = (
        match["player1_name"]
        if current_id == match["player1_id"]
        else match["player2_name"]
    )
    winner_id = (
        match["player2_id"]
        if current_id == match["player1_id"]
        else match["player1_id"]
    )
    winner_name = (
        match["player2_name"]
        if current_id == match["player1_id"]
        else match["player1_name"]
    )

    await db.matches.update_one(
        {"match_id": match_id},
        {
            "$set": {
                "status": "finished",
                "winner_id": winner_id,
                "loser_id": current_id,
                "forfeit": True,
                "finished_at": now_utc(),
            }
        },
    )

    await record_match_result(
        match["player1_id"], match["player1_name"],
        match["player2_id"], match["player2_name"],
        match["game"],
        winner_id,
    )

    forfeit_text = (
        f"❌ Match Forfeited\n\n"
        f"@{loser_name} took too long.\n"
        f"🏆 @{winner_name} wins by forfeit!"
    )

    try:
        await bot.edit_message_text(
            chat_id=match["group_id"],
            message_id=match["message_id"],
            text=forfeit_text,
            reply_markup=rematch_keyboard(
                match["player1_id"], match["player2_id"], match["game"], match["group_id"]
            ),
        )
    except Exception:
        try:
            await bot.send_message(chat_id=match["group_id"], text=forfeit_text)
        except Exception:
            pass

    await _handle_tournament_result(match, winner_id, bot)


async def _finish_match(match: dict, winner_id, winner_name, is_draw: bool, bot: Bot, reason: str = ""):
    db = get_db()
    timeout_manager.cancel_all_for_match(match["match_id"])

    if is_draw:
        result_text = _build_result_text(match, None, None, is_draw, reason)
    else:
        result_text = _build_result_text(match, winner_id, winner_name, False, reason)

    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {
            "$set": {
                "status": "finished",
                "winner_id": winner_id,
                "is_draw": is_draw,
                "finished_at": now_utc(),
            }
        },
    )

    await record_match_result(
        match["player1_id"], match["player1_name"],
        match["player2_id"], match["player2_name"],
        match["game"],
        winner_id,
        is_draw,
    )

    try:
        await bot.edit_message_text(
            chat_id=match["group_id"],
            message_id=match["message_id"],
            text=result_text,
            reply_markup=rematch_keyboard(
                match["player1_id"], match["player2_id"], match["game"], match["group_id"]
            ),
            parse_mode="HTML",
        )
    except Exception:
        try:
            await bot.send_message(
                chat_id=match["group_id"],
                text=result_text,
                reply_markup=rematch_keyboard(
                    match["player1_id"], match["player2_id"], match["game"], match["group_id"]
                ),
            )
        except Exception as e:
            logger.error(f"Failed to send result: {e}")

    await _handle_tournament_result(match, winner_id, bot)


def _build_result_text(match: dict, winner_id, winner_name, is_draw: bool, reason: str = "") -> str:
    game = match["game"]
    if game in NATIVE_DICE_GAMES:
        return dice_game.render_result(match)
    elif game == "rps":
        return rps_game.render_result(match)
    elif game == "tictactoe":
        return ttt_game.render_result(match)
    elif game == "guess":
        return guess_game.render_result(match)
    elif game == "treasure":
        return treasure_game.render_result(match, reason)
    return f"Match finished. Winner: @{winner_name}" if not is_draw else "Match finished. Draw!"


async def _handle_tournament_result(match: dict, winner_id, bot: Bot):
    if not match.get("tournament_id"):
        return
    from handlers.tournament import on_tournament_match_finished
    await on_tournament_match_finished(
        tournament_id=match["tournament_id"],
        tournament_match_id=match.get("tournament_match_id"),
        winner_id=winner_id,
        bot=bot,
    )


@router.callback_query(F.data.startswith("roll:"))
async def cb_roll(callback: CallbackQuery):
    db = get_db()
    match_id = callback.data.split(":")[1]
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or already finished.", show_alert=True)
        return

    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    if user.id != match["current_turn"]:
        await callback.answer("❌ It's not your turn!", show_alert=True)
        return

    game = match["game"]
    state = match["game_state"]
    p1_id = match["player1_id"]

    if user.id == p1_id and state.get("player1_rolled"):
        await callback.answer("❌ You already rolled.", show_alert=True)
        return
    if user.id == match["player2_id"] and state.get("player2_rolled"):
        await callback.answer("❌ You already rolled.", show_alert=True)
        return

    emoji = DICE_EMOJI_MAP.get(game, "🎲")
    dice_msg = await callback.message.answer_dice(emoji=emoji)
    dice_value = dice_msg.dice.value

    match = dice_game.apply_roll(match, user.id, dice_value)

    await db.matches.update_one(
        {"match_id": match_id},
        {
            "$set": {
                "game_state": match["game_state"],
                "current_turn": match["current_turn"],
                "last_action_at": now_utc(),
                "timeout_warned": False,
            }
        },
    )

    timeout_manager.cancel_all_for_match(match_id)

    if dice_game.is_finished(match):
        winner_id, winner_name, is_draw = dice_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = dice_game.render_board(match)
        try:
            await callback.message.edit_text(
                board_text,
                reply_markup=roll_keyboard(match_id, game),
            )
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("rps:"))
async def cb_rps(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    match_id, choice = parts[1], parts[2]
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or already finished.", show_alert=True)
        return

    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    state = match["game_state"]
    p1_chose = state["player1_choice"]
    p2_chose = state["player2_choice"]

    if user.id == match["player1_id"] and p1_chose:
        await callback.answer("✅ You already chose.", show_alert=True)
        return
    if user.id == match["player2_id"] and p2_chose:
        await callback.answer("✅ You already chose.", show_alert=True)
        return

    match = rps_game.apply_choice(match, user.id, choice)
    await db.matches.update_one(
        {"match_id": match_id},
        {
            "$set": {
                "game_state": match["game_state"],
                "last_action_at": now_utc(),
                "timeout_warned": False,
            }
        },
    )

    timeout_manager.cancel_all_for_match(match_id)

    if rps_game.is_finished(match):
        winner_id, winner_name, is_draw = rps_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = rps_game.render_board(match)
        try:
            await callback.message.edit_text(board_text, reply_markup=rps_keyboard(match_id))
        except Exception:
            pass
        await callback.answer("✅ Choice recorded!", show_alert=False)

    await callback.answer()


@router.callback_query(F.data.startswith("ttt:"))
async def cb_ttt(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    match_id, cell = parts[1], int(parts[2])
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or already finished.", show_alert=True)
        return

    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    if user.id != match["current_turn"]:
        await callback.answer("❌ It's not your turn!", show_alert=True)
        return

    match, valid = ttt_game.apply_move(match, user.id, cell)
    if not valid:
        await callback.answer("❌ Cell already taken!", show_alert=True)
        return

    await db.matches.update_one(
        {"match_id": match_id},
        {
            "$set": {
                "game_state": match["game_state"],
                "current_turn": match["current_turn"],
                "last_action_at": now_utc(),
                "timeout_warned": False,
            }
        },
    )

    timeout_manager.cancel_all_for_match(match_id)
    finished, winner_sym = ttt_game.is_finished(match)

    if finished:
        winner_id, winner_name, is_draw = ttt_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = ttt_game.render_board(match)
        markup = tictactoe_keyboard(match_id, match["game_state"]["board"])
        try:
            await callback.message.edit_text(board_text, reply_markup=markup)
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("ttt_noop:"))
async def cb_ttt_noop(callback: CallbackQuery):
    await callback.answer("❌ Cell already taken!", show_alert=True)


@router.message(F.text.regexp(r"^\d+$"))
async def msg_guess_number(message: Message):
    if message.chat.type == "private":
        return

    db = get_db()
    user_id = message.from_user.id
    guess_val = int(message.text)

    if not (1 <= guess_val <= 100):
        return

    match = await db.matches.find_one(
        {
            "$or": [{"player1_id": user_id}, {"player2_id": user_id}],
            "status": "active",
            "game": "guess",
            "group_id": message.chat.id,
        }
    )
    if not match:
        return

    if match["current_turn"] != user_id:
        return

    match, hint, found = guess_game.apply_guess(match, user_id, guess_val)

    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {
            "$set": {
                "game_state": match["game_state"],
                "current_turn": match["current_turn"],
                "last_action_at": now_utc(),
                "timeout_warned": False,
            }
        },
    )

    timeout_manager.cancel_all_for_match(match["match_id"])

    if found:
        winner_id, winner_name, is_draw = guess_game.get_winner_by_user(match, user_id)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, False, message.bot)
    else:
        _schedule_turn_timeout(match["match_id"], message.bot)
        board_text = guess_game.render_board(match)
        try:
            await message.bot.edit_message_text(
                chat_id=match["group_id"],
                message_id=match["message_id"],
                text=board_text,
            )
        except Exception:
            pass
        await message.reply(hint)


@router.callback_query(F.data.startswith("treasure:"))
async def cb_treasure(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    match_id, cell_idx = parts[1], int(parts[2])
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or already finished.", show_alert=True)
        return

    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    if user.id != match["current_turn"]:
        await callback.answer("❌ It's not your turn!", show_alert=True)
        return

    match, result, finished = treasure_game.apply_reveal(match, user.id, cell_idx)

    if result == "already_revealed":
        await callback.answer("❌ Already revealed!", show_alert=True)
        return

    await db.matches.update_one(
        {"match_id": match_id},
        {
            "$set": {
                "game_state": match["game_state"],
                "current_turn": match["current_turn"],
                "last_action_at": now_utc(),
                "timeout_warned": False,
            }
        },
    )

    timeout_manager.cancel_all_for_match(match_id)

    if finished:
        if result == "bomb":
            winner_id, winner_name, is_draw = treasure_game.get_winner_by_bomb(match, user.id)
            match["winner_id"] = winner_id
            loser_name = (
                match["player1_name"] if user.id == match["player1_id"] else match["player2_name"]
            )
            try:
                await callback.message.edit_text(
                    f"💣 BOOM!\n\n@{loser_name} hit a bomb!\n🏆 @{winner_name} wins!",
                    reply_markup=treasure_keyboard(match_id, match["game_state"]["revealed"]),
                )
            except Exception:
                pass
            await _finish_match(match, winner_id, winner_name, False, callback.message.bot, "bomb")
        else:
            winner_id, winner_name, is_draw = treasure_game.get_winner_by_diamonds(match)
            match["winner_id"] = winner_id
            await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot, "all_revealed")
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = treasure_game.render_board(match)
        markup = treasure_keyboard(match_id, match["game_state"]["revealed"])
        if result == "diamond":
            await callback.answer("💎 Diamond found!", show_alert=False)
        try:
            await callback.message.edit_text(board_text, reply_markup=markup)
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("treasure_noop:"))
async def cb_treasure_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("rematch:"))
async def cb_rematch(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    _, p1_id, p2_id, game, group_id = parts[0], int(parts[1]), int(parts[2]), parts[3], int(parts[4])
    user = callback.from_user

    if user.id not in [p1_id, p2_id]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    active_match = await get_active_match_for_user(p1_id)
    if active_match:
        await callback.answer("❌ A player is already in a match.", show_alert=True)
        return
    active_match = await get_active_match_for_user(p2_id)
    if active_match:
        await callback.answer("❌ A player is already in a match.", show_alert=True)
        return

    p1_user = await db.users.find_one({"user_id": p1_id})
    p2_user = await db.users.find_one({"user_id": p2_id})

    p1_name = p1_user["username"] if p1_user and p1_user.get("username") else (p1_user["first_name"] if p1_user else str(p1_id))
    p2_name = p2_user["username"] if p2_user and p2_user.get("username") else (p2_user["first_name"] if p2_user else str(p2_id))

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("🔄 Starting rematch...")

    await start_match(
        bot=callback.message.bot,
        group_id=group_id,
        player1_id=p1_id,
        player1_name=p1_name,
        player2_id=p2_id,
        player2_name=p2_name,
        game=game,
    )
