"""
Match Handler — FIXED VERSION

Fixes applied:
1. Battle rounds: result → 5-sec countdown → delete game msg → next round starts
2. Challenge: cleanup accepted/confirmation messages when match starts
3. Timeout: @mention warning message (separate), 1 min then auto-cancel
4. Dice animation deleted after every roll (including after match ends)
5. "Leave Match" replaces "Cancel/Forfeit Match" everywhere
6. Battle round game boards have no Match ID (clutter-free)
7. on_battle_round_finished called with correct signature (battle_id, match_id, winner_id, is_draw, bot)
"""
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
    leave_confirm_keyboard,
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
    cleanup_msg_ids: list = None,   # message IDs to delete when match starts
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

    short_id  = match["match_id"][:8].upper()
    is_battle = bool(battle_id)

    # Send game board
    if game in NATIVE_DICE_GAMES:
        board_text = _dice_turn_text(
            game, player1_name, player2_name,
            None, None, player1_id, player1_id,
        )
        if not is_battle:
            board_text += f"\n\n🆔 <code>Match {short_id}</code>"
        msg = await bot.send_message(
            chat_id      = group_id,
            text         = board_text,
            parse_mode   = "HTML",
            reply_markup = roll_keyboard(match["match_id"], game, is_battle),
        )
    else:
        board_text, markup = _build_board(match, is_battle)
        if not is_battle:
            board_text += f"\n\n🆔 <code>Match {short_id}</code>"
        msg = await bot.send_message(
            chat_id      = group_id,
            text         = board_text,
            reply_markup = markup,
            parse_mode   = "HTML",
        )

    match["message_id"] = msg.message_id
    await db.matches.insert_one(match)
    _schedule_turn_timeout(match["match_id"], bot)

    # Delete cleanup messages (challenge accept/confirmation messages)
    if cleanup_msg_ids:
        for mid in cleanup_msg_ids:
            if mid:
                try:
                    await bot.delete_message(group_id, mid)
                except Exception:
                    pass

    return match["match_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dice_turn_text(game, p1_name, p2_name, p1_val, p2_val, current_turn_id, player1_id):
    game_title   = GAME_NAMES.get(game, game)
    emoji        = DICE_EMOJI_MAP.get(game, "🎲")
    p1_status    = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>{p1_val}</b>" if p1_val is not None else "⏳ Waiting…"
    p2_status    = f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>{p2_val}</b>" if p2_val is not None else "⏳ Waiting…"
    current_name = p1_name if current_turn_id == player1_id else p2_name
    return (
        f"{emoji} <b>{game_title} Match</b>\n\n"
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p1_name}  —  {p1_status}\n"
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> @{p2_name}  —  {p2_status}\n\n"
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>@{current_name}</b>, your turn! Press Roll ⬇️"
    )


def _build_board(match: dict, is_battle: bool = False):
    game    = match["game"]
    mid     = match["match_id"]
    if game in NATIVE_DICE_GAMES:
        text   = dice_game.render_board(match)
        markup = roll_keyboard(mid, game, is_battle)
    elif game == "rps":
        text   = rps_game.render_board(match)
        markup = rps_keyboard(mid, is_battle)
    elif game == "tictactoe":
        text   = ttt_game.render_board(match)
        markup = tictactoe_keyboard(mid, match["game_state"]["board"], is_battle)
    elif game == "guess":
        text   = guess_game.render_board(match)
        markup = None
    elif game == "treasure":
        text   = treasure_game.render_board(match)
        markup = treasure_keyboard(mid, match["game_state"]["revealed"], is_battle)
    else:
        text   = "Match started."
        markup = None
    return text, markup


def _schedule_turn_timeout(match_id: str, bot: Bot):
    timeout_manager.cancel_all_for_match(match_id)
    timeout_manager.set_timeout(
        f"turn_warn_{match_id}", TURN_TIMEOUT,
        _turn_timeout_warn, match_id, bot,
    )


