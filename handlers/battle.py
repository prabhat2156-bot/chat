"""
Paid Battle System (/battle @opponent)

Flow:
  1. /battle @opponent → interactive form (game / rounds / amount)
  2. Challenger submits → both players confirm
  3. Bot tags group admins to collect payment
  4. Admin clicks "Payment Received" → both players confirm Ready
  5. Rounds loop (each round = one standalone match via match.py)
     - After each round: loser picks next game or same game
  6. Final winner announced → bot asks for UPI ID
  7. Bot tags approving admin with payout info + "Payment Sent" button
  8. Admin confirms → bot congratulates winner
"""
import logging
import math

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
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
    battle_next_round_keyboard,
    battle_next_game_keyboard,
    battle_next_accept_keyboard,
    battle_payout_done_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


# ─── FSM States ──────────────────────────────────────────────────────────────

class BattleFormStates(StatesGroup):
    waiting_amount = State()
    waiting_upi    = State()


# ─── Text helpers ─────────────────────────────────────────────────────────────

def _form_text(battle: dict) -> str:
    game_label   = GAME_NAMES.get(battle["game"], "—") if battle["game"] else "—"
    rounds_label = str(battle["total_rounds"]) if battle["total_rounds"] else "—"
    amount_label = f"₹{battle['amount']}" if battle["amount"] else "—"
    return (
        "⚔️ <b>Battle Request Form</b>\n\n"
        f"👤 <b>Challenger</b>  :  @{battle['challenger_name']}\n"
        f"🎯 <b>Opponent</b>     :  @{battle['opponent_name']}\n"
        f"🎮 <b>Game</b>           :  {game_label}\n"
        f"🔢 <b>Rounds</b>       :  {rounds_label}\n"
        f"💰 <b>Amount</b>      :  {amount_label}\n\n"
        "Fill in the fields below, then press <b>Send Challenge</b>."
    )


def _confirm_text(battle: dict) -> str:
    fee_each = battle["fee_per_player"]
    per_p    = battle["total_per_player"]
    prize    = battle["prize_pool"]
    return (
        "⚔️ <b>Battle Challenge!</b>\n\n"
        f"👤 <b>Challenger</b>  :  @{battle['challenger_name']}\n"
        f"🎯 <b>Opponent</b>     :  @{battle['opponent_name']}\n"
        f"🎮 <b>Game</b>           :  {GAME_NAMES.get(battle['game'], battle['game'])}\n"
        f"🔢 <b>Rounds</b>       :  {battle['total_rounds']}\n"
        f"💰 <b>Bet Amount</b>  :  ₹{battle['amount']} each\n"
        f"📊 <b>Fee ({battle['fee_percent']}%)</b>  :  ₹{fee_each} each\n"
        f"💵 <b>You Pay</b>      :  ₹{per_p} each\n"
        f"🏆 <b>Prize Pool</b>  :  ₹{prize} (goes to winner)\n\n"
        "Both players must <b>Confirm</b> to proceed."
    )


def _payment_text(battle: dict, admin_mentions: str) -> str:
    per_p    = battle["total_per_player"]
    fee_each = battle["fee_per_player"]
    prize    = battle["prize_pool"]
    fee_tot  = fee_each * 2
    return (
        "💰 <b>Battle Payment Required!</b>\n\n"
        f"⚔️  @{battle['challenger_name']}  vs  @{battle['opponent_name']}\n"
        f"🎮 {GAME_NAMES.get(battle['game'], battle['game'])}  ×  {battle['total_rounds']} rounds\n\n"
        "<b>Each player must pay:</b>\n"
        f"• @{battle['challenger_name']}  →  <b>₹{per_p}</b>  (₹{battle['amount']} bet + ₹{fee_each} fee)\n"
        f"• @{battle['opponent_name']}  →  <b>₹{per_p}</b>  (₹{battle['amount']} bet + ₹{fee_each} fee)\n\n"
        f"🏆 Winner receives: <b>₹{prize}</b>\n"
        f"💼 Platform fee (admin keeps): <b>₹{fee_tot}</b>\n\n"
        f"{admin_mentions}\n"
        "👆 Any admin — collect payment from both players, then click <b>Approve</b>."
    )


