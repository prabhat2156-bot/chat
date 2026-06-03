import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message

from database.mongodb import get_db
from database.models import MatchModel, now_utc, new_id
from utils.keyboards import (
    roll_keyboard,
    rps_keyboard,
    tictactoe_keyboard,
    treasure_keyboard,
    post_match_keyboard,
    choose_game_keyboard,
    rematch_accept_keyboard,
    newgame_accept_keyboard,
    cancel_confirm_keyboard,
)
from utils import timeout_manager
from utils.db_helpers import (
    record_match_result,
    get_active_match_for_user_in_group,
    get_or_create_user,
)
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

DICE_ANIM_WAIT = 4  # seconds to wait for dice/dart/ball animation


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called from challenge.py / battle.py / callbacks below
# ─────────────────────────────────────────────────────────────────────────────

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
    trigger_msg_id: int = 0,
    battle_id: str = None,
    battle_round: int = None,
) -> str:
    db = get_db()

    # Build initial game state
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
    else:
        game_state = {}

    match = MatchModel.new(
        player1_id=player1_id,
        player1_name=player1_name,
        player2_id=player2_id,
        player2_name=player2_name,
        game=game,
        group_id=group_id,
        message_id=trigger_msg_id,
        tournament_id=tournament_id,
        tournament_match_id=tournament_match_id,
        battle_id=battle_id,
        battle_round=battle_round,
    )
    match["game_state"] = game_state

    # ── Native dice: sequential turn messages ──
    if game in NATIVE_DICE_GAMES:
        text = _dice_turn_text(
            game, player1_name, player2_name,
            None, None, player1_id, player1_id,
        )
        msg = await bot.send_message(
            chat_id=group_id, text=text, parse_mode="HTML",
            reply_markup=roll_keyboard(match["match_id"], game),
        )
    else:
        board_text, markup = _build_board(match)
        msg = await bot.send_message(
            chat_id=group_id, text=board_text,
            reply_markup=markup, parse_mode="HTML",
        )

    match["message_id"] = msg.message_id
    await db.matches.insert_one(match)
    _schedule_turn_timeout(match["match_id"], bot)
    return match["match_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dice_turn_text(game, p1_name, p2_name, p1_val, p2_val, current_turn_id, player1_id):
    game_title = GAME_NAMES.get(game, game)
    emoji = DICE_EMOJI_MAP.get(game, "🎲")
    p1_status = f"✅ <b>{p1_val}</b>" if p1_val is not None else "⏳ Waiting..."
    p2_status = f"✅ <b>{p2_val}</b>" if p2_val is not None else "⏳ Waiting..."
    current_name = p1_name if current_turn_id == player1_id else p2_name
    return (
        f"{emoji} <b>{game_title} Match</b>\n\n"
        f"👤 @{p1_name}  —  {p1_status}\n"
        f"👤 @{p2_name}  —  {p2_status}\n\n"
        f"🎯 <b>@{current_name}</b>, your turn! Press Roll ⬇️"
    )


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
        markup = tictactoe_keyboard(match["match_id"], match["game_state"]["board"])
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


def _schedule_turn_timeout(match_id: str, bot: Bot):
    timeout_manager.cancel_all_for_match(match_id)
    timeout_manager.set_timeout(
        f"turn_warn_{match_id}", TURN_TIMEOUT,
        _turn_timeout_warn, match_id, bot,
    )


async def _turn_timeout_warn(match_id: str, bot: Bot):
    db = get_db()
    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        return
    current_id = match["current_turn"]
    current_name = match["player1_name"] if current_id == match["player1_id"] else match["player2_name"]
    await db.matches.update_one({"match_id": match_id}, {"$set": {"timeout_warned": True}})
    try:
        await bot.send_message(
            chat_id=match["group_id"],
            text=f"⚠️ <b>@{current_name}</b>, you have 60 more seconds or you forfeit!",
            parse_mode="HTML",
        )
    except Exception:
        pass
    timeout_manager.set_timeout(
        f"turn_forfeit_{match_id}", TURN_WARNING_TIMEOUT,
        _turn_forfeit, match_id, bot,
    )


async def _turn_forfeit(match_id: str, bot: Bot):
    db = get_db()
    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        return
    current_id = match["current_turn"]
    loser_name  = match["player1_name"] if current_id == match["player1_id"] else match["player2_name"]
    winner_id   = match["player2_id"] if current_id == match["player1_id"] else match["player1_id"]
    winner_name = match["player2_name"] if current_id == match["player1_id"] else match["player1_name"]
    await _end_match_forfeit(match, winner_id, winner_name, loser_name, "timeout", bot)


async def _end_match_forfeit(match, winner_id, winner_name, loser_name, reason_key, bot):
    db = get_db()
    timeout_manager.cancel_all_for_match(match["match_id"])

    reason_texts = {
        "timeout": f"⏰ <b>@{loser_name}</b> took too long!",
        "forfeit": f"🏳️ <b>@{loser_name}</b> forfeited!",
    }
    reason_text = reason_texts.get(reason_key, "")

    # Battle rounds never show rematch/newgame buttons
    is_battle_round = bool(match.get("battle_id"))

    text = (
        f"❌ <b>Match Forfeited</b>\n\n"
        f"{reason_text}\n"
        f"🏆 <b>@{winner_name} wins!</b>"
    )
    markup = None if is_battle_round else post_match_keyboard(
        match["player1_id"], match["player2_id"], match["game"], match["group_id"]
    )

    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {"$set": {
            "status": "finished", "winner_id": winner_id,
            "forfeit": True, "finished_at": now_utc(),
        }},
    )
    await record_match_result(
        match["player1_id"], match["player1_name"],
        match["player2_id"], match["player2_name"],
        match["game"], winner_id,
    )

    # Always send as NEW message for clarity
    try:
        await bot.edit_message_reply_markup(
            chat_id=match["group_id"], message_id=match["message_id"], reply_markup=None,
        )
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=match["group_id"], text=text, reply_markup=markup, parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Could not send forfeit message: {e}")

    if is_battle_round:
        await _handle_battle_result(match, winner_id, False, bot)
    else:
        await _handle_tournament_result(match, winner_id, bot)


