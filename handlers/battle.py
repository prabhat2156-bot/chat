"""
Paid Battle System (/battle @opponent) — FIXED VERSION

Fixes applied:
1. Auto-delete "waiting for X to confirm" message (atomic lock prevents duplicate sends)
2. Double-click prevention: MongoDB atomic findOneAndUpdate for all confirm/ready clicks
3. Admin first-click-only: approving_admin_id locked atomically on first approve click
4. Duplicate round start prevention: atomic round_lock field in DB
5. Individual payment DMs sent to each player after confirmation
6. Advanced UI: richer battle card, live round card, and status messages
"""
import asyncio
import logging
import math

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import GAME_NAMES, DEFAULT_FEE_PERCENT
from database.mongodb import get_db
from database.models import BattlePaidModel, now_utc
from utils.keyboards import (
    battle_form_keyboard,
    battle_game_select_keyboard,
    battle_rounds_keyboard,
    battle_confirm_keyboard,
    battle_admin_approve_keyboard,
    battle_ready_keyboard,
    battle_payout_done_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


class BattleFormStates(StatesGroup):
    waiting_amount = State()


def _short_id(battle: dict) -> str:
    return battle["battle_id"][:8].upper()


# ─── Master Card ──────────────────────────────────────────────────────────────

def _master_card_text(battle: dict) -> str:
    short_id   = _short_id(battle)
    game_label = GAME_NAMES.get(battle.get("game") or "", "—") if battle.get("game") else "—"
    rounds     = str(battle["total_rounds"]) if battle.get("total_rounds") else "—"
    status     = battle["status"]

    c_tick = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji>" if battle.get("challenger_confirmed") else "⏳"
    o_tick = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji>" if battle.get("opponent_confirmed")   else "⏳"

    lines = [
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>PAID BATTLE</b>  ·  🆔 <code>Battle {short_id}</code>",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"<tg-emoji emoji-id='5397716813721116058'>👊</tg-emoji> <b>Challenger</b>  ›  @{battle['challenger_name']}  {c_tick}",
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>Opponent</b>     ›  @{battle['opponent_name']}  {o_tick}",
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Game</b>           ›  {game_label}",
        f"<tg-emoji emoji-id='6237485887635067877'>🔢</tg-emoji> <b>Rounds</b>        ›  {rounds}",
    ]

    if battle.get("amount"):
        fee_each = battle.get("fee_per_player", 0)
        per_p    = battle.get("total_per_player", 0)
        prize    = battle.get("prize_pool", 0)
        fee_pct  = battle.get("fee_percent", 10)
        lines += [
            "",
            "━━━━━ <tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> STAKES <tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> ━━━━━",
            f"<tg-emoji emoji-id='4956601935592424315'>💵</tg-emoji> <b>Bet</b>          ›  ₹{battle['amount']} each",
            f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> <b>Fee ({fee_pct}%)</b>  ›  ₹{fee_each} each",
            f"<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> <b>You Pay</b>   ›  ₹{per_p} each",
            f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Prize Pool</b> ›  ₹{prize} to winner",
        ]

    lines.append("")

    if status == "form_filling":
        lines.append("<tg-emoji emoji-id='6141066526129653847'>📝</tg-emoji> <i>Battle form being filled…</i>")

    elif status == "pending_confirmation":
        lines.append("⏳ <b>Awaiting both players to confirm</b>")
        lines.append(f"  {c_tick} @{battle['challenger_name']}")
        lines.append(f"  {o_tick} @{battle['opponent_name']}")

    elif status == "pending_payment":
        lines.append("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Both players confirmed!</b>")
        lines.append("<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> <i>Waiting for admin to collect payment…</i>")

    elif status == "pending_ready":
        admin_name = battle.get("approving_admin_name", "Admin")
        c_r = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Ready" if battle.get("challenger_ready") else "⏳ Not ready"
        o_r = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Ready" if battle.get("opponent_ready") else "⏳ Not ready"
        lines.append(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Payment approved by @{admin_name}</b>")
        lines.append("")
        lines.append("<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> <b>Ready Check:</b>")
        lines.append(f"  @{battle['challenger_name']} — {c_r}")
        lines.append(f"  @{battle['opponent_name']} — {o_r}")

    elif status == "active":
        admin_name   = battle.get("approving_admin_name", "Admin")
        p1_wins      = battle.get("p1_wins", 0)
        p2_wins      = battle.get("p2_wins", 0)
        r_draws      = battle.get("round_draws", 0)
        cur_round    = battle.get("current_round", 0)
        total_rounds = battle.get("total_rounds", 0)
        lines.append(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Approved by @{admin_name}</b>")
        lines.append(f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Round {cur_round}/{total_rounds} in progress…</b>")
        lines.append(f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> @{battle['challenger_name']} <b>{p1_wins}</b> — <b>{p2_wins}</b> @{battle['opponent_name']}")
        if r_draws:
            lines.append(f"<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draws: {r_draws}")

    elif status == "pending_payout":
        winner_name  = battle.get("winner_name", "—")
        p1_wins      = battle.get("p1_wins", 0)
        p2_wins      = battle.get("p2_wins", 0)
        r_draws      = battle.get("round_draws", 0)
        prize        = battle.get("prize_pool", "?")
        admin_name   = battle.get("approving_admin_name", "Admin")
        draws_str    = f"  ({r_draws} draws)" if r_draws else ""
        lines.append(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Approved by @{admin_name}</b>")
        lines.append(f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Final: @{battle['challenger_name']} <b>{p1_wins}</b> — <b>{p2_wins}</b> @{battle['opponent_name']}{draws_str}")
        lines.append(f"\n<tg-emoji emoji-id='5440539497383087970'>🥇</tg-emoji> <b>WINNER: @{winner_name}!</b>")
        lines.append(f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <i>Prize ₹{prize} — payout pending by @{admin_name}</i>")

    elif status == "draw_pending":
        p1_wins   = battle.get("p1_wins", 0)
        p2_wins   = battle.get("p2_wins", 0)
        r_draws   = battle.get("round_draws", 0)
        prize     = battle.get("prize_pool", "?")
        draws_str = f"  ({r_draws} draws)" if r_draws else ""
        lines.append(f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Final: @{battle['challenger_name']} <b>{p1_wins}</b> — <b>{p2_wins}</b> @{battle['opponent_name']}{draws_str}")
        lines.append(f"\n<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>IT'S A DRAW!</b>  Prize: ₹{prize}")
        lines.append("<i>Admin: Split prize or offer rematch round</i>")

    elif status == "completed":
        winner_name  = battle.get("winner_name", "—")
        p1_wins      = battle.get("p1_wins", 0)
        p2_wins      = battle.get("p2_wins", 0)
        r_draws      = battle.get("round_draws", 0)
        prize        = battle.get("prize_pool", "?")
        admin_name   = battle.get("approving_admin_name", "Admin")
        draws_str    = f"  ({r_draws} draws)" if r_draws else ""
        lines.append(f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Final: @{battle['challenger_name']} <b>{p1_wins}</b> — <b>{p2_wins}</b> @{battle['opponent_name']}{draws_str}")
        lines.append(f"\n<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>WINNER: @{winner_name}!</b>")
        lines.append(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> ₹{prize} sent by @{admin_name}")
        lines.append("<tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji> <i>GG and well played!</i>")

    elif status == "cancelled":
        lines.append("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>Battle Cancelled</b>")

    elif status == "declined":
        lines.append("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>Battle Declined</b>")

    return "\n".join(lines)


# ─── Live Round Card ──────────────────────────────────────────────────────────

def _live_card_text(battle: dict, result_line: str = "") -> str:
    short_id     = _short_id(battle)
    game_label   = GAME_NAMES.get(battle.get("game") or "", "—")
    p1_wins      = battle.get("p1_wins", 0)
    p2_wins      = battle.get("p2_wins", 0)
    r_draws      = battle.get("round_draws", 0)
    cur_round    = battle.get("current_round", 0)
    total_rounds = battle.get("total_rounds", 0)

    bar_filled = "█" * p1_wins
    bar_empty  = "░" * (total_rounds - p1_wins - p2_wins - r_draws)
    bar_filled2 = "█" * p2_wins

    lines = [
        f"<tg-emoji emoji-id='4956395910306202687'>🔴</tg-emoji> <b>BATTLE LIVE</b>  🆔 <code>{short_id}</code>",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji>  @{battle['challenger_name']}  <b>VS</b>  @{battle['opponent_name']}",
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>{game_label}</b>  ›  Round <b>{cur_round}</b> of <b>{total_rounds}</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"",
        f"🏅 @{battle['challenger_name']}  ›  <b>{p1_wins}</b> win{'s' if p1_wins != 1 else ''}",
        f"🏅 @{battle['opponent_name']}  ›  <b>{p2_wins}</b> win{'s' if p2_wins != 1 else ''}",
    ]
    if r_draws:
        lines.append(f"<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draws  ›  <b>{r_draws}</b>")

    round_results = battle.get("round_results", [])
    if round_results:
        lines.append("")
        lines.append("<tg-emoji emoji-id='5282843764451195532'>📜</tg-emoji> <b>Round History:</b>")
        for r in round_results[-5:]:
            rnum = r["round"]
            if r["is_draw"]:
                lines.append(f"  Round {rnum}  ›  <tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draw")
            elif r.get("winner_id") == battle["challenger_id"]:
                lines.append(f"  Round {rnum}  ›  <tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> @{battle['challenger_name']}")
            else:
                lines.append(f"  Round {rnum}  ›  <tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> @{battle['opponent_name']}")

    if result_line:
        lines.append(f"\n{result_line}")

    return "\n".join(lines)


# ─── Draw outcome keyboards ───────────────────────────────────────────────────

def _draw_keyboard(battle_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Split Prize",   callback_data=f"bt_split:{battle_id}"),
        InlineKeyboardButton(text="<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> Rematch Round", callback_data=f"bt_rematch:{battle_id}"),
    ]])


_PE_CHECK = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji>"
_PE_WAIT  = "⏳"

def _rematch_confirm_keyboard(battle_id: str, c_confirmed: bool, o_confirmed: bool) -> InlineKeyboardMarkup:
    c_text = f"{_PE_CHECK if c_confirmed else _PE_WAIT} Challenger Ready"
    o_text = f"{_PE_CHECK if o_confirmed else _PE_WAIT} Opponent Ready"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c_text, callback_data=f"bt_rematch_ok:{battle_id}")],
        [InlineKeyboardButton(text=o_text, callback_data=f"bt_rematch_ok:{battle_id}")],
    ])


# ─── DB helpers ───────────────────────────────────────────────────────────────

async def _get_fee_percent(group_id: int) -> float:
    try:
        db = get_db()
        gs = await db.group_settings.find_one({"group_id": group_id})
        if gs and "fee_percent" in gs:
            return float(gs["fee_percent"])
    except Exception:
        pass
    return DEFAULT_FEE_PERCENT


async def _get_admin_mentions(bot: Bot, group_id: int):
    try:
        admins = await bot.get_chat_administrators(group_id)
        ids, parts = [], []
        for a in admins:
            if a.user.is_bot:
                continue
            ids.append(a.user.id)
            parts.append(f"@{a.user.username}" if a.user.username
                         else f"<a href='tg://user?id={a.user.id}'>{a.user.first_name}</a>")
        return ids, (" ".join(parts) if parts else "(no admins)")
    except Exception as e:
        logger.warning(f"Could not get admins for {group_id}: {e}")
        return [], "(could not fetch admins)"


async def _safe_delete(bot: Bot, chat_id: int, message_id):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, int(message_id))
    except Exception:
        pass


async def _edit_master_card(bot: Bot, battle: dict, reply_markup=None):
    msg_id   = battle.get("form_message_id")
    group_id = battle.get("group_id")
    if not msg_id or not group_id:
        return
    try:
        await bot.edit_message_text(
            chat_id      = group_id,
            message_id   = int(msg_id),
            text         = _master_card_text(battle),
            reply_markup = reply_markup,
            parse_mode   = "HTML",
        )
    except Exception as e:
        logger.debug(f"edit_master_card failed: {e}")


async def _edit_live_card(bot: Bot, battle: dict, result_line: str = ""):
    live_msg_id = battle.get("live_msg_id")
    group_id    = battle.get("group_id")
    if not live_msg_id or not group_id:
        return
    try:
        await bot.edit_message_text(
            chat_id    = group_id,
            message_id = int(live_msg_id),
            text       = _live_card_text(battle, result_line),
            parse_mode = "HTML",
        )
    except Exception as e:
        logger.debug(f"edit_live_card failed: {e}")


# ─── /battle command ──────────────────────────────────────────────────────────

@router.message(Command("battle"))
async def cmd_battle(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>/battle</b> only works in groups!\n"
            "Add me to a group and challenge someone there.",
            parse_mode="HTML",
        )
        return

    db          = get_db()
    challenger  = message.from_user
    text        = message.text or ""
    args        = text.split()
    group_id    = message.chat.id

    if len(args) < 2:
        await message.answer(
            "<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Usage:</b> <code>/battle @username</code>\n\n"
            "Example: <code>/battle @godmadara01</code>",
            parse_mode="HTML",
        )
        return

    # Check if challenger already has an active battle
    existing = await db.battles.find_one({
        "group_id": group_id,
        "challenger_id": challenger.id,
        "status": {"$nin": ["completed", "cancelled", "declined"]},
    })
    if existing:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You already have an active battle in this group!\n"
            "Use /mygame to see it.",
            parse_mode="HTML",
        )
        return

    # Resolve opponent
    opponent_id = None
    opponent_username = None
    opponent_first_name = None

    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention" and ent.user:
                if ent.user.id == challenger.id:
                    await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You cannot battle yourself.")
                    return
                if ent.user.is_bot:
                    await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You cannot battle a bot.")
                    return
                opponent_id = ent.user.id
                opponent_username = ent.user.username or ent.user.first_name
                opponent_first_name = ent.user.first_name
                break

    if opponent_id is None and message.entities:
        for ent in message.entities:
            if ent.type == "mention":
                mention_text = text[ent.offset + 1: ent.offset + ent.length]
                if mention_text.lower() == (challenger.username or "").lower():
                    await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> You cannot battle yourself.")
                    return
                opponent_username = mention_text
                break

    if opponent_id is None and opponent_username:
        user_doc = await db.users.find_one(
            {"username": {"$regex": f"^{opponent_username}$", "$options": "i"}}
        )
        if user_doc:
            opponent_id = user_doc["user_id"]
            opponent_username = user_doc.get("username") or user_doc.get("first_name") or opponent_username
            opponent_first_name = user_doc.get("first_name", opponent_username)

    if opponent_username is None and opponent_id is None:
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Could not find that player. Tag them directly.")
        return

    challenger_name = challenger.username or challenger.first_name
    opponent_name   = opponent_username or str(opponent_id)
    fee_percent     = await _get_fee_percent(group_id)

    # Send the initial battle card
    card_msg = await message.answer(
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>PAID BATTLE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Setting up challenge…</i>\n\n"
        f"<tg-emoji emoji-id='5397716813721116058'>👊</tg-emoji> <b>Challenger</b>  ›  @{challenger_name}\n"
        f"<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>Opponent</b>     ›  @{opponent_name}\n"
        f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> <b>Fee</b>            ›  {fee_percent}% platform fee\n\n"
        f"<tg-emoji emoji-id='6141066526129653847'>📝</tg-emoji> <i>@{challenger_name}, fill in the battle details below:</i>",
        parse_mode="HTML",
        reply_markup=battle_form_keyboard(None, None, None, None),
    )

    # Create battle document with placeholder form_message_id
    from database.models import new_id
    battle_id = new_id()
    battle = {
        "battle_id": battle_id,
        "group_id": group_id,
        "challenger_id": challenger.id,
        "challenger_name": challenger_name,
        "opponent_id": opponent_id,
        "opponent_username": opponent_name,
        "opponent_name": opponent_name,
        "game": None,
        "total_rounds": None,
        "amount": None,
        "fee_percent": fee_percent,
        "fee_per_player": 0,
        "total_per_player": 0,
        "prize_pool": 0,
        "challenger_confirmed": False,
        "opponent_confirmed": False,
        "admin_approved": False,
        "approving_admin_id": None,
        "approving_admin_name": None,
        "challenger_ready": False,
        "opponent_ready": False,
        "current_round": 0,
        "current_round_game": None,
        "current_match_id": None,
        "p1_wins": 0,
        "p2_wins": 0,
        "round_draws": 0,
        "round_results": [],
        "next_game_proposed": None,
        "next_game_proposer_id": None,
        "winner_id": None,
        "winner_name": None,
        "winner_upi": None,
        "form_message_id": card_msg.message_id,
        "confirm_message_id": None,
        "payment_message_id": None,
        "ready_message_id": None,
        "waiting_confirm_msg_id": None,
        "live_msg_id": None,
        "round_lock": False,
        "status": "form_filling",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.battles.insert_one(battle)

    # Re-edit with proper keyboard now that we have battle_id
    try:
        await card_msg.edit_text(
            _master_card_text(battle),
            reply_markup=battle_form_keyboard(battle_id, None, None, None),
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─── Form callbacks ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "btf_noop")
async def cb_btf_noop(callback: CallbackQuery):
    await callback.answer("⏳ Fill Game, Rounds, and Amount first!", show_alert=True)


@router.callback_query(F.data.startswith("btf_cancel:"))
async def cb_btf_cancel(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger can cancel.", show_alert=True)
        return
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "cancelled"}})
    battle["status"] = "cancelled"
    try:
        await callback.message.edit_text(_master_card_text(battle), parse_mode="HTML", reply_markup=None)
    except Exception:
        pass
    await callback.answer("Battle cancelled.")


@router.callback_query(F.data.startswith("btf_back:"))
async def cb_btf_back(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            _master_card_text(battle),
            reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("btf_game:"))
async def cb_btf_game(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await callback.message.edit_text(
        "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Select a Game for this Battle</b>\n\n"
        "<i>Choose wisely — this game will be played every round!</i>",
        reply_markup=battle_game_select_keyboard(battle_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("btf_game_sel:"))
async def cb_btf_game_sel(callback: CallbackQuery):
    parts     = callback.data.split(":")
    battle_id = parts[1]
    game      = parts[2]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"game": game}})
    battle["game"] = game
    await callback.message.edit_text(
        _master_card_text(battle),
        reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
        parse_mode="HTML",
    )
    await callback.answer(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {GAME_NAMES.get(game, game)} selected!")


@router.callback_query(F.data.startswith("btf_rounds:"))
async def cb_btf_rounds(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await callback.message.edit_text(
        "<tg-emoji emoji-id='6237485887635067877'>🔢</tg-emoji> <b>Select Number of Rounds</b>\n\n"
        "Each round = 1 match.\n"
        "Player with most wins takes the prize!\n\n"
        "<i>Odd numbers recommended to avoid draws.</i>",
        reply_markup=battle_rounds_keyboard(battle_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("btf_rounds_sel:"))
async def cb_btf_rounds_sel(callback: CallbackQuery):
    parts     = callback.data.split(":")
    battle_id = parts[1]
    rounds    = int(parts[2])
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"total_rounds": rounds}})
    battle["total_rounds"] = rounds
    await callback.message.edit_text(
        _master_card_text(battle),
        reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
        parse_mode="HTML",
    )
    await callback.answer(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {rounds} rounds selected!")


# ─── Amount input (FSM) ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("btf_amount:"))
async def cb_btf_amount(callback: CallbackQuery, state: FSMContext):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await state.set_state(BattleFormStates.waiting_amount)
    await state.update_data(battle_id=battle_id, form_msg_id=callback.message.message_id)
    await callback.answer("💰 Type the bet amount below!", show_alert=True)

    prompt = await callback.message.answer(
        "<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Enter the bet amount</b>\n\n"
        "Type a number (e.g. <code>100</code>)\n"
        "<i>This is what each player will pay.</i>",
        parse_mode="HTML",
    )
    await state.update_data(amount_prompt_msg_id=prompt.message_id)


@router.message(BattleFormStates.waiting_amount, F.text)
async def msg_battle_amount(message: Message, state: FSMContext):
    data             = await state.get_data()
    battle_id        = data.get("battle_id")
    form_msg_id      = data.get("form_msg_id")
    amount_prompt_id = data.get("amount_prompt_msg_id")

    txt = (message.text or "").strip()
    if not txt.isdigit() or int(txt) < 1:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Please enter a valid amount (numbers only).\nExample: <code>100</code>",
            parse_mode="HTML",
        )
        return

    amount = int(txt)
    await state.clear()

    await _safe_delete(message.bot, message.chat.id, message.message_id)
    await _safe_delete(message.bot, message.chat.id, amount_prompt_id)

    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        return

    fee_per   = math.ceil(amount * battle["fee_percent"] / 100)
    total_per = amount + fee_per
    prize     = amount * 2

    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {
            "amount":           amount,
            "fee_per_player":   fee_per,
            "total_per_player": total_per,
            "prize_pool":       prize,
        }},
    )
    battle.update({
        "amount": amount,
        "fee_per_player": fee_per,
        "total_per_player": total_per,
        "prize_pool": prize,
    })

    try:
        await message.bot.edit_message_text(
            chat_id      = message.chat.id,
            message_id   = form_msg_id,
            text         = _master_card_text(battle),
            reply_markup = battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
            parse_mode   = "HTML",
        )
    except Exception:
        pass