# ─── DB / Telegram helpers ────────────────────────────────────────────────────

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
    """Returns (list_of_admin_ids, mention_string)."""
    try:
        admins = await bot.get_chat_administrators(group_id)
        ids, parts = [], []
        for a in admins:
            if a.user.is_bot:
                continue
            ids.append(a.user.id)
            if a.user.username:
                parts.append(f"@{a.user.username}")
            else:
                parts.append(f"<a href='tg://user?id={a.user.id}'>{a.user.first_name}</a>")
        return ids, (" ".join(parts) if parts else "(no admins found)")
    except Exception as e:
        logger.warning(f"Could not get admins for {group_id}: {e}")
        return [], "(could not fetch admins)"


# ─── /battle command ─────────────────────────────────────────────────────────

@router.message(Command("battle"))
async def cmd_battle(message: Message):
    if message.chat.type == "private":
        await message.answer("⚔️ Use /battle in a group, not in DM.")
        return

    if not message.from_user:
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "⚔️ <b>Paid Battle — Usage</b>\n\n"
            "<code>/battle @opponent</code>\n\n"
            "Set a bet, pick a game and rounds — both confirm — pay the admin — and fight!\n"
            "🏆 Winner takes the full prize pool.",
        )
        return

    raw = args[1].lstrip("@")
    if not raw:
        await message.answer("❌ Mention an opponent:  <code>/battle @username</code>")
        return

    challenger = message.from_user
    db = get_db()

    # Resolve opponent from DB or entity
    opponent_id   = None
    opponent_name = raw
    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention" and ent.user:
                if ent.user.id == challenger.id:
                    await message.answer("❌ You can't battle yourself.")
                    return
                if ent.user.is_bot:
                    await message.answer("❌ You can't battle a bot.")
                    return
                opponent_id   = ent.user.id
                opponent_name = ent.user.username or ent.user.first_name
                break

    if opponent_id is None:
        doc = await db.users.find_one({"username": {"$regex": f"^{raw}$", "$options": "i"}})
        if doc:
            opponent_id   = doc["user_id"]
            opponent_name = doc.get("username") or doc.get("first_name") or raw

    if opponent_id == challenger.id:
        await message.answer("❌ You can't battle yourself.")
        return

    # Check existing active battle in this group
    existing = await db.battles.find_one({
        "group_id": message.chat.id,
        "status": {"$nin": ["completed", "cancelled", "declined"]},
        "$or": [{"challenger_id": challenger.id}, {"opponent_id": challenger.id}],
    })
    if existing:
        await message.answer("❌ You already have an active /battle in this group. Finish it first.")
        return

    fee_pct = await _get_fee_percent(message.chat.id)
    challenger_name = challenger.username or challenger.first_name

    battle = BattlePaidModel.new(
        group_id        = message.chat.id,
        challenger_id   = challenger.id,
        challenger_name = challenger_name,
        opponent_id     = opponent_id,
        opponent_username = opponent_name,
        form_message_id = message.message_id,
        fee_percent     = fee_pct,
    )
    await db.battles.insert_one(battle)

    sent = await message.answer(
        _form_text(battle),
        reply_markup=battle_form_keyboard(
            battle["battle_id"], battle["game"],
            battle["total_rounds"], battle["amount"],
        ),
    )
    await db.battles.update_one(
        {"battle_id": battle["battle_id"]},
        {"$set": {"form_message_id": sent.message_id}},
    )


# ─── Form: back ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "btf_noop")
async def cb_btf_noop(callback: CallbackQuery):
    await callback.answer("⏳ Fill all fields first (Game, Rounds, Amount).", show_alert=True)


