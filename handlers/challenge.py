import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from database.mongodb import get_db
from database.models import ChallengeModel, now_utc
from utils.keyboards import game_selection_keyboard, challenge_accept_keyboard
from utils.db_helpers import (
    get_or_create_user,
    get_active_challenge_for_user,
    get_active_match_for_user,
)
from utils import timeout_manager
from config import CHALLENGE_TIMEOUT, GAME_NAMES

logger = logging.getLogger(__name__)
router = Router()


async def _expire_challenge(challenge_id: str, bot):
    db = get_db()
    challenge = await db.challenges.find_one(
        {"challenge_id": challenge_id, "status": "pending"}
    )
    if not challenge:
        return
    await db.challenges.update_one(
        {"challenge_id": challenge_id}, {"$set": {"status": "expired"}}
    )
    try:
        await bot.edit_message_text(
            chat_id=challenge["group_id"],
            message_id=challenge["message_id"],
            text="⏰ Challenge Expired",
        )
    except Exception:
        pass


@router.message(Command("challenge"))
async def cmd_challenge(message: Message):
    if message.chat.type == "private":
        await message.answer("❌ This bot only works in groups.")
        return

    db = get_db()
    challenger = message.from_user
    text = message.text or ""
    args = text.split()

    if len(args) < 2:
        await message.answer(
            "Usage: /challenge @username\n\n"
            "Make sure to tag the player directly (e.g. /challenge @PlayerB)."
        )
        return

    await get_or_create_user(
        challenger.id,
        challenger.username or "",
        challenger.first_name or "",
    )

    active_match = await get_active_match_for_user(challenger.id)
    if active_match:
        await message.answer("❌ You are already in an active match.")
        return

    active_challenge = await get_active_challenge_for_user(challenger.id)
    if active_challenge:
        await message.answer("❌ You already have an active challenge.")
        return

    opponent_id = None
    opponent_username = None
    opponent_first_name = None

    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention" and ent.user:
                if ent.user.id == challenger.id:
                    continue
                if ent.user.is_bot:
                    await message.answer("❌ You cannot challenge a bot.")
                    return
                opponent_id = ent.user.id
                opponent_username = ent.user.username or ent.user.first_name
                opponent_first_name = ent.user.first_name
                break
            elif ent.type == "mention":
                mention_text = text[ent.offset + 1: ent.offset + ent.length]
                if mention_text.lower() == (challenger.username or "").lower():
                    continue
                opponent_username = mention_text
                break

    if opponent_id is None and opponent_username:
        user_doc = await db.users.find_one({
            "username": {"$regex": f"^{opponent_username}$", "$options": "i"}
        })
        if user_doc:
            opponent_id = user_doc["user_id"]
            opponent_username = user_doc.get("username") or user_doc.get("first_name") or opponent_username
            opponent_first_name = user_doc.get("first_name", opponent_username)
        else:
            await message.answer(
                f"❌ @{opponent_username} has not interacted with the bot yet.\n\n"
                f"Ask them to send any message in this group first, then try challenging again."
            )
            return

    if opponent_id is None:
        mention = args[1].lstrip("@")
        await message.answer(
            f"❌ Could not find @{mention}.\n\n"
            "Make sure the player has chatted in this group before, "
            "or use a text mention (type their name and select from autocomplete)."
        )
        return

    if opponent_id == challenger.id:
        await message.answer("❌ You cannot challenge yourself.")
        return

    active_challenge_against = await db.challenges.find_one({
        "challenger_id": challenger.id,
        "opponent_id": opponent_id,
        "status": "pending",
    })
    if active_challenge_against:
        await message.answer("❌ You already have a pending challenge against this player.")
        return

    active_opp_match = await get_active_match_for_user(opponent_id)
    if active_opp_match:
        opp_display = f"@{opponent_username}" if opponent_username else "That player"
        await message.answer(f"❌ {opp_display} is already in an active match.")
        return

    await get_or_create_user(
        opponent_id,
        opponent_username or "",
        opponent_first_name or opponent_username or "",
    )

    challenger_name = challenger.username or challenger.first_name
    opponent_name = opponent_username or str(opponent_id)

    select_msg = await message.answer(
        f"🎮 <b>Select a game to challenge @{opponent_name}</b>\n\n"
        f"👤 Challenger: @{challenger_name}\n"
        f"👤 Opponent: @{opponent_name}",
        parse_mode="HTML",
        reply_markup=game_selection_keyboard(f"TEMP"),
    )

    await db.challenge_selections.replace_one(
        {"user_id": challenger.id},
        {
            "user_id": challenger.id,
            "challenger_id": challenger.id,
            "challenger_name": challenger_name,
            "opponent_id": opponent_id,
            "opponent_name": opponent_name,
            "group_id": message.chat.id,
            "select_msg_id": select_msg.message_id,
        },
        upsert=True,
    )

    await message.bot.edit_message_reply_markup(
        chat_id=message.chat.id,
        message_id=select_msg.message_id,
        reply_markup=game_selection_keyboard(f"SEL_{challenger.id}"),
    )