async def _turn_timeout_warn(match_id: str, bot: Bot):
    db    = get_db()
    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        return

    current_id   = match["current_turn"]
    current_name = match["player1_name"] if current_id == match["player1_id"] else match["player2_name"]
    await db.matches.update_one({"match_id": match_id}, {"$set": {"timeout_warned": True}})

    # Send @mention warning as a NEW separate message (visible to both players)
    try:
        warn_msg = await bot.send_message(
            chat_id    = match["group_id"],
            text       = (
                f"⏰ <b>@{current_name}</b> — it's your turn!\n\n"
                f"You have <b>60 seconds</b> to respond or the match will be cancelled.\n"
                f"🆔 <code>Match {match_id[:8].upper()}</code>"
            ),
            parse_mode = "HTML",
        )
        await db.matches.update_one(
            {"match_id": match_id},
            {"$set": {"timeout_warn_msg_id": warn_msg.message_id}},
        )
    except Exception:
        pass

    timeout_manager.set_timeout(
        f"turn_forfeit_{match_id}", TURN_WARNING_TIMEOUT,
        _turn_forfeit, match_id, bot,
    )


async def _turn_forfeit(match_id: str, bot: Bot):
    db    = get_db()
    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        return

    # Delete the timeout warning message
    warn_msg_id = match.get("timeout_warn_msg_id")
    if warn_msg_id:
        try:
            await bot.delete_message(match["group_id"], warn_msg_id)
        except Exception:
            pass

    current_id  = match["current_turn"]
    loser_name  = match["player1_name"] if current_id == match["player1_id"] else match["player2_name"]
    winner_id   = match["player2_id"]   if current_id == match["player1_id"] else match["player1_id"]
    winner_name = match["player2_name"] if current_id == match["player1_id"] else match["player1_name"]
    await _end_match_forfeit(match, winner_id, winner_name, loser_name, "timeout", bot)