@router.callback_query(F.data.startswith("btf_cancel:"))
async def cb_btf_cancel(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger can cancel.", show_alert=True)
        return
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "cancelled"}})
    await callback.message.edit_text("❌ <b>Battle form cancelled.</b>")
    await callback.answer()


@router.callback_query(F.data.startswith("btf_back:"))
async def cb_btf_back(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await callback.message.edit_text(
        _form_text(battle),
        reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
    )
    await callback.answer()


# ─── Form: game selection ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("btf_game:"))
async def cb_btf_game(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await callback.message.edit_text(
        "🎮 <b>Select a Game</b>",
        reply_markup=battle_game_select_keyboard(battle_id),
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
        _form_text(battle),
        reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
    )
    await callback.answer(f"✅ {GAME_NAMES.get(game, game)}")


# ─── Form: rounds selection ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("btf_rounds:"))
async def cb_btf_rounds(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or callback.from_user.id != battle["challenger_id"]:
        await callback.answer("Only the challenger fills this form.", show_alert=True)
        return
    await callback.message.edit_text(
        "🔢 <b>Select Number of Rounds</b>\n\nEach round = 1 match. Player with most wins takes the prize.",
        reply_markup=battle_rounds_keyboard(battle_id),
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
        _form_text(battle),
        reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
    )
    await callback.answer(f"✅ Rounds: {rounds}")


# ─── Form: amount input (FSM) ─────────────────────────────────────────────────

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
    await callback.answer("💰 Type the bet amount (e.g. 50)", show_alert=True)
    await callback.message.answer("💰 <b>Type the bet amount (numbers only)</b>\nExample: <code>50</code>")


@router.message(BattleFormStates.waiting_amount, F.text)
async def msg_battle_amount(message: Message, state: FSMContext):
    data       = await state.get_data()
    battle_id  = data.get("battle_id")
    form_msg_id = data.get("form_msg_id")

    txt = (message.text or "").strip()
    if not txt.isdigit() or int(txt) < 1:
        await message.answer("❌ Enter a valid positive number. Example: <code>50</code>")
        return

    amount = int(txt)
    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass

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
            "amount": amount,
            "fee_per_player": fee_per,
            "total_per_player": total_per,
            "prize_pool": prize,
        }},
    )
    battle.update({"amount": amount, "fee_per_player": fee_per,
                   "total_per_player": total_per, "prize_pool": prize})

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=form_msg_id,
            text=_form_text(battle),
            reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
        )
    except Exception:
        await message.answer(
            _form_text(battle),
            reply_markup=battle_form_keyboard(battle_id, battle["game"], battle["total_rounds"], battle["amount"]),
        )


# ─── Form: submit → send challenge ───────────────────────────────────────────

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
    await callback.message.edit_text(
        _confirm_text(battle),
        reply_markup=battle_confirm_keyboard(battle_id),
    )
    await callback.answer("✅ Challenge sent!")