# ─── Submit → send challenge ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("btf_submit:"))
async def cb_btf_submit(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger can submit.", show_alert=True)
        return
    if not all([battle["game"], battle["total_rounds"], battle["amount"]]):
        await callback.answer("❌ Fill all fields first!", show_alert=True)
        return

    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "pending_confirmation"}})
    battle["status"] = "pending_confirmation"

    await callback.message.edit_text(
        _master_card_text(battle),
        reply_markup=battle_confirm_keyboard(battle_id),
        parse_mode="HTML",
    )
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Battle challenge sent!")


# ─── Both players confirm (ATOMIC — prevents double-confirm) ─────────────────

@router.callback_query(F.data.startswith("bt_confirm:"))
async def cb_bt_confirm(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db        = get_db()
    uid       = callback.from_user.id
    uname     = callback.from_user.username or callback.from_user.first_name

    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return
    if battle["status"] != "pending_confirmation":
        await callback.answer("Not waiting for confirmation.", show_alert=True)
        return

    # Determine which field to set atomically
    if uid == battle["challenger_id"]:
        field        = "challenger_confirmed"
        already_done = battle.get("challenger_confirmed", False)
    elif uid == battle.get("opponent_id") or (
        battle.get("opponent_id") is None and
        callback.from_user.username and
        callback.from_user.username.lower() == battle["opponent_username"].lower()
    ):
        field        = "opponent_confirmed"
        already_done = battle.get("opponent_confirmed", False)
    else:
        await callback.answer("❌ You are not part of this battle.", show_alert=True)
        return

    if already_done:
        await callback.answer("✅ You already confirmed!", show_alert=True)
        return

    # ATOMIC update: only succeed if field is still False
    extra_set = {}
    if uid != battle.get("opponent_id") and field == "opponent_confirmed":
        extra_set = {"opponent_id": uid, "opponent_name": uname}

    result = await db.battles.find_one_and_update(
        {"battle_id": battle_id, field: False, "status": "pending_confirmation"},
        {"$set": {field: True, **extra_set, "updated_at": now_utc()}},
        return_document=True,
    )
    if result is None:
        # Someone else already confirmed or status changed
        await callback.answer("✅ Already confirmed!", show_alert=True)
        return

    battle = result
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Confirmed!")

    # Delete any previous "waiting for X" message
    prev_waiting_id = battle.get("waiting_confirm_msg_id")
    if prev_waiting_id:
        await _safe_delete(callback.message.bot, battle["group_id"], prev_waiting_id)
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"waiting_confirm_msg_id": None}},
        )

    if battle["challenger_confirmed"] and battle["opponent_confirmed"]:
        # Both confirmed → move to payment
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"status": "pending_payment", "waiting_confirm_msg_id": None}},
        )
        battle["status"] = "pending_payment"
        try:
            await callback.message.edit_text(
                _master_card_text(battle),
                reply_markup=None,
                parse_mode="HTML",
            )
        except Exception:
            pass
        # Send individual payment DMs to both players
        await _request_payment(battle, callback.message.bot)
    else:
        # Update master card with tick marks
        try:
            await callback.message.edit_text(
                _master_card_text(battle),
                reply_markup=battle_confirm_keyboard(battle_id),
                parse_mode="HTML",
            )
        except Exception:
            pass

        # Show who's still waiting — atomic: only one message at a time
        pending = []
        if not battle["challenger_confirmed"]:
            pending.append(f"@{battle['challenger_name']}")
        if not battle["opponent_confirmed"]:
            pending.append(f"@{battle['opponent_name']}")

        waiting_msg = await callback.message.answer(
            f"⏳ <b>Waiting for:</b> {', '.join(pending)} to confirm.",
            parse_mode="HTML",
        )
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"waiting_confirm_msg_id": waiting_msg.message_id}},
        )