async def _end_match_forfeit(match, winner_id, winner_name, loser_name, reason_key, bot):
    db = get_db()
    timeout_manager.cancel_all_for_match(match["match_id"])

    reason_texts = {
        "timeout": f"⏰ <b>@{loser_name}</b> ran out of time!",
        "forfeit": f"<tg-emoji emoji-id='6082411364653993798'>🏳</tg-emoji>️ <b>@{loser_name}</b> left the match.",
    }
    reason_text     = reason_texts.get(reason_key, "")
    is_battle_round = bool(match.get("battle_id"))
    short_id        = match["match_id"][:8].upper()
    game_name       = GAME_NAMES.get(match["game"], match["game"])

    text = (
        f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji>  <b>Match Cancelled</b>  ·  {game_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{reason_text}\n\n"
        f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>@{winner_name} wins!</b>"
    )
    if not is_battle_round:
        text += f"\n\n🆔 <code>Match {short_id}</code>"

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

    if is_battle_round:
        # Delete game board, then pass result to battle handler
        try:
            await bot.delete_message(match["group_id"], match["message_id"])
        except Exception:
            pass
        await _handle_battle_result(match, winner_id, False, bot)
    else:
        edited = False
        try:
            await bot.edit_message_text(
                chat_id=match["group_id"], message_id=match["message_id"],
                text=text, reply_markup=markup, parse_mode="HTML",
            )
            edited = True
        except Exception:
            pass
        if not edited:
            try:
                await bot.send_message(
                    chat_id=match["group_id"], text=text, reply_markup=markup, parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Could not send forfeit message: {e}")
        await _handle_tournament_result(match, winner_id, bot)


async def _finish_match(
    match: dict,
    winner_id,
    winner_name,
    is_draw: bool,
    bot: Bot,
    reason: str = "",
    send_new_message: bool = False,
):
    """
    Finalize a match.

    For battle rounds:
      - Show result in game board
      - 5-second countdown
      - Delete the game board message
      - Call battle handler to update live card and start next round

    For free matches:
      - Edit game board in-place with result + rematch buttons
    """
    db = get_db()
    timeout_manager.cancel_all_for_match(match["match_id"])

    is_battle_round = bool(match.get("battle_id"))
    short_id        = match["match_id"][:8].upper()

    base_text   = _result_text(match, winner_id, winner_name, is_draw, reason)
    result_text = base_text if is_battle_round else (base_text + f"\n\n🆔 <code>Match {short_id}</code>")

    markup = None if is_battle_round else post_match_keyboard(
        match["player1_id"], match["player2_id"], match["game"], match["group_id"]
    )

    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {"$set": {
            "status":      "finished",
            "winner_id":   winner_id,
            "is_draw":     is_draw,
            "finished_at": now_utc(),
        }},
    )
    await record_match_result(
        match["player1_id"], match["player1_name"],
        match["player2_id"], match["player2_name"],
        match["game"], winner_id, is_draw,
    )

    # ── Delete all stored dice animations ──
    for dmid in match.get("dice_msg_ids", []):
        try:
            await bot.delete_message(match["group_id"], dmid)
        except Exception:
            pass

    if is_battle_round:
        # ── Step 1: Show result on game board ──
        game_msg_id = match.get("message_id")
        if game_msg_id:
            try:
                await bot.edit_message_text(
                    chat_id      = match["group_id"],
                    message_id   = game_msg_id,
                    text         = result_text,
                    reply_markup = None,
                    parse_mode   = "HTML",
                )
            except Exception:
                # If edit fails, send new result message temporarily
                try:
                    tmp = await bot.send_message(
                        chat_id    = match["group_id"],
                        text       = result_text,
                        parse_mode = "HTML",
                    )
                    game_msg_id = tmp.message_id
                    await db.matches.update_one(
                        {"match_id": match["match_id"]},
                        {"$set": {"message_id": game_msg_id}},
                    )
                except Exception:
                    game_msg_id = None

        # ── Step 2: 5-second countdown ──
        for remaining in range(5, 0, -1):
            await asyncio.sleep(1)
            if game_msg_id:
                try:
                    await bot.edit_message_text(
                        chat_id      = match["group_id"],
                        message_id   = game_msg_id,
                        text         = result_text + f"\n\n<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> <b>Next round in {remaining}…</b>",
                        parse_mode   = "HTML",
                    )
                except Exception:
                    pass

        # ── Step 3: Delete game board message ──
        if game_msg_id:
            try:
                await bot.delete_message(match["group_id"], game_msg_id)
            except Exception:
                pass

        # ── Step 4: Tell battle handler → update live card + start next round ──
        await _handle_battle_result(match, winner_id, is_draw, bot)

    else:
        # ── FREE MATCH: edit game board in-place with result ──
        edited = False
        if not send_new_message:
            try:
                await bot.edit_message_text(
                    chat_id      = match["group_id"],
                    message_id   = match["message_id"],
                    text         = result_text,
                    reply_markup = markup,
                    parse_mode   = "HTML",
                )
                edited = True
            except Exception:
                pass
        if not edited:
            try:
                await bot.edit_message_reply_markup(
                    chat_id      = match["group_id"],
                    message_id   = match["message_id"],
                    reply_markup = None,
                )
            except Exception:
                pass
            try:
                await bot.send_message(
                    chat_id      = match["group_id"],
                    text         = result_text,
                    reply_markup = markup,
                    parse_mode   = "HTML",
                )
            except Exception as e:
                logger.error(f"Failed to send result: {e}")

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
        return "<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>It's a Draw!</b>"
    return f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>@{winner_name} wins!</b>"


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
    """Called after every battle-round match finishes — passes result to battle.py."""
    if not match.get("battle_id"):
        return
    try:
        from handlers.battle import on_battle_round_finished
        await on_battle_round_finished(
            battle_id = match["battle_id"],
            match_id  = match["match_id"],
            winner_id = winner_id,
            is_draw   = is_draw,
            bot       = bot,
        )
    except Exception as e:
        logger.error(f"Battle round result error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# LEAVE MATCH (replaces "Cancel Match" / "Forfeit Match")
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("leave_match:"))
async def cb_leave_match(callback: CallbackQuery):
    db       = get_db()
    match_id = callback.data.split(":")[1]
    user     = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or already finished.", show_alert=True)
        return
    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    short_id      = match_id[:8].upper()
    leaver_name   = match["player1_name"] if user.id == match["player1_id"] else match["player2_name"]
    opponent_name = match["player2_name"] if user.id == match["player1_id"] else match["player1_name"]

    await db.matches.update_one(
        {"match_id": match_id},
        {"$set": {"leave_requested_by": user.id}},
    )
    await callback.answer("<tg-emoji emoji-id='4956611513369494230'>⚠️</tg-emoji> Leave confirmation sent.")

    await callback.message.bot.send_message(
        chat_id    = match["group_id"],
        text       = (
            f"<tg-emoji emoji-id='4956611513369494230'>⚠️</tg-emoji> <b>@{leaver_name} wants to leave the match!</b>\n\n"
            f"Confirming will <b>forfeit</b> the match — @{opponent_name} wins.\n\n"
            f"🆔 <code>Match {short_id}</code>"
        ),
        reply_markup = leave_confirm_keyboard(match_id),
        parse_mode   = "HTML",
    )


@router.callback_query(F.data.startswith("leave_abort:"))
async def cb_leave_abort(callback: CallbackQuery):
    db       = get_db()
    match_id = callback.data.split(":")[1]
    user     = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found.", show_alert=True)
        return
    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    await db.matches.update_one({"match_id": match_id}, {"$unset": {"leave_requested_by": ""}})
    try:
        await callback.message.edit_text(
            "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Match continues!</b>",
            reply_markup = None,
            parse_mode   = "HTML",
        )
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Continuing!")


@router.callback_query(F.data.startswith("leave_confirm:"))
async def cb_leave_confirm(callback: CallbackQuery):
    db       = get_db()
    match_id = callback.data.split(":")[1]
    user     = callback.from_user

    match = await db.matches.find_one({"match_id": match_id, "status": "active"})
    if not match:
        await callback.answer("❌ Match not found or already finished.", show_alert=True)
        return
    if user.id not in [match["player1_id"], match["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    leave_requester = match.get("leave_requested_by")
    if leave_requester and user.id != leave_requester:
        await callback.answer("❌ Only the player who requested to leave can confirm.", show_alert=True)
        return

    loser_name  = match["player1_name"] if user.id == match["player1_id"] else match["player2_name"]
    winner_id   = match["player2_id"]   if user.id == match["player1_id"] else match["player1_id"]
    winner_name = match["player2_name"] if user.id == match["player1_id"] else match["player1_name"]

    try:
        await callback.message.edit_text(
            f"<tg-emoji emoji-id='6082411364653993798'>🏳</tg-emoji>️ <b>@{loser_name} left the match.</b>\n<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>@{winner_name} wins!</b>",
            reply_markup = None,
            parse_mode   = "HTML",
        )
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Match forfeited.")
    await _end_match_forfeit(match, winner_id, winner_name, loser_name, "forfeit", callback.message.bot)


# ── Backward-compat aliases for old callback_data ──
@router.callback_query(F.data.startswith("cancel_match:"))
async def cb_cancel_match_alias(callback: CallbackQuery):
    match_id     = callback.data.split(":")[1]
    callback.data = f"leave_match:{match_id}"
    await cb_leave_match(callback)

@router.callback_query(F.data.startswith("cancel_confirm:"))
async def cb_cancel_confirm_alias(callback: CallbackQuery):
    match_id     = callback.data.split(":")[1]
    callback.data = f"leave_confirm:{match_id}"
    await cb_leave_confirm(callback)

@router.callback_query(F.data.startswith("cancel_abort:"))
async def cb_cancel_abort_alias(callback: CallbackQuery):
    match_id     = callback.data.split(":")[1]
    callback.data = f"leave_abort:{match_id}"
    await cb_leave_abort(callback)


# ─────────────────────────────────────────────────────────────────────────────
# NATIVE DICE ROLL
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("roll:"))
async def cb_roll(callback: CallbackQuery):
    db       = get_db()
    match_id = callback.data.split(":")[1]
    user     = callback.from_user

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

    # Send dice animation
    dice_msg   = await callback.message.answer_dice(emoji=emoji)
    dice_value = dice_msg.dice.value
    await asyncio.sleep(DICE_ANIM_WAIT)
    # Store dice animation message (deleted together after winner is decided)
    await db.matches.update_one(
        {"match_id": match_id},
        {"$push": {"dice_msg_ids": dice_msg.message_id}},
    )
    # Also update local dict so _finish_match can delete ALL dice messages
    if "dice_msg_ids" not in match:
        match["dice_msg_ids"] = []
    match["dice_msg_ids"].append(dice_msg.message_id)

    match = dice_game.apply_roll(match, user.id, dice_value)
    await db.matches.update_one(
        {"match_id": match_id},
        {"$set": {
            "game_state":     match["game_state"],
            "current_turn":   match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match_id)

    is_battle = bool(match.get("battle_id"))
    state     = match["game_state"]
    p1_name   = match["player1_name"]
    p2_name   = match["player2_name"]
    p1_id     = match["player1_id"]

    if dice_game.is_finished(match):
        winner_id, winner_name, is_draw = dice_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
    else:
        p1_val    = state["player1_value"] if state["player1_rolled"] else None
        p2_val    = state["player2_value"] if state["player2_rolled"] else None
        next_turn = match["current_turn"]
        short_id  = match_id[:8].upper()

        turn_text = _dice_turn_text(game, p1_name, p2_name, p1_val, p2_val, next_turn, p1_id)
        if not is_battle:
            turn_text += f"\n\n🆔 <code>Match {short_id}</code>"

        edited = False
        try:
            await callback.message.bot.edit_message_text(
                chat_id      = match["group_id"],
                message_id   = match["message_id"],
                text         = turn_text,
                parse_mode   = "HTML",
                reply_markup = roll_keyboard(match_id, game, is_battle),
            )
            edited = True
        except Exception:
            pass
        if not edited:
            new_msg = await callback.message.bot.send_message(
                chat_id      = match["group_id"],
                text         = turn_text,
                parse_mode   = "HTML",
                reply_markup = roll_keyboard(match_id, game, is_battle),
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
        await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Already chosen! Waiting for opponent.", show_alert=False)
        return
    if user.id == match["player2_id"] and state["player2_choice"]:
        await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Already chosen! Waiting for opponent.", show_alert=False)
        return

    match = rps_game.apply_choice(match, user.id, choice)
    await db.matches.update_one(
        {"match_id": match_id},
        {"$set": {"game_state": match["game_state"], "last_action_at": now_utc(), "timeout_warned": False}},
    )
    timeout_manager.cancel_all_for_match(match_id)

    is_battle = bool(match.get("battle_id"))

    if rps_game.is_finished(match):
        winner_id, winner_name, is_draw = rps_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
        await callback.answer()
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = rps_game.render_board(match)
        try:
            await callback.message.edit_text(
                board_text,
                reply_markup = rps_keyboard(match_id, is_battle),
                parse_mode   = "HTML",
            )
        except Exception:
            pass
        await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Choice recorded! Waiting for opponent.")


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
            "game_state":     match["game_state"],
            "current_turn":   match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match_id)

    is_battle = bool(match.get("battle_id"))
    finished, _ = ttt_game.is_finished(match)
    if finished:
        winner_id, winner_name, is_draw = ttt_game.get_winner(match)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, is_draw, callback.message.bot)
    else:
        _schedule_turn_timeout(match_id, callback.message.bot)
        board_text = ttt_game.render_board(match)
        markup     = tictactoe_keyboard(match_id, match["game_state"]["board"], is_battle)
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

    db        = get_db()
    user_id   = message.from_user.id
    guess_val = int(message.text)
    if not (1 <= guess_val <= 100):
        return

    match = await db.matches.find_one({
        "$or":      [{"player1_id": user_id}, {"player2_id": user_id}],
        "status":   "active",
        "game":     "guess",
        "group_id": message.chat.id,
    })
    if not match or match["current_turn"] != user_id:
        return

    match, hint, found = guess_game.apply_guess(match, user_id, guess_val)
    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {"$set": {
            "game_state":     match["game_state"],
            "current_turn":   match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match["match_id"])

    if found:
        winner_id, winner_name, _ = guess_game.get_winner_by_user(match, user_id)
        match["winner_id"] = winner_id
        await _finish_match(match, winner_id, winner_name, False, message.bot)
        # Send chat mention to celebrate the winner
        try:
            await message.bot.send_message(
                chat_id    = match["group_id"],
                text       = (
                    f"🎯 @{winner_name} you guessed the right number! "
                    f"You win! 🎉"
                ),
                parse_mode = "HTML",
            )
        except Exception:
            pass
    else:
        _schedule_turn_timeout(match["match_id"], message.bot)
        board_text = guess_game.render_board(match)
        try:
            await message.bot.edit_message_text(
                chat_id    = match["group_id"],
                message_id = match["message_id"],
                text       = board_text,
                parse_mode = "HTML",
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
            "game_state":     match["game_state"],
            "current_turn":   match["current_turn"],
            "last_action_at": now_utc(),
            "timeout_warned": False,
        }},
    )
    timeout_manager.cancel_all_for_match(match_id)

    is_battle = bool(match.get("battle_id"))

    if finished:
        if result == "bomb":
            winner_id, winner_name, _ = treasure_game.get_winner_by_bomb(match, user.id)
            loser_name = match["player1_name"] if user.id == match["player1_id"] else match["player2_name"]
            match["winner_id"] = winner_id
            try:
                await callback.message.edit_text(
                    f"<tg-emoji emoji-id='5280569974404966639'>💣</tg-emoji> <b>BOOM! @{loser_name} hit a bomb!</b>\n⏳ Calculating result…",
                    reply_markup = treasure_keyboard(match_id, match["game_state"]["revealed"], is_battle),
                    parse_mode   = "HTML",
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
        markup     = treasure_keyboard(match_id, match["game_state"]["revealed"], is_battle)
        if result == "diamond":
            await callback.answer("<tg-emoji emoji-id='4956719506027185156'>💎</tg-emoji> Diamond found!", show_alert=False)
        try:
            await callback.message.edit_text(board_text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    await callback.answer()


@router.callback_query(F.data.startswith("treasure_noop:"))
async def cb_treasure_noop(callback: CallbackQuery):
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# REMATCH
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
    opp_doc   = await db.users.find_one({"user_id": opponent_id})
    opp_name  = (opp_doc.get("username") or opp_doc.get("first_name") or str(opponent_id)) if opp_doc else str(opponent_id)

    await db.rematch_requests.insert_one({
        "req_id":         req_id,
        "requester_id":   user.id,
        "requester_name": requester_name,
        "opponent_id":    opponent_id,
        "opponent_name":  opp_name,
        "player1_id":     p1_id,
        "player2_id":     p2_id,
        "game":           game,
        "group_id":       group_id,
        "status":         "pending",
        "created_at":     now_utc(),
    })

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.bot.send_message(
        chat_id    = group_id,
        text       = (
            f"<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> <b>Rematch Request!</b>\n\n"
            f"@{requester_name} wants a rematch in <b>{game_name}</b>!\n\n"
            f"<i>@{opp_name}, do you accept?</i>"
        ),
        parse_mode   = "HTML",
        reply_markup = rematch_accept_keyboard(req_id),
    )
    await callback.answer("<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> Rematch request sent!")


@router.callback_query(F.data.startswith("rematch_accept:"))
async def cb_rematch_accept(callback: CallbackQuery):
    db     = get_db()
    req_id = callback.data.split(":")[1]
    user   = callback.from_user

    req = await db.rematch_requests.find_one({"req_id": req_id, "status": "pending"})
    if not req:
        await callback.answer("❌ Request not found.", show_alert=True)
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
    game_name = GAME_NAMES.get(req["game"], req["game"])

    try:
        await callback.message.edit_text(
            f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Rematch accepted!</b>\n<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Starting <b>{game_name}</b>…",
            parse_mode="HTML", reply_markup=None,
        )
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Rematch starting!")

    p1_doc  = await db.users.find_one({"user_id": req["player1_id"]})
    p2_doc  = await db.users.find_one({"user_id": req["player2_id"]})
    p1_name = (p1_doc.get("username") or p1_doc.get("first_name") or str(req["player1_id"])) if p1_doc else req.get("requester_name", str(req["player1_id"]))
    p2_name = (p2_doc.get("username") or p2_doc.get("first_name") or str(req["player2_id"])) if p2_doc else req.get("opponent_name", str(req["player2_id"]))

    await start_match(
        bot          = callback.message.bot,
        group_id     = req["group_id"],
        player1_id   = req["player1_id"],
        player1_name = p1_name,
        player2_id   = req["player2_id"],
        player2_name = p2_name,
        game         = req["game"],
    )


@router.callback_query(F.data.startswith("rematch_decline:"))
async def cb_rematch_decline(callback: CallbackQuery):
    db     = get_db()
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
        await callback.message.edit_text("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>Rematch Declined</b>", parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Declined")


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
        "req_id":         req_id,
        "requester_id":   user.id,
        "requester_name": requester_name,
        "opponent_id":    opponent_id,
        "opponent_name":  opp_name,
        "player1_id":     p1_id,
        "player2_id":     p2_id,
        "game":           game,
        "group_id":       group_id,
        "status":         "pending",
        "created_at":     now_utc(),
    })

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.bot.send_message(
        chat_id    = group_id,
        text       = (
            f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>New Game Request</b>\n\n"
            f"@{requester_name} wants to play <b>{game_name}</b>!\n\n"
            f"<i>@{opp_name}, do you accept?</i>"
        ),
        parse_mode   = "HTML",
        reply_markup = newgame_accept_keyboard(req_id),
    )
    await callback.answer("<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Request sent!")


@router.callback_query(F.data.startswith("newgame_accept:"))
async def cb_newgame_accept(callback: CallbackQuery):
    db     = get_db()
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
            f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>@{req['opponent_name']} accepted!</b>\n<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Starting <b>{game_name}</b>…",
            parse_mode="HTML", reply_markup=None,
        )
    except Exception:
        pass
    await callback.answer(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Starting {game_name}!")

    p1_doc  = await db.users.find_one({"user_id": req["player1_id"]})
    p2_doc  = await db.users.find_one({"user_id": req["player2_id"]})
    p1_name = (p1_doc.get("username") or p1_doc.get("first_name") or str(req["player1_id"])) if p1_doc else req.get("requester_name", str(req["player1_id"]))
    p2_name = (p2_doc.get("username") or p2_doc.get("first_name") or str(req["player2_id"])) if p2_doc else req.get("opponent_name", str(req["player2_id"]))

    await start_match(
        bot          = callback.message.bot,
        group_id     = req["group_id"],
        player1_id   = req["player1_id"],
        player1_name = p1_name,
        player2_id   = req["player2_id"],
        player2_name = p2_name,
        game         = req["game"],
    )


@router.callback_query(F.data.startswith("newgame_decline:"))
async def cb_newgame_decline(callback: CallbackQuery):
    db     = get_db()
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
        await callback.message.edit_text("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>Game Request Declined</b>", parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Declined")