# ─── Both players confirm ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_confirm:"))
async def cb_bt_confirm(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return
    if battle["status"] != "pending_confirmation":
        await callback.answer("Not waiting for confirmation.", show_alert=True)
        return

    uid  = callback.from_user.id
    uname = callback.from_user.username or callback.from_user.first_name

    if uid == battle["challenger_id"]:
        if battle["challenger_confirmed"]:
            await callback.answer("You already confirmed!", show_alert=True)
            return
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"challenger_confirmed": True}})
        battle["challenger_confirmed"] = True

    elif uid == battle.get("opponent_id") or (
        battle.get("opponent_id") is None and
        callback.from_user.username and
        callback.from_user.username.lower() == battle["opponent_username"].lower()
    ):
        if battle["opponent_confirmed"]:
            await callback.answer("You already confirmed!", show_alert=True)
            return
        # Resolve opponent_id if not already set
        if not battle.get("opponent_id"):
            await db.battles.update_one(
                {"battle_id": battle_id},
                {"$set": {"opponent_id": uid, "opponent_name": uname}},
            )
            battle["opponent_id"]   = uid
            battle["opponent_name"] = uname
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"opponent_confirmed": True}})
        battle["opponent_confirmed"] = True
    else:
        await callback.answer("❌ You are not part of this battle.", show_alert=True)
        return

    await callback.answer("✅ Confirmed!")

    battle = await db.battles.find_one({"battle_id": battle_id})
    if battle["challenger_confirmed"] and battle["opponent_confirmed"]:
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "pending_payment"}})
        await callback.message.edit_reply_markup(reply_markup=None)
        await _request_payment(battle, callback.message.bot)
    else:
        pending = []
        if not battle["challenger_confirmed"]:
            pending.append(f"@{battle['challenger_name']}")
        if not battle["opponent_confirmed"]:
            pending.append(f"@{battle['opponent_name']}")
        await callback.message.answer(f"⏳ Waiting for: {', '.join(pending)} to confirm.")


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

    name = callback.from_user.username or callback.from_user.first_name
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "cancelled"}})
    await callback.message.edit_text(f"❌ <b>Battle Cancelled</b>\n\n@{name} declined.")
    await callback.answer("Battle cancelled.")


# ─── Request payment from group admins ───────────────────────────────────────

async def _request_payment(battle: dict, bot: Bot):
    _, mentions = await _get_admin_mentions(bot, battle["group_id"])
    sent = await bot.send_message(
        battle["group_id"],
        _payment_text(battle, mentions),
        reply_markup=battle_admin_approve_keyboard(battle["battle_id"]),
    )
    db = get_db()
    await db.battles.update_one(
        {"battle_id": battle["battle_id"]},
        {"$set": {"payment_message_id": sent.message_id}},
    )


# ─── Admin approves payment ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_admin_approve:"))
async def cb_bt_admin_approve(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return
    if battle["status"] != "pending_payment":
        await callback.answer("Not in payment stage.", show_alert=True)
        return

    # Verify admin
    try:
        m = await callback.message.bot.get_chat_member(battle["group_id"], callback.from_user.id)
        if m.status not in ("administrator", "creator"):
            await callback.answer("❌ Only group admins can approve.", show_alert=True)
            return
    except Exception:
        await callback.answer("❌ Could not verify admin status.", show_alert=True)
        return

    admin_name = callback.from_user.username or callback.from_user.first_name
    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {
            "status": "pending_ready",
            "admin_approved": True,
            "approving_admin_id": callback.from_user.id,
            "approving_admin_name": admin_name,
        }},
    )
    await callback.answer(f"✅ Approved by @{admin_name}!")
    await callback.message.edit_reply_markup(reply_markup=None)

    battle = await db.battles.find_one({"battle_id": battle_id})
    await callback.message.bot.send_message(
        battle["group_id"],
        f"✅ <b>Payment Approved by @{admin_name}!</b>\n\n"
        f"⚔️  @{battle['challenger_name']}  vs  @{battle['opponent_name']}\n"
        f"🎮 {GAME_NAMES.get(battle['game'], battle['game'])}  ×  {battle['total_rounds']} rounds\n"
        f"🏆 Prize Pool: <b>₹{battle['prize_pool']}</b>\n\n"
        "Both players press <b>⚡ I'm Ready!</b> to start!",
        reply_markup=battle_ready_keyboard(battle_id),
    )