@router.callback_query(F.data.startswith("sel_game:"))
async def cb_select_game(callback: CallbackQuery):
    db = get_db()
    parts = callback.data.split(":")
    game = parts[2]
    caller_id = callback.from_user.id

    selection = await db.challenge_selections.find_one({"user_id": caller_id})
    if not selection:
        await callback.answer("❌ Session expired. Please use /challenge again.", show_alert=True)
        return

    if selection.get("challenger_id") != caller_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    challenger_name = selection["challenger_name"]
    opponent_id = selection["opponent_id"]
    opponent_name = selection["opponent_name"]
    group_id = selection["group_id"]
    select_msg_id = selection["select_msg_id"]

    active_match = await get_active_match_for_user(caller_id)
    if active_match:
        await callback.answer("❌ You are already in an active match.", show_alert=True)
        return
    active_challenge = await get_active_challenge_for_user(caller_id)
    if active_challenge:
        await callback.answer("❌ You already have an active challenge.", show_alert=True)
        return

    game_name = GAME_NAMES.get(game, game)

    challenge_msg = await callback.message.bot.send_message(
        chat_id=group_id,
        text=(
            f"🎮 <b>Challenge Request</b>\n\n"
            f"👤 Challenger: @{challenger_name}\n"
            f"👤 Opponent: @{opponent_name}\n\n"
            f"🎮 Game: {game_name}"
        ),
        parse_mode="HTML",
        reply_markup=challenge_accept_keyboard("PLACEHOLDER"),
    )

    challenge = ChallengeModel.new(
        challenger_id=caller_id,
        challenger_name=challenger_name,
        opponent_id=opponent_id,
        opponent_name=opponent_name,
        game=game,
        group_id=group_id,
        message_id=challenge_msg.message_id,
    )
    from datetime import timedelta
    challenge["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_TIMEOUT)
    await db.challenges.insert_one(challenge)

    await callback.message.bot.edit_message_reply_markup(
        chat_id=group_id,
        message_id=challenge_msg.message_id,
        reply_markup=challenge_accept_keyboard(challenge["challenge_id"]),
    )

    try:
        await callback.message.bot.delete_message(chat_id=group_id, message_id=select_msg_id)
    except Exception:
        pass

    await db.challenge_selections.delete_one({"user_id": caller_id})

    timeout_manager.set_timeout(
        f"challenge_{challenge['challenge_id']}",
        CHALLENGE_TIMEOUT,
        _expire_challenge,
        challenge["challenge_id"],
        callback.message.bot,
    )

    await callback.answer()


@router.callback_query(F.data.startswith("challenge_accept:"))
async def cb_challenge_accept(callback: CallbackQuery):
    db = get_db()
    challenge_id = callback.data.split(":")[1]
    user = callback.from_user

    challenge = await db.challenges.find_one({"challenge_id": challenge_id})
    if not challenge:
        await callback.answer("❌ Challenge not found.", show_alert=True)
        return

    if user.id != challenge["opponent_id"]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    if challenge["status"] != "pending":
        status_msg = {
            "accepted": "❌ Challenge already accepted.",
            "declined": "❌ Challenge was declined.",
            "expired": "❌ Challenge has expired.",
        }
        await callback.answer(status_msg.get(challenge["status"], "❌ Challenge no longer active."), show_alert=True)
        return

    active_match = await get_active_match_for_user(user.id)
    if active_match:
        await callback.answer("❌ You are already in an active match.", show_alert=True)
        return

    active_match2 = await get_active_match_for_user(challenge["challenger_id"])
    if active_match2:
        await callback.answer("❌ Challenger is already in an active match.", show_alert=True)
        return

    timeout_manager.cancel_timeout(f"challenge_{challenge_id}")
    await db.challenges.update_one(
        {"challenge_id": challenge_id}, {"$set": {"status": "accepted"}}
    )

    await get_or_create_user(user.id, user.username or "", user.first_name or "")

    try:
        await callback.message.edit_text(
            f"✅ <b>Challenge Accepted!</b>\nStarting Match...",
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception:
        pass

    from handlers.match import start_match
    await start_match(
        bot=callback.message.bot,
        group_id=challenge["group_id"],
        player1_id=challenge["challenger_id"],
        player1_name=challenge["challenger_name"],
        player2_id=challenge["opponent_id"],
        player2_name=challenge["opponent_name"],
        game=challenge["game"],
    )
    await callback.answer("✅ Match starting!")


@router.callback_query(F.data.startswith("challenge_decline:"))
async def cb_challenge_decline(callback: CallbackQuery):
    db = get_db()
    challenge_id = callback.data.split(":")[1]
    user = callback.from_user

    challenge = await db.challenges.find_one({"challenge_id": challenge_id})
    if not challenge:
        await callback.answer("❌ Challenge not found.", show_alert=True)
        return

    if user.id != challenge["opponent_id"]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    if challenge["status"] != "pending":
        await callback.answer("❌ Challenge is no longer active.", show_alert=True)
        return

    timeout_manager.cancel_timeout(f"challenge_{challenge_id}")
    await db.challenges.update_one(
        {"challenge_id": challenge_id}, {"$set": {"status": "declined"}}
    )

    try:
        await callback.message.edit_text(
            "❌ <b>Challenge Declined</b>", parse_mode="HTML", reply_markup=None
        )
    except Exception:
        pass
    await callback.answer("❌ Declined")


@router.message()
async def track_user(message: Message):
    if message.chat.type == "private":
        return
    if message.from_user and not message.from_user.is_bot:
        from utils.db_helpers import get_or_create_user as _get
        await _get(
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
        )
