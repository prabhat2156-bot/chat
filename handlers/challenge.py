"""
Challenge System (/challenge @opponent) — FIXED VERSION

Fixes:
1. Double-accept prevention: atomic findOneAndUpdate with status="pending" condition
2. Double match_confirm prevention: atomic findOneAndUpdate
3. Advanced UI: richer challenge and confirmation cards
4. Auto-cleanup of expired/declined challenge messages
"""
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from database.mongodb import get_db
from database.models import ChallengeModel, now_utc, new_id
from utils.keyboards import (
    game_selection_keyboard,
    challenge_accept_keyboard,
    match_confirm_keyboard,
)
from utils.db_helpers import (
    get_or_create_user,
    get_active_challenge_for_user_in_group,
    get_active_match_for_user_in_group,
)
from utils import timeout_manager
from config import CHALLENGE_TIMEOUT, GAME_NAMES, GAME_EMOJI

logger = logging.getLogger(__name__)
router = Router()

CONFIRM_TIMEOUT = 120


async def _expire_challenge(challenge_id: str, bot):
    db = get_db()
    ch = await db.challenges.find_one({"challenge_id": challenge_id, "status": "pending"})
    if not ch:
        return
    await db.challenges.update_one({"challenge_id": challenge_id}, {"$set": {"status": "expired"}})
    await db.challenge_selections.delete_one({"challenger_id": ch["challenger_id"]})
    try:
        await bot.edit_message_text(
            chat_id    = ch["group_id"],
            message_id = ch["message_id"],
            text       = "⏰ <b>Challenge Expired</b>\n<i>No response received in time.</i>",
            parse_mode = "HTML",
            reply_markup = None,
        )
    except Exception:
        pass


async def _expire_confirmation(confirm_id: str, bot):
    db = get_db()
    conf = await db.match_confirmations.find_one({"confirm_id": confirm_id, "status": "pending"})
    if not conf:
        return
    await db.match_confirmations.update_one({"confirm_id": confirm_id}, {"$set": {"status": "expired"}})
    try:
        await bot.edit_message_text(
            chat_id    = conf["group_id"],
            message_id = conf["message_id"],
            text       = "⏰ <b>Match confirmation expired.</b>\nChallenge again to play.",
            parse_mode = "HTML",
            reply_markup = None,
        )
    except Exception:
        pass


@router.message(Command("challenge"))
async def cmd_challenge(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>/challenge</b> only works in groups!\n"
            "Add me to a group and challenge someone there.",
            parse_mode="HTML",
        )
        return

    db         = get_db()
    challenger = message.from_user
    text       = message.text or ""
    args       = text.split()

    if len(args) < 2:
        await message.answer(
            "<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Usage:</b> <code>/challenge @username</code>\n\n"
            "Example: <code>/challenge @godmadara01</code>\n\n"
            "This is a <b>free</b> match — no payment required.\n"
            "For paid battles use /battle @username",
            parse_mode="HTML",
        )
        return

    await get_or_create_user(challenger.id, challenger.username or "", challenger.first_name or "")

    group_id = message.chat.id

    active_match = await get_active_match_for_user_in_group(challenger.id, group_id)
    if active_match:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You are already in an active match in this group!\n"
            "Use /mygame to see it.",
            parse_mode="HTML",
        )
        return

    active_challenge = await get_active_challenge_for_user_in_group(challenger.id, group_id)
    if active_challenge:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You already have a pending challenge in this group!\n"
            "Wait for it to expire or be declined.",
            parse_mode="HTML",
        )
        return

    # Resolve opponent
    opponent_id         = None
    opponent_username   = None
    opponent_first_name = None

    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention" and ent.user:
                if ent.user.id == challenger.id:
                    await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You cannot challenge yourself!")
                    return
                if ent.user.is_bot:
                    await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You cannot challenge a bot!")
                    return
                opponent_id         = ent.user.id
                opponent_username   = ent.user.username or ent.user.first_name
                opponent_first_name = ent.user.first_name
                break

    if opponent_id is None and message.entities:
        for ent in message.entities:
            if ent.type == "mention":
                mention_text = text[ent.offset + 1: ent.offset + ent.length]
                if mention_text.lower() == (challenger.username or "").lower():
                    await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You cannot challenge yourself!")
                    return
                opponent_username = mention_text
                break

    if opponent_id is None and opponent_username:
        user_doc = await db.users.find_one(
            {"username": {"$regex": f"^{opponent_username}$", "$options": "i"}}
        )
        if user_doc:
            opponent_id         = user_doc["user_id"]
            opponent_username   = user_doc.get("username") or user_doc.get("first_name") or opponent_username
            opponent_first_name = user_doc.get("first_name", opponent_username)

    if opponent_username is None and opponent_id is None:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Could not find that player. Tag them directly with @username.",
            parse_mode="HTML",
        )
        return

    challenger_name = challenger.username or challenger.first_name
    opponent_name   = opponent_username or str(opponent_id)

    # Game selection card
    select_msg = await message.answer(
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>CHALLENGE REQUEST</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<tg-emoji emoji-id='5397716813721116058'>👊</tg-emoji> <b>Challenger</b>  ›  @{challenger_name}\n"
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>Opponent</b>     ›  @{opponent_name}\n\n"
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Select a game to challenge with:</b>",
        parse_mode="HTML",
        reply_markup=game_selection_keyboard(f"SEL_{challenger.id}"),
    )

    await db.challenge_selections.replace_one(
        {"user_id": challenger.id},
        {
            "user_id":          challenger.id,
            "challenger_id":    challenger.id,
            "challenger_name":  challenger_name,
            "opponent_id":      opponent_id,
            "opponent_username": opponent_name,
            "group_id":         group_id,
            "select_msg_id":    select_msg.message_id,
        },
        upsert=True,
    )