# ─── Both Ready → Start Round 1 ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_ready:"))
async def cb_bt_ready(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "pending_ready":
        await callback.answer("Not in ready phase.", show_alert=True)
        return

    uid = callback.from_user.id
    if uid == battle["challenger_id"]:
        if battle["challenger_ready"]:
            await callback.answer("Already ready!", show_alert=True)
            return
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"challenger_ready": True}})
        battle["challenger_ready"] = True
    elif uid == battle.get("opponent_id"):
        if battle["opponent_ready"]:
            await callback.answer("Already ready!", show_alert=True)
            return
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"opponent_ready": True}})
        battle["opponent_ready"] = True
    else:
        await callback.answer("You are not in this battle.", show_alert=True)
        return

    await callback.answer("⚡ Ready!")
    battle = await db.battles.find_one({"battle_id": battle_id})

    if battle["challenger_ready"] and battle["opponent_ready"]:
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "active"}})
        await callback.message.edit_text(
            f"⚡ <b>Battle Starting!</b>\n\n"
            f"@{battle['challenger_name']}  vs  @{battle['opponent_name']}\n"
            f"🎮 {GAME_NAMES.get(battle['game'], battle['game'])}  ×  {battle['total_rounds']} rounds\n"
            f"🏆 Prize: ₹{battle['prize_pool']}",
        )
        await _start_battle_round(battle, callback.message.bot)
    else:
        pending = []
        if not battle["challenger_ready"]:
            pending.append(f"@{battle['challenger_name']}")
        if not battle["opponent_ready"]:
            pending.append(f"@{battle['opponent_name']}")
        await callback.message.answer(f"⚡ Waiting for: {', '.join(pending)}")


# ─── Start a round ────────────────────────────────────────────────────────────

async def _start_battle_round(battle: dict, bot: Bot):
    """Create a standalone match for the current round."""
    from handlers.match import start_match

    battle_id  = battle["battle_id"]
    round_num  = battle["current_round"] + 1
    game       = battle.get("current_round_game") or battle["game"]
    group_id   = battle["group_id"]

    db = get_db()
    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {"current_round": round_num, "current_round_game": game, "current_match_id": None}},
    )
    battle["current_round"] = round_num

    await bot.send_message(
        group_id,
        f"🥊 <b>Round {round_num} of {battle['total_rounds']}</b>\n\n"
        f"@{battle['challenger_name']}  vs  @{battle['opponent_name']}\n"
        f"🎮 <b>{GAME_NAMES.get(game, game)}</b>\n"
        f"📊 Score:  {battle['p1_wins']} – {battle['p2_wins']}",
    )

    match_id = await start_match(
        bot          = bot,
        group_id     = group_id,
        player1_id   = battle["challenger_id"],
        player1_name = battle["challenger_name"],
        player2_id   = battle["opponent_id"],
        player2_name = battle["opponent_name"],
        game         = game,
        battle_id    = battle_id,
        battle_round = round_num,
    )
    if match_id:
        await db.battles.update_one({"battle_id": battle_id}, {"$set": {"current_match_id": match_id}})


# ─── Called by match.py when a round ends ────────────────────────────────────