@router.callback_query(F.data.startswith("bt_decline:"))
async def cb_bt_decline(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return

    uid = callback.from_user.id
    if uid not in (battle.get("challenger_id"), battle.get("opponent_id")) and \
       not (callback.from_user.username and
            callback.from_user.username.lower() == battle["opponent_username"].lower()):
        await callback.answer("You are not in this battle.", show_alert=True)
        return

    # Clean up waiting message if any
    prev_waiting_id = battle.get("waiting_confirm_msg_id")
    if prev_waiting_id:
        await _safe_delete(callback.message.bot, battle["group_id"], prev_waiting_id)

    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "declined"}})
    battle["status"] = "declined"
    try:
        await callback.message.edit_text(_master_card_text(battle), reply_markup=None, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Battle declined.")


# ─── Request payment — individual DM per player + group message ───────────────

async def _request_payment(battle: dict, bot: Bot):
    _, mentions = await _get_admin_mentions(bot, battle["group_id"])
    fee_each = battle.get("fee_per_player", 0)
    per_p    = battle.get("total_per_player", 0)
    prize    = battle.get("prize_pool", 0)
    fee_tot  = fee_each * 2
    short_id = _short_id(battle)

    # Group payment announcement
    group_text = (
        f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>BATTLE PAYMENT REQUIRED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji>  @{battle['challenger_name']}  vs  @{battle['opponent_name']}\n"
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {GAME_NAMES.get(battle['game'], battle['game'])}  ×  {battle['total_rounds']} rounds\n"
        f"🆔 <code>Battle {short_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Each player must pay:</b>\n"
        f"<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> @{battle['challenger_name']}  ›  <b>₹{per_p}</b>  (₹{battle['amount']} + ₹{fee_each} fee)\n"
        f"<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> @{battle['opponent_name']}  ›  <b>₹{per_p}</b>  (₹{battle['amount']} + ₹{fee_each} fee)\n\n"
        f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Winner prize:</b> ₹{prize}\n"
        f"<tg-emoji emoji-id='6093612746736145083'>💼</tg-emoji> <b>Platform fee:</b> ₹{fee_tot}\n\n"
        f"<tg-emoji emoji-id='6255886352164853615'>👮</tg-emoji> <b>Admins:</b> {mentions}\n"
        f"Collect payment from both players, then press <b>Approve</b>."
    )
    sent = await bot.send_message(
        battle["group_id"],
        group_text,
        reply_markup=battle_admin_approve_keyboard(battle["battle_id"]),
        parse_mode="HTML",
    )
    db = get_db()
    await db.battles.update_one(
        {"battle_id": battle["battle_id"]},
        {"$set": {"payment_message_id": sent.message_id}},
    )

    # Individual DM to each player
    dm_text_template = (
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Your Battle Payment</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>Battle {short_id}</code>\n"
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {GAME_NAMES.get(battle['game'], battle['game'])}  ×  {battle['total_rounds']} rounds\n"
        f"🆚 vs @{{opponent}}\n\n"
        f"<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> <b>You need to pay:</b> ₹{per_p}\n"
        f"  ₹{battle['amount']} (bet) + ₹{fee_each} (fee)\n\n"
        f"Pay to an admin in the group now!\n"
        f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> Winner takes: ₹{prize}"
    )

    # DM challenger
    try:
        await bot.send_message(
            battle["challenger_id"],
            dm_text_template.format(opponent=battle["opponent_name"]),
            parse_mode="HTML",
        )
    except Exception:
        pass

    # DM opponent
    opp_id = battle.get("opponent_id")
    if opp_id:
        try:
            await bot.send_message(
                opp_id,
                dm_text_template.format(opponent=battle["challenger_name"]),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Admin approves payment (ATOMIC — first admin click wins) ─────────────────

@router.callback_query(F.data.startswith("bt_admin_approve:"))
async def cb_bt_admin_approve(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db        = get_db()

    # Verify admin status first
    try:
        m = await callback.message.bot.get_chat_member(
            callback.message.chat.id, callback.from_user.id
        )
        if m.status not in ("administrator", "creator"):
            await callback.answer("❌ Only group admins can approve.", show_alert=True)
            return
    except Exception:
        await callback.answer("❌ Could not verify admin status.", show_alert=True)
        return

    admin_id   = callback.from_user.id
    admin_name = callback.from_user.username or callback.from_user.first_name

    # ATOMIC: only lock if no admin has claimed it yet AND status is still pending_payment
    result = await db.battles.find_one_and_update(
        {
            "battle_id": battle_id,
            "status": "pending_payment",
            "approving_admin_id": None,
        },
        {
            "$set": {
                "approving_admin_id":   admin_id,
                "approving_admin_name": admin_name,
                "admin_approved":       True,
                "status":               "pending_ready",
                "updated_at":           now_utc(),
            }
        },
        return_document=True,
    )

    if result is None:
        # Check if this admin is the one who already claimed it
        battle = await db.battles.find_one({"battle_id": battle_id})
        if not battle:
            await callback.answer("Battle not found.", show_alert=True)
            return
        if battle.get("approving_admin_id") == admin_id:
            await callback.answer("✅ You already approved this battle.", show_alert=True)
        elif battle.get("approving_admin_id"):
            other = battle.get("approving_admin_name", "another admin")
            await callback.answer(
                f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> @{other} already approved this battle first.",
                show_alert=True,
            )
        else:
            await callback.answer("❌ Battle is not in payment stage.", show_alert=True)
        return

    battle = result
    await callback.answer(f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Battle approved! You are the approving admin.")

    # Delete payment message
    payment_msg_id = battle.get("payment_message_id")
    if payment_msg_id:
        await _safe_delete(callback.message.bot, battle["group_id"], payment_msg_id)

    # Update master card
    await _edit_master_card(callback.message.bot, battle)

    # Send ready message to group
    ready_msg = await callback.message.bot.send_message(
        battle["group_id"],
        f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Payment Approved by @{admin_name}!</b>\n\n"
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> @{battle['challenger_name']}  vs  @{battle['opponent_name']}\n\n"
        f"<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> <b>Both players press the button below to start!</b>",
        reply_markup=battle_ready_keyboard(battle_id),
        parse_mode="HTML",
    )
    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {"ready_message_id": ready_msg.message_id}},
    )


# ─── Players press Ready (ATOMIC — prevents double-start) ─────────────────────

@router.callback_query(F.data.startswith("bt_ready:"))
async def cb_bt_ready(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db        = get_db()
    uid       = callback.from_user.id

    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "pending_ready":
        await callback.answer("Not in ready stage.", show_alert=True)
        return

    if uid == battle["challenger_id"]:
        field        = "challenger_ready"
        already_done = battle.get("challenger_ready", False)
    elif uid == battle.get("opponent_id"):
        field        = "opponent_ready"
        already_done = battle.get("opponent_ready", False)
    else:
        await callback.answer("❌ You are not in this battle.", show_alert=True)
        return

    if already_done:
        await callback.answer("✅ You're already ready!", show_alert=True)
        return

    # ATOMIC update: only if field is still False
    result = await db.battles.find_one_and_update(
        {"battle_id": battle_id, field: False, "status": "pending_ready"},
        {"$set": {field: True, "updated_at": now_utc()}},
        return_document=True,
    )
    if result is None:
        await callback.answer("✅ Already marked ready!", show_alert=True)
        return

    battle = result
    await callback.answer("<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> You're ready!")

    if battle["challenger_ready"] and battle["opponent_ready"]:
        # ATOMIC lock to prevent duplicate round start
        lock_result = await db.battles.find_one_and_update(
            {"battle_id": battle_id, "round_lock": False, "status": "pending_ready"},
            {"$set": {"round_lock": True, "status": "active", "updated_at": now_utc()}},
            return_document=True,
        )
        if lock_result is None:
            # Already starting — ignore
            return

        battle = lock_result

        # Delete ready message
        ready_msg_id = battle.get("ready_message_id")
        if ready_msg_id:
            await _safe_delete(callback.message.bot, battle["group_id"], ready_msg_id)

        # Update master card to active state
        await _edit_master_card(callback.message.bot, battle)

        # Start first round
        try:
            await _start_battle_round(battle, callback.message.bot)
        except Exception as e:
            logger.error(f"Round start error (ready): {e}")
        finally:
            # Always release lock — even if round start fails
            await db.battles.update_one(
                {"battle_id": battle_id},
                {"$set": {"round_lock": False}},
            )
    else:
        # Update ready button to show who's ready
        pending = []
        if not battle["challenger_ready"]:
            pending.append(f"@{battle['challenger_name']}")
        if not battle["opponent_ready"]:
            pending.append(f"@{battle['opponent_name']}")
        try:
            _cr = _PE_CHECK if battle['challenger_ready'] else _PE_WAIT
            _or = _PE_CHECK if battle['opponent_ready']   else _PE_WAIT
            await callback.message.edit_text(
                f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Payment Approved!</b>\n\n"
                f"<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> <b>Ready Check:</b>\n"
                f"{_cr} @{battle['challenger_name']}\n"
                f"{_or} @{battle['opponent_name']}\n\n"
                f"<i>Waiting for: {', '.join(pending)}</i>",
                reply_markup=battle_ready_keyboard(battle_id),
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Start a battle round ─────────────────────────────────────────────────────

async def _start_battle_round(battle: dict, bot: Bot):
    db           = get_db()
    battle_id    = battle["battle_id"]
    round_num    = battle.get("current_round", 0) + 1
    total_rounds = battle.get("total_rounds", 1)
    game         = battle["game"]
    game_label   = GAME_NAMES.get(game, game)

    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {"current_round": round_num, "current_round_game": game}},
    )
    battle["current_round"] = round_num

    # Send / edit live card
    live_msg_id = battle.get("live_msg_id")
    if live_msg_id:
        try:
            await bot.edit_message_text(
                chat_id    = battle["group_id"],
                message_id = live_msg_id,
                text       = _live_card_text(battle),
                parse_mode = "HTML",
            )
        except Exception:
            live_msg_id = None

    if not live_msg_id:
        live_msg = await bot.send_message(
            battle["group_id"],
            _live_card_text(battle),
            parse_mode="HTML",
        )
        live_msg_id = live_msg.message_id
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"live_msg_id": live_msg_id}},
        )

    # Alternate first turn each round:
    # Odd rounds  (1, 3, 5…) → challenger goes first
    # Even rounds (2, 4, 6…) → opponent goes first
    if round_num % 2 == 1:
        p1_id, p1_name = battle["challenger_id"], battle["challenger_name"]
        p2_id, p2_name = battle["opponent_id"],   battle["opponent_name"]
    else:
        p1_id, p1_name = battle["opponent_id"],   battle["opponent_name"]
        p2_id, p2_name = battle["challenger_id"], battle["challenger_name"]

    # Start the actual match — retry once on failure (e.g. Telegram rate limit)
    from handlers.match import start_match
    match_started = False
    last_err      = None
    for attempt in range(2):
        try:
            await start_match(
                bot          = bot,
                group_id     = battle["group_id"],
                player1_id   = p1_id,
                player1_name = p1_name,
                player2_id   = p2_id,
                player2_name = p2_name,
                game         = game,
                battle_id    = battle_id,
                battle_round = round_num,
            )
            match_started = True
            break
        except Exception as err:
            last_err = err
            logger.error(f"start_match attempt {attempt + 1} failed (battle={battle_id} round={round_num}): {err}")
            if attempt == 0:
                await asyncio.sleep(2)

    if not match_started:
        logger.error(f"start_match failed after 2 attempts for battle={battle_id} round={round_num}: {last_err}")
        try:
            await bot.send_message(
                battle["group_id"],
                f"⚠️ <b>Round {round_num} could not start</b> (technical error).\n\n"
                f"Please use /cancel <code>{battle_id}</code> and start a new battle.\n"
                f"Sorry for the inconvenience! 🙏",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Round finished callback (called by match handler) ────────────────────────

async def on_battle_round_finished(
    battle_id: str,
    match_id: str,
    winner_id,
    is_draw: bool,
    bot: Bot,
):
    """
    Called by match.py after every battle round ends.
    match.py already shows result + 5-sec countdown + deletes game board.
    This function: records result, updates live card, starts next round or finishes battle.
    """
    db     = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        return

    # Derive winner_name from battle doc
    if winner_id is None:
        winner_name = None
    elif winner_id == battle["challenger_id"]:
        winner_name = battle["challenger_name"]
    else:
        winner_name = battle["opponent_name"]

    round_num    = battle.get("current_round", 0)
    total_rounds = battle.get("total_rounds", 1)

    # Record round result
    round_result = {
        "round":     round_num,
        "winner_id": winner_id,
        "is_draw":   is_draw,
    }

    inc_fields = {}
    if is_draw:
        inc_fields["round_draws"] = 1
    elif winner_id == battle["challenger_id"]:
        inc_fields["p1_wins"] = 1
    else:
        inc_fields["p2_wins"] = 1

    await db.battles.update_one(
        {"battle_id": battle_id},
        {
            "$inc":  inc_fields,
            "$push": {"round_results": round_result},
        },
    )
    battle = await db.battles.find_one({"battle_id": battle_id})

    p1_wins      = battle.get("p1_wins", 0)
    p2_wins      = battle.get("p2_wins", 0)
    rounds_played = round_num

    if is_draw:
        result_line = f"<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>Round {round_num} — Draw!</b>"
    elif winner_id == battle["challenger_id"]:
        result_line = f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Round {round_num} — @{battle['challenger_name']} wins!</b>"
    else:
        result_line = f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Round {round_num} — @{battle['opponent_name']} wins!</b>"

    # Update live card with round result
    await _edit_live_card(bot, battle, result_line)

    # Check if battle is decided
    majority    = (total_rounds // 2) + 1
    battle_over = rounds_played >= total_rounds
    p1_clinched = p1_wins >= majority
    p2_clinched = p2_wins >= majority

    if p1_clinched or p2_clinched or battle_over:
        if p1_wins > p2_wins:
            final_winner_id   = battle["challenger_id"]
            final_winner_name = battle["challenger_name"]
            final_is_draw     = False
        elif p2_wins > p1_wins:
            final_winner_id   = battle["opponent_id"]
            final_winner_name = battle["opponent_name"]
            final_is_draw     = False
        else:
            final_winner_id   = None
            final_winner_name = None
            final_is_draw     = True

        await _finish_battle(battle, final_winner_id, final_winner_name, final_is_draw, bot)
    else:
        # Start next round — use current_round as idempotency key.
        # _start_battle_round increments current_round immediately, so any
        # duplicate call for the same round_num will find a mismatch and stop.
        battle = await db.battles.find_one({"battle_id": battle_id})
        if not battle or battle["status"] != "active":
            return
        guard = await db.battles.find_one_and_update(
            {"battle_id": battle_id, "current_round": round_num, "status": "active"},
            {"$set": {"updated_at": now_utc()}},
            return_document=True,
        )
        if guard is None:
            # Another call already advanced past this round
            return
        try:
            await _start_battle_round(battle, bot)
        except Exception as e:
            logger.error(f"Round start error (round_finished): {e}")


# ─── Finish battle ────────────────────────────────────────────────────────────

async def _finish_battle(battle: dict, winner_id, winner_name, is_draw: bool, bot: Bot):
    db        = get_db()
    battle_id = battle["battle_id"]
    prize     = battle.get("prize_pool", 0)

    if is_draw:
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"status": "draw_pending", "winner_id": None, "winner_name": None}},
        )
        battle = await db.battles.find_one({"battle_id": battle_id})
        await _edit_master_card(bot, battle, _draw_keyboard(battle_id))

        await bot.send_message(
            battle["group_id"],
            f"<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>IT'S A DRAW!</b>\n\n"
            f"@{battle['challenger_name']} vs @{battle['opponent_name']}\n"
            f"Prize: ₹{prize}\n\n"
            f"<b>Admin:</b> Choose to split or rematch below!",
            reply_markup=_draw_keyboard(battle_id),
            parse_mode="HTML",
        )
    else:
        await _update_battle_stats(
            battle["challenger_id"], battle["opponent_id"], winner_id, False
        )
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {
                "status":      "pending_payout",
                "winner_id":   winner_id,
                "winner_name": winner_name,
            }},
        )
        battle = await db.battles.find_one({"battle_id": battle_id})
        await _edit_master_card(bot, battle)

        admin_name         = battle.get("approving_admin_name", "Admin")
        approving_admin_id = battle.get("approving_admin_id")
        p1_wins            = battle.get("p1_wins", 0)
        p2_wins            = battle.get("p2_wins", 0)
        r_draws            = battle.get("round_draws", 0)
        total_rounds       = battle.get("total_rounds", 0)

        draws_str  = f"  ({r_draws} draw{'s' if r_draws != 1 else ''})" if r_draws else ""
        score_line = (
            f"@{battle['challenger_name']} <b>{p1_wins}</b> — "
            f"<b>{p2_wins}</b> @{battle['opponent_name']}{draws_str}"
        )

        payout_text = (
            f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>BATTLE OVER!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> {score_line}\n\n"
            f"<tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji> <b>Congratulations @{winner_name}!</b>\n"
            f"<tg-emoji emoji-id='5440539497383087970'>🥇</tg-emoji> You won the battle!\n"
            f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Prize: ₹{prize}</b>\n\n"
            f"📩 @{winner_name} — contact @{admin_name} for your payment.\n\n"
            f"<i>@{admin_name}: click below once payment is sent ⬇️</i>"
        )
        payout_msg = await bot.send_message(
            battle["group_id"],
            payout_text,
            reply_markup=battle_payout_done_keyboard(battle_id),
            parse_mode="HTML",
        )
        # Store payout message ID so we can edit it when payment is done
        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"payout_msg_id": payout_msg.message_id}},
        )

        # DM winner
        try:
            await bot.send_message(
                winner_id,
                f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Congratulations! You won the battle!</b>\n\n"
                f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Prize: <b>₹{prize}</b>\n\n"
                f"📩 Please contact @{admin_name} to collect your payment.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Draw: Split ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_split:"))