@router.callback_query(F.data.startswith("sel_game:"))
async def cb_select_game(callback: CallbackQuery):
    db        = get_db()
    parts     = callback.data.split(":")
    game      = parts[2]
    caller_id = callback.from_user.id

    selection = await db.challenge_selections.find_one({"user_id": caller_id})
    if not selection:
        await callback.answer("❌ Session expired. Use /challenge again.", show_alert=True)
        return
    if selection.get("challenger_id") != caller_id:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    group_id         = selection["group_id"]
    challenger_name  = selection["challenger_name"]
    opponent_id      = selection.get("opponent_id")
    opponent_username = selection["opponent_username"]
    select_msg_id    = selection["select_msg_id"]

    active_match = await get_active_match_for_user_in_group(caller_id, group_id)
    if active_match:
        await callback.answer("❌ You are already in a match in this group.", show_alert=True)
        return

    game_name  = GAME_NAMES.get(game, game)
    game_emoji = GAME_EMOJI.get(game, "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji>")

    # Send the challenge card
    challenge_msg = await callback.message.bot.send_message(
        chat_id = group_id,
        text    = (
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>BATTLE CHALLENGE!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<tg-emoji emoji-id='5397716813721116058'>👊</tg-emoji> <b>Challenger</b>  ›  @{challenger_name}\n"
            f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>Opponent</b>     ›  @{opponent_username}\n"
            f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Game</b>           ›  {game_emoji} {game_name.replace(f'{game_emoji} ', '')}\n\n"
            f"⏰ <i>Expires in {CHALLENGE_TIMEOUT // 60} minutes</i>\n\n"
            f"@{opponent_username}, do you accept this challenge?"
        ),
        parse_mode   = "HTML",
        reply_markup = challenge_accept_keyboard("PLACEHOLDER"),
    )

    challenge = ChallengeModel.new(
        challenger_id   = caller_id,
        challenger_name = challenger_name,
        opponent_id     = opponent_id or 0,
        opponent_name   = opponent_username,
        game            = game,
        group_id        = group_id,
        message_id      = challenge_msg.message_id,
    )
    challenge["opponent_username"]    = opponent_username
    challenge["opponent_id_required"] = opponent_id
    challenge["expires_at"]           = datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_TIMEOUT)

    await db.challenges.insert_one(challenge)
    await callback.message.bot.edit_message_reply_markup(
        chat_id    = group_id,
        message_id = challenge_msg.message_id,
        reply_markup = challenge_accept_keyboard(challenge["challenge_id"]),
    )

    # Delete game selection message
    try:
        await callback.message.bot.delete_message(chat_id=group_id, message_id=select_msg_id)
    except Exception:
        pass

    await db.challenge_selections.delete_one({"user_id": caller_id})

    timeout_manager.set_timeout(
        f"challenge_{challenge['challenge_id']}", CHALLENGE_TIMEOUT,
        _expire_challenge, challenge["challenge_id"], callback.message.bot,
    )
    await callback.answer(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Challenge sent with {game_name}!")


@router.callback_query(F.data.startswith("challenge_accept:"))
async def cb_challenge_accept(callback: CallbackQuery):
    db   = get_db()
    challenge_id = callback.data.split(":")[1]
    user = callback.from_user

    ch = await db.challenges.find_one({"challenge_id": challenge_id})
    if not ch:
        await callback.answer("❌ Challenge not found.", show_alert=True)
        return

    # Validate who can accept
    can_accept = False
    req_id     = ch.get("opponent_id_required")
    opp_uname  = (ch.get("opponent_username") or "").lower()
    if req_id and req_id != 0 and user.id == req_id:
        can_accept = True
    elif opp_uname and user.username and user.username.lower() == opp_uname:
        can_accept = True

    if not can_accept:
        await callback.answer("❌ This challenge is not for you.", show_alert=True)
        return

    if ch["status"] != "pending":
        msgs = {
            "accepted": "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Already accepted.",
            "declined": "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> This challenge was declined.",
            "expired":  "⏰ This challenge expired.",
        }
        await callback.answer(msgs.get(ch["status"], "❌ No longer active."), show_alert=True)
        return

    active_match = await get_active_match_for_user_in_group(user.id, ch["group_id"])
    if active_match:
        await callback.answer("❌ You are already in a match in this group.", show_alert=True)
        return

    active_match2 = await get_active_match_for_user_in_group(ch["challenger_id"], ch["group_id"])
    if active_match2:
        await callback.answer("❌ Challenger is already in another match.", show_alert=True)
        return

    # ATOMIC: only accept if still pending — prevents double-click starting two games
    result = await db.challenges.find_one_and_update(
        {"challenge_id": challenge_id, "status": "pending"},
        {"$set": {"status": "accepted", "opponent_id": user.id}},
        return_document=True,
    )
    if result is None:
        await callback.answer("❌ Challenge already accepted or expired.", show_alert=True)
        return

    timeout_manager.cancel_timeout(f"challenge_{challenge_id}")
    await get_or_create_user(user.id, user.username or "", user.first_name or "")

    opponent_name = user.username or user.first_name
    game_name     = GAME_NAMES.get(ch["game"], ch["game"])
    game_emoji    = GAME_EMOJI.get(ch["game"], "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji>")

    try:
        await callback.message.edit_text(
            f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>@{opponent_name} accepted the challenge!</b>\n\n"
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> @{ch['challenger_name']}  vs  @{opponent_name}\n"
            f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {game_emoji} {game_name.replace(f'{game_emoji} ', '')}\n\n"
            f"<i>Starting match confirmation…</i>",
            parse_mode   = "HTML",
            reply_markup = None,
        )
    except Exception:
        pass

    await _create_match_confirmation(
        bot              = callback.message.bot,
        group_id         = ch["group_id"],
        player1_id       = ch["challenger_id"],
        player1_name     = ch["challenger_name"],
        player2_id       = user.id,
        player2_name     = opponent_name,
        game             = ch["game"],
        challenge_msg_id = ch.get("message_id"),  # will be deleted when match starts
    )
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Accepted! Press Ready to start.")


async def _create_match_confirmation(
    bot, group_id, player1_id, player1_name, player2_id, player2_name, game,
    challenge_msg_id: int = None,
):
    db         = get_db()
    confirm_id = new_id()
    game_name  = GAME_NAMES.get(game, game)
    game_emoji = GAME_EMOJI.get(game, "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji>")

    text = _confirm_text(game_name, game_emoji, player1_name, player2_name, False, False)
    msg  = await bot.send_message(
        chat_id      = group_id,
        text         = text,
        parse_mode   = "HTML",
        reply_markup = match_confirm_keyboard(confirm_id),
    )

    await db.match_confirmations.insert_one({
        "confirm_id":        confirm_id,
        "player1_id":        player1_id,
        "player1_name":      player1_name,
        "player2_id":        player2_id,
        "player2_name":      player2_name,
        "game":              game,
        "group_id":          group_id,
        "message_id":        msg.message_id,
        "challenge_msg_id":  challenge_msg_id,  # accepted challenge card, deleted on match start
        "player1_ready":     False,
        "player2_ready":     False,
        "status":            "pending",
        "created_at":        now_utc(),
    })

    timeout_manager.set_timeout(
        f"confirm_{confirm_id}", CONFIRM_TIMEOUT,
        _expire_confirmation, confirm_id, bot,
    )


def _confirm_text(game_name, game_emoji, p1_name, p2_name, p1_ready, p2_ready):
    p1_status = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>READY!</b>" if p1_ready else "⏳ Not ready"
    p2_status = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>READY!</b>" if p2_ready else "⏳ Not ready"
    clean_name = game_name.replace(f"{game_emoji} ", "")
    return (
        f"<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> <b>MATCH CONFIRMATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Game:</b> {game_emoji} {clean_name}\n\n"
        f"<tg-emoji emoji-id='5397716813721116058'>👊</tg-emoji> @{p1_name}  —  {p1_status}\n"
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> @{p2_name}  —  {p2_status}\n\n"
        f"<i>Both players press <tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> I'm Ready to start!</i>"
    )


@router.callback_query(F.data.startswith("match_confirm:"))
async def cb_match_confirm(callback: CallbackQuery):
    db         = get_db()
    confirm_id = callback.data.split(":")[1]
    user       = callback.from_user

    conf = await db.match_confirmations.find_one({"confirm_id": confirm_id, "status": "pending"})
    if not conf:
        await callback.answer("❌ Confirmation expired or not found.", show_alert=True)
        return

    if user.id not in [conf["player1_id"], conf["player2_id"]]:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    is_p1 = user.id == conf["player1_id"]
    field  = "player1_ready" if is_p1 else "player2_ready"

    if conf.get(field):
        await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> You already confirmed — waiting for your opponent!", show_alert=False)
        return

    # ATOMIC: only update if field is still False — prevents double-click starting two matches
    result = await db.match_confirmations.find_one_and_update(
        {"confirm_id": confirm_id, "status": "pending", field: False},
        {"$set": {field: True}},
        return_document=True,
    )
    if result is None:
        await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Already confirmed!", show_alert=False)
        return

    conf      = result
    game_name  = GAME_NAMES.get(conf["game"], conf["game"])
    game_emoji = GAME_EMOJI.get(conf["game"], "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji>")
    both_ready = conf["player1_ready"] and conf["player2_ready"]

    if both_ready:
        # ATOMIC: mark as started so no second trigger
        started = await db.match_confirmations.find_one_and_update(
            {"confirm_id": confirm_id, "status": "pending"},
            {"$set": {"status": "started"}},
            return_document=True,
        )
        if started is None:
            # Already started by another click
            await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Match is starting!", show_alert=False)
            return

        timeout_manager.cancel_timeout(f"confirm_{confirm_id}")

        # Delete: confirmation card + challenge accepted card
        cleanup_ids = [
            conf.get("message_id"),
            conf.get("challenge_msg_id"),
        ]

        from handlers.match import start_match
        await start_match(
            bot              = callback.message.bot,
            group_id         = conf["group_id"],
            player1_id       = conf["player1_id"],
            player1_name     = conf["player1_name"],
            player2_id       = conf["player2_id"],
            player2_name     = conf["player2_name"],
            game             = conf["game"],
            cleanup_msg_ids  = cleanup_ids,
        )
        await callback.answer("<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Match starting!")
    else:
        updated_text = _confirm_text(
            game_name, game_emoji,
            conf["player1_name"], conf["player2_name"],
            conf["player1_ready"], conf["player2_ready"],
        )
        try:
            await callback.message.edit_text(
                updated_text,
                parse_mode   = "HTML",
                reply_markup = match_confirm_keyboard(confirm_id),
            )
        except Exception:
            pass
        await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Confirmed! Waiting for the other player…")


@router.callback_query(F.data.startswith("challenge_decline:"))
async def cb_challenge_decline(callback: CallbackQuery):
    db           = get_db()
    challenge_id = callback.data.split(":")[1]
    user         = callback.from_user

    ch = await db.challenges.find_one({"challenge_id": challenge_id})
    if not ch:
        await callback.answer("❌ Challenge not found.", show_alert=True)
        return

    can_decline = False
    req_id      = ch.get("opponent_id_required")
    opp_uname   = (ch.get("opponent_username") or "").lower()
    if req_id and req_id != 0 and user.id == req_id:
        can_decline = True
    elif opp_uname and user.username and user.username.lower() == opp_uname:
        can_decline = True

    if not can_decline:
        await callback.answer("❌ This button is not for you.", show_alert=True)
        return

    if ch["status"] != "pending":
        await callback.answer("❌ Challenge no longer active.", show_alert=True)
        return

    timeout_manager.cancel_timeout(f"challenge_{challenge_id}")
    await db.challenges.update_one(
        {"challenge_id": challenge_id},
        {"$set": {"status": "declined"}},
    )

    opponent_name = user.username or user.first_name
    try:
        await callback.message.edit_text(
            f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>Challenge Declined</b>\n\n"
            f"@{opponent_name} declined the challenge from @{ch['challenger_name']}.",
            parse_mode   = "HTML",
            reply_markup = None,
        )
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Challenge declined.")