async def on_battle_round_finished(battle_id: str, match_id: str, winner_id, is_draw: bool, bot: Bot):
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        return

    round_num    = battle["current_round"]
    p1_id        = battle["challenger_id"]
    p1_name      = battle["challenger_name"]
    p2_id        = battle["opponent_id"]
    p2_name      = battle["opponent_name"]
    group_id     = battle["group_id"]
    total_rounds = battle["total_rounds"]

    p1_wins  = battle["p1_wins"]
    p2_wins  = battle["p2_wins"]
    r_draws  = battle["round_draws"]

    if is_draw:
        r_draws += 1
        loser_id = p1_id
    elif winner_id == p1_id:
        p1_wins += 1
        loser_id = p2_id
    else:
        p2_wins += 1
        loser_id = p1_id

    await db.battles.update_one(
        {"battle_id": battle_id},
        {
            "$set": {
                "p1_wins": p1_wins, "p2_wins": p2_wins,
                "round_draws": r_draws, "current_match_id": None,
                "next_game_proposed": None, "next_game_proposer_id": None,
            },
            "$push": {"round_results": {
                "round": round_num, "winner_id": winner_id,
                "is_draw": is_draw,
                "game": battle.get("current_round_game") or battle["game"],
            }},
        },
    )
    battle.update({"p1_wins": p1_wins, "p2_wins": p2_wins, "round_draws": r_draws})

    score = (
        f"📊 Score:  <b>@{p1_name}</b> {p1_wins} – {p2_wins} <b>@{p2_name}</b>"
        + (f"  ({r_draws} draw{'s' if r_draws != 1 else ''})" if r_draws else "")
    )

    if is_draw:
        result_line = "🤝 <b>This round is a Draw!</b>"
    elif winner_id == p1_id:
        result_line = f"🏆 <b>@{p1_name} wins Round {round_num}!</b>"
    else:
        result_line = f"🏆 <b>@{p2_name} wins Round {round_num}!</b>"

    # Check if battle is over (majority or all rounds played)
    majority = total_rounds // 2 + 1
    battle_over = (p1_wins >= majority or p2_wins >= majority or round_num >= total_rounds)

    if battle_over:
        if p1_wins > p2_wins:
            final_winner_id, final_winner_name = p1_id, p1_name
        elif p2_wins > p1_wins:
            final_winner_id, final_winner_name = p2_id, p2_name
        else:
            final_winner_id, final_winner_name = p1_id, p1_name  # challenger wins on tie

        await db.battles.update_one(
            {"battle_id": battle_id},
            {"$set": {"status": "pending_upi", "winner_id": final_winner_id, "winner_name": final_winner_name}},
        )
        await _update_battle_stats(p1_id, p2_id, final_winner_id, p1_wins == p2_wins)

        await bot.send_message(
            group_id,
            f"🥊 <b>Round {round_num} Result</b>\n{result_line}\n{score}",
        )
        battle.update({"winner_id": final_winner_id, "winner_name": final_winner_name})
        await _announce_battle_winner(battle, bot)
        return

    # More rounds left
    rounds_left  = total_rounds - round_num
    loser_name   = p1_name if loser_id == p1_id else p2_name

    await bot.send_message(
        group_id,
        f"🥊 <b>Round {round_num} Result</b>\n{result_line}\n{score}\n\n"
        f"⏩ {rounds_left} round{'s' if rounds_left > 1 else ''} remaining.\n\n"
        f"<b>@{loser_name}</b> — choose the next game or rematch:",
        reply_markup=battle_next_round_keyboard(battle_id),
    )
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"next_game_proposer_id": loser_id}})