async def _finish_match(
    match: dict, winner_id, winner_name, is_draw: bool,
    bot: Bot, reason: str = "",
    send_new_message: bool = False,
):
    """
    Finalize a match.
    For battle rounds, always sends a new message (no rematch buttons).
    For regular matches, always sends a new message too (user request).
    """
    db = get_db()
    timeout_manager.cancel_all_for_match(match["match_id"])

    is_battle_round = bool(match.get("battle_id"))

    text   = _result_text(match, winner_id, winner_name, is_draw, reason)
    # Battle rounds: no post-match buttons (next-round handled separately)
    markup = None if is_battle_round else post_match_keyboard(
        match["player1_id"], match["player2_id"], match["game"], match["group_id"]
    )

    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {"$set": {
            "status": "finished", "winner_id": winner_id,
            "is_draw": is_draw, "finished_at": now_utc(),
        }},
    )
    await record_match_result(
        match["player1_id"], match["player1_name"],
        match["player2_id"], match["player2_name"],
        match["game"], winner_id, is_draw,
    )

    # Always clear old keyboard and send a fresh result message
    try:
        await bot.edit_message_reply_markup(
            chat_id=match["group_id"], message_id=match["message_id"], reply_markup=None,
        )
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=match["group_id"], text=text, reply_markup=markup, parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to send result: {e}")

    if is_battle_round:
        await _handle_battle_result(match, winner_id, is_draw, bot)
    else:
        await _handle_tournament_result(match, winner_id, bot)


def _result_text(match, winner_id, winner_name, is_draw, reason=""):
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
    if is_draw:
        return "🤝 <b>It's a Draw!</b>"
    return f"🏆 <b>@{winner_name} wins!</b>"


async def _handle_tournament_result(match: dict, winner_id, bot: Bot):
    if not match.get("tournament_id"):
        return
    try:
        from handlers.tournament import on_tournament_match_finished
        await on_tournament_match_finished(
            tournament_id=match["tournament_id"],
            tournament_match_id=match.get("tournament_match_id"),
            winner_id=winner_id,
            bot=bot,
        )
    except Exception as e:
        logger.error(f"Tournament result error: {e}")