async def cb_bt_split(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "draw_pending":
        await callback.answer("Not in draw state.", show_alert=True)
        return

    approving_admin_id = battle.get("approving_admin_id")
    if approving_admin_id and callback.from_user.id != approving_admin_id:
        await callback.answer("❌ Only the approving admin can decide.", show_alert=True)
        return
    if not approving_admin_id:
        try:
            m = await callback.message.bot.get_chat_member(battle["group_id"], callback.from_user.id)
            if m.status not in ("administrator", "creator"):
                await callback.answer("❌ Only admins can decide.", show_alert=True)
                return
        except Exception:
            await callback.answer("❌ Could not verify admin status.", show_alert=True)
            return

    split_amount = battle.get("prize_pool", 0) // 2
    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {"status": "completed", "updated_at": now_utc()}},
    )
    battle["status"] = "completed"
    battle["winner_name"] = "DRAW — Split"

    try:
        await callback.message.edit_text(
            f"<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>Prize Split!</b>\n\n"
            f"Each player receives ₹{split_amount}\n"
            f"Decided by @{callback.from_user.username or callback.from_user.first_name}",
            reply_markup=None,
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Prize will be split!")

    # Update master card
    await _edit_master_card(callback.message.bot, battle)

    # DM both players
    for pid, pname, opp in [
        (battle["challenger_id"], battle["challenger_name"], battle["opponent_name"]),
        (battle.get("opponent_id"), battle["opponent_name"], battle["challenger_name"]),
    ]:
        if not pid:
            continue
        try:
            await callback.message.bot.send_message(
                pid,
                f"<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> <b>Battle Draw — Prize Split!</b>\n\n"
                f"You and @{opp} each receive ₹{split_amount}.\n"
                f"Admin will send your share shortly!",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Draw: Rematch ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_rematch:"))
async def cb_bt_rematch(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "draw_pending":
        await callback.answer("Not in draw state.", show_alert=True)
        return

    approving_admin_id = battle.get("approving_admin_id")
    if approving_admin_id and callback.from_user.id != approving_admin_id:
        await callback.answer("❌ Only the approving admin can offer rematch.", show_alert=True)
        return
    if not approving_admin_id:
        try:
            m = await callback.message.bot.get_chat_member(battle["group_id"], callback.from_user.id)
            if m.status not in ("administrator", "creator"):
                await callback.answer("❌ Only admins can offer rematch.", show_alert=True)
                return
        except Exception:
            await callback.answer("❌ Could not verify admin.", show_alert=True)
            return

    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {
            "status":                     "draw_rematch_pending",
            "rematch_challenger_confirm": False,
            "rematch_opponent_confirm":   False,
        }},
    )
    await callback.answer("<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> Rematch proposed!")
    battle = await db.battles.find_one({"battle_id": battle_id})

    try:
        await callback.message.bot.edit_message_text(
            chat_id      = battle["group_id"],
            message_id   = battle.get("form_message_id"),
            text         = _master_card_text(battle) +
                           f"\n\n<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> <b>Rematch Proposed!</b>\n"
                           f"@{battle['challenger_name']} and @{battle['opponent_name']} "
                           f"must both confirm below.",
            reply_markup = _rematch_confirm_keyboard(battle_id, False, False),
            parse_mode   = "HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("bt_rematch_ok:"))
async def cb_bt_rematch_ok(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db        = get_db()
    uid       = callback.from_user.id

    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "draw_rematch_pending":
        await callback.answer("Not waiting for rematch confirmation.", show_alert=True)
        return

    if uid == battle["challenger_id"]:
        field        = "rematch_challenger_confirm"
        already_done = battle.get(field, False)
    elif uid == battle.get("opponent_id"):
        field        = "rematch_opponent_confirm"
        already_done = battle.get(field, False)
    else:
        await callback.answer("You are not in this battle.", show_alert=True)
        return

    if already_done:
        await callback.answer("✅ Already confirmed!", show_alert=True)
        return

    result = await db.battles.find_one_and_update(
        {"battle_id": battle_id, field: False, "status": "draw_rematch_pending"},
        {"$set": {field: True, "updated_at": now_utc()}},
        return_document=True,
    )
    if result is None:
        await callback.answer("✅ Already confirmed!", show_alert=True)
        return

    battle = result
    c_confirmed = battle.get("rematch_challenger_confirm", False)
    o_confirmed = battle.get("rematch_opponent_confirm", False)
    await callback.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Rematch confirmed!")

    if c_confirmed and o_confirmed:
        lock_result = await db.battles.find_one_and_update(
            {"battle_id": battle_id, "round_lock": False, "status": "draw_rematch_pending"},
            {"$set": {
                "status":                     "active",
                "total_rounds":               battle["total_rounds"] + 1,
                "rematch_challenger_confirm": False,
                "rematch_opponent_confirm":   False,
                "round_lock":                 True,
            }},
            return_document=True,
        )
        if lock_result is None:
            return
        battle = lock_result

        try:
            await callback.message.bot.edit_message_text(
                chat_id      = battle["group_id"],
                message_id   = battle.get("form_message_id"),
                text         = _master_card_text(battle),
                reply_markup = None,
                parse_mode   = "HTML",
            )
        except Exception:
            pass

        try:
            await _start_battle_round(battle, callback.message.bot)
        except Exception as e:
            logger.error(f"Round start error (rematch): {e}")
        finally:
            # Always release lock — even if round start throws
            await db.battles.update_one(
                {"battle_id": battle_id},
                {"$set": {"round_lock": False}},
            )
    else:
        try:
            await callback.message.bot.edit_message_reply_markup(
                chat_id      = battle["group_id"],
                message_id   = battle.get("form_message_id"),
                reply_markup = _rematch_confirm_keyboard(battle_id, c_confirmed, o_confirmed),
            )
        except Exception:
            pass


# ─── Admin marks payout done (FIRST-CLICK-ONLY) ───────────────────────────────

@router.callback_query(F.data.startswith("bt_payment_done:"))
async def cb_bt_payment_done(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db        = get_db()
    uid       = callback.from_user.id

    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "pending_payout":
        await callback.answer("Already done or wrong state.", show_alert=True)
        return

    approving_admin_id = battle.get("approving_admin_id")
    if approving_admin_id and uid != approving_admin_id:
        other = battle.get("approving_admin_name", "another admin")
        await callback.answer(
            f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Only @{other} (who approved this battle) can mark payment sent.",
            show_alert=True,
        )
        return
    if not approving_admin_id:
        try:
            m = await callback.message.bot.get_chat_member(battle["group_id"], uid)
            if m.status not in ("administrator", "creator"):
                await callback.answer("❌ Only admins can mark payment sent.", show_alert=True)
                return
        except Exception:
            await callback.answer("❌ Could not verify admin status.", show_alert=True)
            return

    # ATOMIC: only transition from pending_payout → completed once
    result = await db.battles.find_one_and_update(
        {"battle_id": battle_id, "status": "pending_payout"},
        {"$set": {"status": "completed", "updated_at": now_utc()}},
        return_document=True,
    )
    if result is None:
        await callback.answer("✅ Payment already confirmed!", show_alert=True)
        return

    battle      = result
    admin_name  = callback.from_user.username or callback.from_user.first_name
    winner_name = battle.get("winner_name", "—")
    prize       = battle.get("prize_pool", "?")

    await callback.answer("✅ Payment confirmed!")

    # Edit the payout message to show payment done (remove button, update text)
    payout_msg_id = battle.get("payout_msg_id") or (
        callback.message.message_id if callback.message else None
    )
    if payout_msg_id:
        try:
            await callback.message.bot.edit_message_text(
                chat_id    = battle["group_id"],
                message_id = payout_msg_id,
                text       = (
                    f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>BATTLE OVER!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<tg-emoji emoji-id='5440539497383087970'>🥇</tg-emoji> <b>Winner: @{winner_name}</b>\n"
                    f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Prize: ₹{prize}</b>\n\n"
                    f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Payment Done!</b> "
                    f"Sent by @{admin_name}\n"
                    f"<tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji> <i>GG and well played!</i>"
                ),
                reply_markup = None,
                parse_mode   = "HTML",
            )
        except Exception:
            pass

    # Update master card to show completed state
    battle["status"]       = "completed"
    battle["winner_name"]  = winner_name
    await _edit_master_card(callback.message.bot, battle)

    # DM the winner
    winner_id = battle.get("winner_id")
    if winner_id:
        try:
            await callback.message.bot.send_message(
                winner_id,
                f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Payment Sent!</b>\n\n"
                f"@{admin_name} has sent you ₹{prize}.\n"
                f"Please check your UPI / wallet!\n\n"
                f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> GG and well played! <tg-emoji emoji-id='4956596167451346576'>🎉</tg-emoji>",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── Update battle stats ──────────────────────────────────────────────────────

async def _update_battle_stats(p1_id: int, p2_id: int, winner_id, is_draw: bool):
    db = get_db()
    if is_draw or winner_id is None:
        await db.users.update_many(
            {"user_id": {"$in": [p1_id, p2_id]}},
            {"$inc": {"battle_draws": 1, "total_battles": 1}},
        )
    elif winner_id == p1_id:
        await db.users.update_one({"user_id": p1_id}, {"$inc": {"battle_wins": 1, "total_battles": 1}})
        await db.users.update_one({"user_id": p2_id}, {"$inc": {"battle_losses": 1, "total_battles": 1}})
    else:
        await db.users.update_one({"user_id": p2_id}, {"$inc": {"battle_wins": 1, "total_battles": 1}})
        await db.users.update_one({"user_id": p1_id}, {"$inc": {"battle_losses": 1, "total_battles": 1}})