# ─── Next round selection ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_next_same:"))
async def cb_bt_next_same(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "active":
        await callback.answer("Battle not active.", show_alert=True)
        return
    if callback.from_user.id not in (battle["challenger_id"], battle.get("opponent_id")):
        await callback.answer("You are not in this battle.", show_alert=True)
        return
    if battle.get("current_match_id"):
        await callback.answer("A match is already in progress!", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("🔄 Same game!")
    await _start_battle_round(battle, callback.message.bot)


@router.callback_query(F.data.startswith("bt_next_pick:"))
async def cb_bt_next_pick(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "active":
        await callback.answer("Battle not active.", show_alert=True)
        return
    if callback.from_user.id not in (battle["challenger_id"], battle.get("opponent_id")):
        await callback.answer("You are not in this battle.", show_alert=True)
        return
    if battle.get("current_match_id"):
        await callback.answer("A match is already in progress!", show_alert=True)
        return

    await callback.message.edit_text(
        f"🎮 <b>Pick game for Round {battle['current_round'] + 1}:</b>",
        reply_markup=battle_next_game_keyboard(battle_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bt_next_game:"))
async def cb_bt_next_game(callback: CallbackQuery):
    parts     = callback.data.split(":")
    battle_id = parts[1]
    game      = parts[2]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return
    if callback.from_user.id not in (battle["challenger_id"], battle.get("opponent_id")):
        await callback.answer("You are not in this battle.", show_alert=True)
        return

    proposer_name = callback.from_user.username or callback.from_user.first_name
    other_name = (
        battle["opponent_name"] if callback.from_user.id == battle["challenger_id"]
        else battle["challenger_name"]
    )

    await db.battles.update_one(
        {"battle_id": battle_id},
        {"$set": {"next_game_proposed": game, "next_game_proposer_id": callback.from_user.id}},
    )
    await callback.message.edit_text(
        f"🎮 <b>@{proposer_name}</b> proposes: <b>{GAME_NAMES.get(game, game)}</b>\n\n"
        f"@{other_name} — accept or decline?",
        reply_markup=battle_next_accept_keyboard(battle_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bt_next_accept:"))
async def cb_bt_next_accept(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return

    if callback.from_user.id == battle.get("next_game_proposer_id"):
        await callback.answer("Wait for your opponent to accept!", show_alert=True)
        return
    if callback.from_user.id not in (battle["challenger_id"], battle.get("opponent_id")):
        await callback.answer("You are not in this battle.", show_alert=True)
        return

    game = battle.get("next_game_proposed") or battle["game"]
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"current_round_game": game}})
    battle["current_round_game"] = game

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(f"✅ {GAME_NAMES.get(game, game)} accepted!")
    await _start_battle_round(battle, callback.message.bot)


@router.callback_query(F.data.startswith("bt_next_decline:"))
async def cb_bt_next_decline(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle:
        await callback.answer("Battle not found.", show_alert=True)
        return
    if callback.from_user.id == battle.get("next_game_proposer_id"):
        await callback.answer("You proposed this game!", show_alert=True)
        return

    game = battle.get("current_round_game") or battle["game"]
    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"current_round_game": game, "next_game_proposed": None}})
    battle["current_round_game"] = game

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("❌ Declined — playing same game.")
    await _start_battle_round(battle, callback.message.bot)


# ─── Battle winner announcement ───────────────────────────────────────────────

async def _announce_battle_winner(battle: dict, bot: Bot):
    group_id     = battle["group_id"]
    battle_id    = battle["battle_id"]
    winner_id    = battle["winner_id"]
    winner_name  = battle["winner_name"]
    p1_name      = battle["challenger_name"]
    p2_name      = battle["opponent_name"]
    p1_wins      = battle["p1_wins"]
    p2_wins      = battle["p2_wins"]
    r_draws      = battle.get("round_draws", 0)
    prize        = battle["prize_pool"]
    total_rounds = battle["total_rounds"]

    await bot.send_message(
        group_id,
        f"🏆 <b>BATTLE OVER!</b>\n\n"
        f"⚔️  @{p1_name}  vs  @{p2_name}  ({total_rounds} rounds)\n\n"
        f"📊 <b>Final Score:</b>\n"
        f"  @{p1_name}   🏅 {p1_wins} wins\n"
        f"  @{p2_name}   🏅 {p2_wins} wins\n"
        + (f"  🤝 {r_draws} draws\n" if r_draws else "")
        + f"\n🎉 <b>WINNER: @{winner_name}!</b>\n"
        f"💰 Prize: <b>₹{prize}</b>\n\n"
        f"@{winner_name} — please reply with your <b>UPI ID</b> to claim your prize!",
    )

    db = get_db()
    await db.battle_upi_waiting.update_one(
        {"user_id": winner_id, "group_id": group_id},
        {"$set": {"user_id": winner_id, "group_id": group_id,
                  "battle_id": battle_id, "created_at": now_utc()}},
        upsert=True,
    )


# ─── UPI ID capture ───────────────────────────────────────────────────────────

@router.message(BattleFormStates.waiting_upi, F.text)
async def msg_upi_fsm(message: Message, state: FSMContext):
    data = await state.get_data()
    battle_id = data.get("battle_id")
    await state.clear()
    if battle_id:
        await _process_upi(message, battle_id)


@router.message(F.text & ~F.text.startswith("/"))
async def msg_catch_upi_db(message: Message, state: FSMContext):
    """Catch winner's UPI ID typed in the group (DB-based state)."""
    if not message.from_user or not message.chat:
        return
    cur = await state.get_state()
    # Don't intercept if we're in another FSM state
    if cur is not None:
        return

    db = get_db()
    waiting = await db.battle_upi_waiting.find_one({
        "user_id": message.from_user.id,
        "group_id": message.chat.id,
    })
    if not waiting:
        return

    await db.battle_upi_waiting.delete_one({
        "user_id": message.from_user.id, "group_id": message.chat.id,
    })
    await _process_upi(message, waiting["battle_id"])


async def _process_upi(message: Message, battle_id: str):
    upi_id = (message.text or "").strip()
    if not upi_id or len(upi_id) < 3:
        await message.answer("❌ Invalid UPI ID. Please type again. Example: <code>name@paytm</code>")
        return

    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "pending_upi":
        return

    admin_id   = battle.get("approving_admin_id")
    admin_name = battle.get("approving_admin_name") or "admin"
    prize      = battle["prize_pool"]
    winner_name = battle["winner_name"]
    group_id   = battle["group_id"]

    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"winner_upi": upi_id, "status": "pending_payout"}})

    admin_tag = f"@{admin_name}" if admin_name else f"<a href='tg://user?id={admin_id}'>Admin</a>"
    await message.bot.send_message(
        group_id,
        f"💸 <b>Payout Request</b>\n\n"
        f"🏆 Winner: <b>@{winner_name}</b>\n"
        f"💰 Amount: <b>₹{prize}</b>\n"
        f"📱 UPI ID: <code>{upi_id}</code>\n\n"
        f"{admin_tag} — please send <b>₹{prize}</b> to UPI: <code>{upi_id}</code>\n"
        "Click <b>Payment Sent</b> once done.",
        reply_markup=battle_payout_done_keyboard(battle_id),
    )