async def _handle_battle_result(match: dict, winner_id, is_draw: bool, bot: Bot):
    """Called after every battle-round match finishes."""
    if not match.get("battle_id"):
        return
    try:
        from handlers.battle import on_battle_round_finished
        await on_battle_round_finished(
            battle_id=match["battle_id"],
            match_id=match["match_id"],
            winner_id=winner_id,
            is_draw=is_draw,
            bot=bot,
        )
    except Exception as e:
        logger.error(f"Battle round result error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CANCEL / FORFEIT
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cancel_match:"))
async def cb_cancel_match(callback: CallbackQuery):
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

    try:
        await callback.message.edit_reply_markup(reply_markup=cancel_confirm_keyboard(match_id))
    except Exception:
        pass
    await callback.answer("⚠️ Confirm forfeit?", show_alert=False)


@router.callback_query(F.data.startswith("cancel_abort:"))
async def cb_cancel_abort(callback: CallbackQuery):
    db = get_db()
    match_id = callback.data.split(":")[1]
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found.", show_alert=True)
        return
    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    _, markup = _build_board(match)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass
    await callback.answer("✅ Continuing the match!")


@router.callback_query(F.data.startswith("cancel_confirm:"))
async def cb_cancel_confirm(callback: CallbackQuery):
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

    loser_name  = match["player1_name"] if user.id == match["player1_id"] else match["player2_name"]
    winner_id   = match["player2_id"] if user.id == match["player1_id"] else match["player1_id"]
    winner_name = match["player2_name"] if user.id == match["player1_id"] else match["player1_name"]

    await callback.answer("🏳️ Forfeited.")
    await _end_match_forfeit(match, winner_id, winner_name, loser_name, "forfeit", callback.message.bot)


# ─────────────────────────────────────────────────────────────────────────────
# NATIVE DICE ROLL
# ─────────────────────────────────────────────────────────────────────────────

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

    state = match["game_state"]
    if user.id == match["player1_id"] and state.get("player1_rolled"):
        await callback.answer("❌ You already rolled.", show_alert=True)
        return
    if user.id == match["player2_id"] and state.get("player2_rolled"):
        await callback.answer("❌ You already rolled.", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()

    game  = match["game"]
    emoji = DICE_EMOJI_MAP.get(game, "🎲")

    dice_msg    = await callback.message.answer_dice(emoji=emoji)
    dice_value  = dice_msg.dice.value
    await asyncio.sleep(DICE_ANIM_WAIT)

    match = dice_game.apply_roll(match, user.id, dice_value)
    await db.matches.update_one(
        {"match_id": match_id},
        {"$set": {
            "game_state": match["game_state"],
            "current_turn": match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match_id)

    state    = match["game_state"]
    p1_name  = match["player1_name"]
    p2_name  = match["player2_name"]
    p1_id    = match["player1_id"]

    if dice_game.is_finished(match):
        winner_id, winner_name, is_draw = dice_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(
            match, winner_id, winner_name, is_draw,
            callback.message.bot, send_new_message=True,
        )
    else:
        p1_val   = state["player1_value"] if state["player1_rolled"] else None
        p2_val   = state["player2_value"] if state["player2_rolled"] else None
        next_turn = match["current_turn"]

        turn_text = _dice_turn_text(game, p1_name, p2_name, p1_val, p2_val, next_turn, p1_id)
        new_msg   = await callback.message.bot.send_message(
            chat_id=match["group_id"],
            text=turn_text, parse_mode="HTML",
            reply_markup=roll_keyboard(match_id, game),
        )
        await db.matches.update_one({"match_id": match_id}, {"$set": {"message_id": new_msg.message_id}})
        _schedule_turn_timeout(match_id, callback.message.bot)


# ─────────────────────────────────────────────────────────────────────────────
# RPS
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rps:"))
async def cb_rps(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    match_id, choice = parts[1], parts[2]
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or finished.", show_alert=True)
        return
    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    state = match["game_state"]
    if user.id == match["player1_id"] and state["player1_choice"]:
        await callback.answer("✅ Already chosen! Waiting for opponent.", show_alert=False)
        return
    if user.id == match["player2_id"] and state["player2_choice"]:
        await callback.answer("✅ Already chosen! Waiting for opponent.", show_alert=False)
        return

    match = rps_game.apply_choice(match, user.id, choice)
    await db.matches.update_one(
        {"match_id": match_id},
        {"$set": {"game_state": match["game_state"], "last_action_at": now_utc(), "timeout_warned": False}},
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
            await callback.message.edit_text(board_text, reply_markup=rps_keyboard(match_id), parse_mode="HTML")
        except Exception:
            pass
        await callback.answer("✅ Choice recorded! Waiting for opponent.")
        return

    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# TIC TAC TOE
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ttt:"))
async def cb_ttt(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    match_id, cell = parts[1], int(parts[2])
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or finished.", show_alert=True)
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
        {"$set": {
            "game_state": match["game_state"],
            "current_turn": match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match_id)

    finished, _ = ttt_game.is_finished(match)
    if finished:
        winner_id, winner_name, is_draw = ttt_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = ttt_game.render_board(match)
        markup = tictactoe_keyboard(match_id, match["game_state"]["board"])
        try:
            await callback.message.edit_text(board_text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("ttt_noop:"))
async def cb_ttt_noop(callback: CallbackQuery):
    await callback.answer("❌ Already taken!", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
# GUESS NUMBER
# ─────────────────────────────────────────────────────────────────────────────

@router.message(F.text.regexp(r"^\d+$"))
async def msg_guess_number(message: Message):
    if message.chat.type == "private":
        return

    db = get_db()
    user_id   = message.from_user.id
    guess_val = int(message.text)
    if not (1 <= guess_val <= 100):
        return

    match = await db.matches.find_one({
        "$or": [{"player1_id": user_id}, {"player2_id": user_id}],
        "status": "active",
        "game": "guess",
        "group_id": message.chat.id,
    })
    if not match or match["current_turn"] != user_id:
        return

    match, hint, found = guess_game.apply_guess(match, user_id, guess_val)
    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {"$set": {
            "game_state": match["game_state"],
            "current_turn": match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
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
                text=board_text, parse_mode="HTML",
            )
        except Exception:
            pass
        await message.reply(f"<b>{hint}</b>", parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# TREASURE HUNT
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("treasure:"))
async def cb_treasure(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    match_id, cell_idx = parts[1], int(parts[2])
    user = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or finished.", show_alert=True)
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
        {"$set": {
            "game_state": match["game_state"],
            "current_turn": match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match_id)

    if finished:
        if result == "bomb":
            winner_id, winner_name, _ = treasure_game.get_winner_by_bomb(match, user.id)
            loser_name = match["player1_name"] if user.id == match["player1_id"] else match["player2_name"]
            match["winner_id"] = winner_id
            try:
                await callback.message.edit_text(
                    f"💣 <b>BOOM!</b>\n\n@{loser_name} hit a bomb!\n⏳ Calculating result...",
                    reply_markup=treasure_keyboard(match_id, match["game_state"]["revealed"]),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await asyncio.sleep(1)
            await _finish_match(match, winner_id, winner_name, False, callback.message.bot,
                                reason="bomb", send_new_message=True)
        else:
            winner_id, winner_name, is_draw = treasure_game.get_winner_by_diamonds(match)
            match["winner_id"] = winner_id
            await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot,
                                reason="all_revealed", send_new_message=True)
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = treasure_game.render_board(match)
        markup = treasure_keyboard(match_id, match["game_state"]["revealed"])
        if result == "diamond":
            await callback.answer("💎 Diamond found!", show_alert=False)
        try:
            await callback.message.edit_text(board_text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("treasure_noop:"))
async def cb_treasure_noop(callback: CallbackQuery):
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# REMATCH — requires opponent acceptance
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rematch_req:"))
async def cb_rematch_req(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    p1_id, p2_id, game, group_id = int(parts[1]), int(parts[2]), parts[3], int(parts[4])
    user = callback.from_user

    if user.id not in [p1_id, p2_id]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    requester_name = user.username or user.first_name
    opponent_id    = p2_id if user.id == p1_id else p1_id

    active = await get_active_match_for_user_in_group(p1_id, group_id)
    if not active:
        active = await get_active_match_for_user_in_group(p2_id, group_id)
    if active:
        await callback.answer("❌ A player is already in a match.", show_alert=True)
        return

    req_id    = new_id()
    game_name = GAME_NAMES.get(game, game)

    opp_doc  = await db.users.find_one({"user_id": opponent_id})
    opp_name = (opp_doc.get("username") or opp_doc.get("first_name") or str(opponent_id)) if opp_doc else str(opponent_id)

    await db.rematch_requests.insert_one({
        "req_id": req_id,
        "requester_id": user.id,
        "requester_name": requester_name,
        "opponent_id": opponent_id,
        "opponent_name": opp_name,
        "player1_id": p1_id,
        "player2_id": p2_id,
        "game": game,
        "group_id": group_id,
        "status": "pending",
        "created_at": now_utc(),
    })

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.bot.send_message(
        chat_id=group_id,
        text=(
            f"🔄 <b>Rematch Request</b>\n\n"
            f"👤 @{requester_name} wants a rematch!\n"
            f"🎮 <b>Game:</b> {game_name}\n\n"
            f"<i>@{opp_name}, do you accept?</i>"
        ),
        parse_mode="HTML",
        reply_markup=rematch_accept_keyboard(req_id),
    )
    await callback.answer("🔄 Rematch request sent!")


@router.callback_query(F.data.startswith("rematch_accept:"))
async def cb_rematch_accept(callback: CallbackQuery):
    db = get_db()
    req_id = callback.data.split(":")[1]
    user   = callback.from_user

    req = await db.rematch_requests.find_one({"req_id": req_id, "status": "pending"})
    if not req:
        await callback.answer("❌ Request expired or not found.", show_alert=True)
        return
    if user.id != req["opponent_id"]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    active = await get_active_match_for_user_in_group(req["player1_id"], req["group_id"])
    if not active:
        active = await get_active_match_for_user_in_group(req["player2_id"], req["group_id"])
    if active:
        await callback.answer("❌ A player is already in a match.", show_alert=True)
        return

    await db.rematch_requests.update_one({"req_id": req_id}, {"$set": {"status": "accepted"}})

    try:
        await callback.message.edit_text("✅ <b>Rematch accepted!</b> Starting...", parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
    await callback.answer("✅ Rematch started!")

    p1_doc = await db.users.find_one({"user_id": req["player1_id"]})
    p2_doc = await db.users.find_one({"user_id": req["player2_id"]})
    p1_name = (p1_doc.get("username") or p1_doc.get("first_name") or str(req["player1_id"])) if p1_doc else req.get("requester_name", str(req["player1_id"]))
    p2_name = (p2_doc.get("username") or p2_doc.get("first_name") or str(req["player2_id"])) if p2_doc else req.get("opponent_name", str(req["player2_id"]))

    await start_match(
        bot=callback.message.bot, group_id=req["group_id"],
        player1_id=req["player1_id"], player1_name=p1_name,
        player2_id=req["player2_id"], player2_name=p2_name,
        game=req["game"],
    )


@router.callback_query(F.data.startswith("rematch_decline:"))
async def cb_rematch_decline(callback: CallbackQuery):
    db = get_db()
    req_id = callback.data.split(":")[1]
    user   = callback.from_user

    req = await db.rematch_requests.find_one({"req_id": req_id, "status": "pending"})
    if not req:
        await callback.answer("❌ Request not found.", show_alert=True)
        return
    if user.id != req["opponent_id"]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    await db.rematch_requests.update_one({"req_id": req_id}, {"$set": {"status": "declined"}})
    try:
        await callback.message.edit_text("❌ <b>Rematch Declined</b>", parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
    await callback.answer("❌ Declined")


# ─────────────────────────────────────────────────────────────────────────────
# CHOOSE ANOTHER GAME
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("choose_game:"))
async def cb_choose_game(callback: CallbackQuery):
    parts = callback.data.split(":")
    p1_id, p2_id, group_id = int(parts[1]), int(parts[2]), int(parts[3])
    user = callback.from_user

    if user.id not in [p1_id, p2_id]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=choose_game_keyboard(p1_id, p2_id, group_id))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("newgame_req:"))
async def cb_newgame_req(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    p1_id, p2_id, group_id, game = int(parts[1]), int(parts[2]), int(parts[3]), parts[4]
    user = callback.from_user

    if user.id not in [p1_id, p2_id]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    requester_name = user.username or user.first_name
    opponent_id    = p2_id if user.id == p1_id else p1_id

    active = await get_active_match_for_user_in_group(p1_id, group_id)
    if not active:
        active = await get_active_match_for_user_in_group(p2_id, group_id)
    if active:
        await callback.answer("❌ A player is already in a match.", show_alert=True)
        return

    req_id    = new_id()
    game_name = GAME_NAMES.get(game, game)
    opp_doc   = await db.users.find_one({"user_id": opponent_id})
    opp_name  = (opp_doc.get("username") or opp_doc.get("first_name") or str(opponent_id)) if opp_doc else str(opponent_id)

    await db.newgame_requests.insert_one({
        "req_id": req_id,
        "requester_id": user.id,
        "requester_name": requester_name,
        "opponent_id": opponent_id,
        "opponent_name": opp_name,
        "player1_id": p1_id,
        "player2_id": p2_id,
        "game": game,
        "group_id": group_id,
        "status": "pending",
        "created_at": now_utc(),
    })

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.bot.send_message(
        chat_id=group_id,
        text=(
            f"🎮 <b>New Game Request</b>\n\n"
            f"👤 @{requester_name} wants to play <b>{game_name}</b>!\n\n"
            f"<i>@{opp_name}, do you accept?</i>"
        ),
        parse_mode="HTML",
        reply_markup=newgame_accept_keyboard(req_id),
    )
    await callback.answer(f"🎮 Request sent!")


@router.callback_query(F.data.startswith("newgame_accept:"))
async def cb_newgame_accept(callback: CallbackQuery):
    db = get_db()
    req_id = callback.data.split(":")[1]
    user   = callback.from_user

    req = await db.newgame_requests.find_one({"req_id": req_id, "status": "pending"})
    if not req:
        await callback.answer("❌ Request expired or not found.", show_alert=True)
        return
    if user.id != req["opponent_id"]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    active = await get_active_match_for_user_in_group(req["player1_id"], req["group_id"])
    if not active:
        active = await get_active_match_for_user_in_group(req["player2_id"], req["group_id"])
    if active:
        await callback.answer("❌ A player is already in a match.", show_alert=True)
        return

    await db.newgame_requests.update_one({"req_id": req_id}, {"$set": {"status": "accepted"}})
    game_name = GAME_NAMES.get(req["game"], req["game"])

    try:
        await callback.message.edit_text(
            f"✅ <b>@{req['opponent_name']} accepted!</b>\n🎮 Starting <b>{game_name}</b>...",
            parse_mode="HTML", reply_markup=None,
        )
    except Exception:
        pass
    await callback.answer(f"✅ Starting {game_name}!")

    p1_doc = await db.users.find_one({"user_id": req["player1_id"]})
    p2_doc = await db.users.find_one({"user_id": req["player2_id"]})
    p1_name = (p1_doc.get("username") or p1_doc.get("first_name") or str(req["player1_id"])) if p1_doc else req.get("requester_name", str(req["player1_id"]))
    p2_name = (p2_doc.get("username") or p2_doc.get("first_name") or str(req["player2_id"])) if p2_doc else req.get("opponent_name", str(req["player2_id"]))

    await start_match(
        bot=callback.message.bot, group_id=req["group_id"],
        player1_id=req["player1_id"], player1_name=p1_name,
        player2_id=req["player2_id"], player2_name=p2_name,
        game=req["game"],
    )


@router.callback_query(F.data.startswith("newgame_decline:"))
async def cb_newgame_decline(callback: CallbackQuery):
    db = get_db()
    req_id = callback.data.split(":")[1]
    user   = callback.from_user

    req = await db.newgame_requests.find_one({"req_id": req_id, "status": "pending"})
    if not req:
        await callback.answer("❌ Request not found.", show_alert=True)
        return
    if user.id != req["opponent_id"]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    await db.newgame_requests.update_one({"req_id": req_id}, {"$set": {"status": "declined"}})
    try:
        await callback.message.edit_text("❌ <b>Game Request Declined</b>", parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
    await callback.answer("❌ Declined")