# ─── Admin marks payout done ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("bt_payment_done:"))
async def cb_bt_payment_done(callback: CallbackQuery):
    battle_id = callback.data.split(":")[1]
    db = get_db()
    battle = await db.battles.find_one({"battle_id": battle_id})
    if not battle or battle["status"] != "pending_payout":
        await callback.answer("Already done or wrong state.", show_alert=True)
        return

    # Verify admin
    try:
        m = await callback.message.bot.get_chat_member(battle["group_id"], callback.from_user.id)
        if m.status not in ("administrator", "creator"):
            await callback.answer("❌ Only admins can mark payment sent.", show_alert=True)
            return
    except Exception:
        pass

    await db.battles.update_one({"battle_id": battle_id}, {"$set": {"status": "completed", "updated_at": now_utc()}})
    await callback.answer("✅ Payout confirmed!")
    await callback.message.edit_reply_markup(reply_markup=None)

    winner_name = battle["winner_name"]
    upi_id      = battle.get("winner_upi", "your UPI")
    prize       = battle["prize_pool"]

    await callback.message.bot.send_message(
        battle["group_id"],
        f"✅ <b>Payment Sent!</b>\n\n"
        f"@{winner_name} — ₹{prize} has been sent to <code>{upi_id}</code>\n\n"
        "Please check your wallet! 🎉🏆",
    )


# ─── Update battle stats ──────────────────────────────────────────────────────

async def _update_battle_stats(p1_id: int, p2_id: int, winner_id, is_draw: bool):
    db = get_db()
    if is_draw:
        await db.users.update_one({"user_id": p1_id}, {"$inc": {"battle_draws": 1, "total_battles": 1}})
        await db.users.update_one({"user_id": p2_id}, {"$inc": {"battle_draws": 1, "total_battles": 1}})
    elif winner_id == p1_id:
        await db.users.update_one({"user_id": p1_id}, {"$inc": {"battle_wins": 1, "total_battles": 1}})
        await db.users.update_one({"user_id": p2_id}, {"$inc": {"battle_losses": 1, "total_battles": 1}})
    else:
        await db.users.update_one({"user_id": p2_id}, {"$inc": {"battle_wins": 1, "total_battles": 1}})
        await db.users.update_one({"user_id": p1_id}, {"$inc": {"battle_losses": 1, "total_battles": 1}})
