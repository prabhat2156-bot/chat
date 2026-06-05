import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command

from database.mongodb import get_db
from database.models import now_utc
from config import DEFAULT_FEE_PERCENT, GAME_NAMES, OWNER_ID
from utils import timeout_manager

logger = logging.getLogger(__name__)
router = Router()


async def _is_group_admin(message: Message) -> bool:
    """Returns True if sender is a group creator or administrator."""
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


# ─── /feeset — group admins set their group's battle fee ─────────────────────

@router.message(Command("feeset"))
async def cmd_feeset(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "<tg-emoji emoji-id='5341715473882955310'>⚙️</tg-emoji> Use <code>/feeset</code> inside a group (not in DM).\n\n"
            "Example: <code>/feeset 10</code>  — sets 10% fee for that group.",
            parse_mode="HTML",
        )
        return

    if not await _is_group_admin(message):
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Only group admins can change the battle fee.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        db = get_db()
        gs = await db.group_settings.find_one({"group_id": message.chat.id})
        current = gs.get("fee_percent", DEFAULT_FEE_PERCENT) if gs else DEFAULT_FEE_PERCENT
        await message.answer(
            f"<tg-emoji emoji-id='5341715473882955310'>⚙️</tg-emoji> <b>Battle Fee — {message.chat.title}</b>\n\n"
            f"Current fee: <b>{current}%</b>\n\n"
            f"To change: <code>/feeset 10</code>  (0 – 50%)",
            parse_mode="HTML",
        )
        return

    raw = args[1].rstrip("%")
    try:
        percent = float(raw)
        if not (0 <= percent <= 50):
            raise ValueError
    except ValueError:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Fee must be a number between <b>0</b> and <b>50</b>.\n"
            "Example: <code>/feeset 10</code>",
            parse_mode="HTML",
        )
        return

    db = get_db()
    await db.group_settings.update_one(
        {"group_id": message.chat.id},
        {"$set": {
            "group_id": message.chat.id,
            "fee_percent": percent,
            "updated_at": now_utc(),
        }},
        upsert=True,
    )
    await message.answer(
        f"<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Battle fee updated!</b>\n\n"
        f"<tg-emoji emoji-id='6082576398772345226'>🏟</tg-emoji> Group: <b>{message.chat.title}</b>\n"
        f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> New fee: <b>{percent}%</b>\n\n"
        f"From now on, each /battle in this group will charge <b>{percent}%</b> platform fee.",
        parse_mode="HTML",
    )


# ─── /fee → show current fee ──────────────────────────────────────────────────

@router.message(Command("fee"))
async def cmd_fee(message: Message):
    if message.chat.type == "private":
        await message.answer("Use <code>/fee</code> inside a group.", parse_mode="HTML")
        return

    db = get_db()
    gs = await db.group_settings.find_one({"group_id": message.chat.id})
    current = gs.get("fee_percent", DEFAULT_FEE_PERCENT) if gs else DEFAULT_FEE_PERCENT
    await message.answer(
        f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Current battle fee:</b> <b>{current}%</b>\n\n"
        f"<i>Group admins can change it with <code>/feeset 10</code></i>",
        parse_mode="HTML",
    )


# ─── /history — admin sees all active matches & battles in group ──────────────

@router.message(Command("history"))
async def cmd_history(message: Message):
    """Group admin views all currently active matches and battles."""
    if message.chat.type == "private":
        await message.answer("Use <code>/history</code> inside a group.", parse_mode="HTML")
        return

    if not await _is_group_admin(message):
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Only group admins can use /history.")
        return

    db = get_db()
    group_id = message.chat.id

    # Fetch active matches
    active_matches = await db.matches.find({
        "group_id": group_id,
        "status": "active",
    }).to_list(length=50)

    # Fetch active battles (any non-terminal status)
    active_battles = await db.battles.find({
        "group_id": group_id,
        "status": {"$nin": ["completed", "cancelled", "declined"]},
    }).to_list(length=50)

    if not active_matches and not active_battles:
        await message.answer(
            "<tg-emoji emoji-id='5197269100878907942'>📋</tg-emoji> <b>No active games right now.</b>\n\n"
            "All quiet in this group! Use /challenge or /battle to start a game.",
            parse_mode="HTML",
        )
        return

    lines = ["<tg-emoji emoji-id='5197269100878907942'>📋</tg-emoji> <b>Active Games — Current Group</b>\n"]

    if active_matches:
        lines.append(f"<b><tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> Matches ({len(active_matches)})</b>")
        for m in active_matches:
            short_id  = m["match_id"][:8].upper()
            game_name = GAME_NAMES.get(m["game"], m["game"])
            p1        = m["player1_name"]
            p2        = m["player2_name"]
            is_battle = "  [Battle Round]" if m.get("battle_id") else ""
            lines.append(
                f"  🆔 <code>{short_id}</code> — {game_name}\n"
                f"      @{p1} vs @{p2}{is_battle}"
            )
        lines.append("")

    if active_battles:
        lines.append(f"<b><tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Paid Battles ({len(active_battles)})</b>")
        for b in active_battles:
            short_id   = b["battle_id"][:8].upper()
            game_name  = GAME_NAMES.get(b.get("game") or "", "—") if b.get("game") else "—"
            p1         = b["challenger_name"]
            p2         = b["opponent_name"]
            status_map = {
                "form_filling":        "<tg-emoji emoji-id='6141066526129653847'>📝</tg-emoji> Filling form",
                "pending_confirmation":"⏳ Awaiting confirm",
                "pending_payment":     "<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> Awaiting payment",
                "pending_ready":       "<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> Awaiting ready",
                "in_progress":         "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> In progress",
                "pending_payout":      "<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Awaiting payout",
            }
            status_label = status_map.get(b["status"], b["status"])
            rounds_info  = f"{b.get('current_round',0)}/{b.get('total_rounds','?')} rounds" if b.get("total_rounds") else "rounds TBD"
            amount_info  = f"₹{b['amount']}" if b.get("amount") else "amount TBD"
            lines.append(
                f"  🆔 <code>{short_id}</code> — {game_name}\n"
                f"      @{p1} vs @{p2}\n"
                f"      {status_label}  |  {rounds_info}  |  {amount_info}"
            )
        lines.append("")

    lines.append(
        "<i>Use /cancel &lt;ID&gt; to cancel any game by its ID.\n"
        "Use /endall to cancel every active game at once.</i>"
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── /endall — admin cancels ALL active matches & battles in group ────────────

@router.message(Command("endall"))
async def cmd_endall(message: Message):
    """Group admin cancels every active match and battle in this group."""
    if message.chat.type == "private":
        await message.answer("Use <code>/endall</code> inside a group.", parse_mode="HTML")
        return

    if not await _is_group_admin(message):
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Only group admins can use /endall.")
        return

    db = get_db()
    group_id   = message.chat.id
    admin_id   = message.from_user.id
    admin_name = message.from_user.username or message.from_user.first_name

    # ── Cancel all active matches ──
    active_matches = await db.matches.find({
        "group_id": group_id,
        "status": "active",
    }).to_list(length=200)

    matches_cancelled = 0
    for m in active_matches:
        timeout_manager.cancel_all_for_match(m["match_id"])
        await db.matches.update_one(
            {"match_id": m["match_id"]},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": now_utc(),
                "cancelled_by": admin_id,
            }},
        )
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=m["group_id"],
                message_id=m["message_id"],
                reply_markup=None,
            )
        except Exception:
            pass
        matches_cancelled += 1

    # ── Cancel all active battles ──
    active_battles = await db.battles.find({
        "group_id": group_id,
        "status": {"$nin": ["completed", "cancelled", "declined"]},
    }).to_list(length=200)

    battles_cancelled = 0
    for b in active_battles:
        # Cancel any running match round inside the battle
        active_round = await db.matches.find_one({
            "battle_id": b["battle_id"],
            "status": "active",
        })
        if active_round:
            timeout_manager.cancel_all_for_match(active_round["match_id"])
            await db.matches.update_one(
                {"match_id": active_round["match_id"]},
                {"$set": {"status": "cancelled", "cancelled_at": now_utc()}},
            )
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=active_round["group_id"],
                    message_id=active_round["message_id"],
                    reply_markup=None,
                )
            except Exception:
                pass

        await db.battles.update_one(
            {"battle_id": b["battle_id"]},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": now_utc(),
                "cancelled_by": admin_id,
            }},
        )
        battles_cancelled += 1

    total = matches_cancelled + battles_cancelled
    if total == 0:
        await message.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>No active games found.</b> Nothing to cancel.", parse_mode="HTML")
        return

    parts = []
    if matches_cancelled:
        parts.append(f"{matches_cancelled} match{'es' if matches_cancelled != 1 else ''}")
    if battles_cancelled:
        parts.append(f"{battles_cancelled} battle{'s' if battles_cancelled != 1 else ''}")

    await message.answer(
        f"<tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji> <b>All Games Ended by Admin</b>\n\n"
        f"Cancelled: <b>{', '.join(parts)}</b>\n\n"
        f"Done by @{admin_name}. No stats were recorded.",
        parse_mode="HTML",
    )


# ─── /cancel — any user can cancel their own game; admins can cancel any game ──

@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """
    For ALL users:
      /cancel         → shows your current active game(s) with IDs
      /cancel <ID>    → cancels your own match or battle by ID

    For group ADMINS:
      /cancel         → shows all active games (same as /history)
      /cancel <ID>    → cancels any game by ID
    """
    if message.chat.type == "private":
        await message.answer(
            "Use <code>/cancel</code> inside a group to see your active games.\n"
            "Use <code>/cancel A1B2C3D4</code> to cancel a game by its ID.",
            parse_mode="HTML",
        )
        return

    uid      = message.from_user.id
    uname    = message.from_user.username or message.from_user.first_name
    db       = get_db()
    is_admin = await _is_group_admin(message)
    args     = (message.text or "").split()

    # ── No ID given → show active games ──────────────────────────────────────
    if len(args) < 2:
        group_id = message.chat.id

        if is_admin:
            # Admin: show everything (redirect to /history logic)
            active_matches = await db.matches.find({
                "group_id": group_id, "status": "active",
            }).to_list(length=50)
            active_battles = await db.battles.find({
                "group_id": group_id,
                "status": {"$nin": ["completed", "cancelled", "declined"]},
            }).to_list(length=50)

            if not active_matches and not active_battles:
                await message.answer("<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> No active games in this group right now.")
                return

            lines = ["<tg-emoji emoji-id='5197269100878907942'>📋</tg-emoji> <b>Active Games in this Group</b>\n"]
            if active_matches:
                lines.append(f"<b><tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> Matches ({len(active_matches)})</b>")
                for m in active_matches:
                    short  = m["match_id"][:8].upper()
                    gname  = GAME_NAMES.get(m["game"], m["game"])
                    tag    = "  [Battle Round]" if m.get("battle_id") else ""
                    lines.append(f"  🆔 <code>{short}</code> — {gname}  @{m['player1_name']} vs @{m['player2_name']}{tag}")
                lines.append("")
            if active_battles:
                lines.append(f"<b><tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Battles ({len(active_battles)})</b>")
                for b in active_battles:
                    short  = b["battle_id"][:8].upper()
                    gname  = GAME_NAMES.get(b.get("game") or "", "—") if b.get("game") else "—"
                    smap   = {
                        "form_filling": "<tg-emoji emoji-id='6141066526129653847'>📝</tg-emoji> Filling",
                        "pending_confirmation": "⏳ Confirm",
                        "pending_payment": "<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> Payment",
                        "pending_ready": "<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> Ready",
                        "active": "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Playing",
                        "pending_payout": "<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Payout",
                    }
                    slabel = smap.get(b["status"], b["status"])
                    lines.append(f"  🆔 <code>{short}</code> — {gname}  @{b['challenger_name']} vs @{b['opponent_name']}  [{slabel}]")
                lines.append("")
            lines.append("<i>Use /cancel &lt;ID&gt; to cancel any game.</i>")
            await message.answer("\n".join(lines), parse_mode="HTML")

        else:
            # Regular user: show only their own active games
            my_match = await db.matches.find_one({
                "group_id": group_id,
                "status": "active",
                "$or": [{"player1_id": uid}, {"player2_id": uid}],
            })
            my_battle = await db.battles.find_one({
                "group_id": group_id,
                "status": {"$nin": ["completed", "cancelled", "declined"]},
                "$or": [{"challenger_id": uid}, {"opponent_id": uid}],
            })

            if not my_match and not my_battle:
                await message.answer(
                    "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>You have no active games in this group.</b>\n\n"
                    "Use /challenge @player or /battle @player to start one!",
                    parse_mode="HTML",
                )
                return

            lines = [f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Your Active Games</b>\n"]
            if my_match:
                short  = my_match["match_id"][:8].upper()
                gname  = GAME_NAMES.get(my_match["game"], my_match["game"])
                opp    = my_match["player2_name"] if uid == my_match["player1_id"] else my_match["player1_name"]
                tag    = "  _(inside a /battle)_" if my_match.get("battle_id") else ""
                lines.append(
                    f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Match</b>\n"
                    f"  🆔 <code>{short}</code>\n"
                    f"  <tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {gname}\n"
                    f"  🆚 vs @{opp}{tag}\n"
                    f"  <tg-emoji emoji-id='4956282853882069908'>➡️</tg-emoji> Cancel: <code>/cancel {short}</code>"
                )
            if my_battle:
                short  = my_battle["battle_id"][:8].upper()
                gname  = GAME_NAMES.get(my_battle.get("game") or "", "—") if my_battle.get("game") else "—"
                opp    = my_battle["opponent_name"] if uid == my_battle["challenger_id"] else my_battle["challenger_name"]
                smap   = {
                    "form_filling": "<tg-emoji emoji-id='6141066526129653847'>📝</tg-emoji> Filling form",
                    "pending_confirmation": "⏳ Waiting for confirmation",
                    "pending_payment": "<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> Waiting for payment",
                    "pending_ready": "<tg-emoji emoji-id='4958479549265347295'>⚡</tg-emoji> Waiting for ready",
                    "active": "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> Rounds in progress",
                    "pending_payout": "<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Waiting for payout",
                    "draw_pending": "<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draw — awaiting resolution",
                    "draw_rematch_pending": "<tg-emoji emoji-id='4956371914323920049'>🔄</tg-emoji> Rematch confirmation pending",
                }
                slabel = smap.get(my_battle["status"], my_battle["status"])
                amount = f"₹{my_battle['amount']}" if my_battle.get("amount") else "amount TBD"
                score  = ""
                if my_battle.get("total_rounds"):
                    p1w = my_battle.get("p1_wins", 0)
                    p2w = my_battle.get("p2_wins", 0)
                    score = f"\n  <tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Score: {p1w}–{p2w} (Round {my_battle.get('current_round',0)}/{my_battle['total_rounds']})"
                lines.append(
                    f"\n<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Battle</b>\n"
                    f"  🆔 <code>{short}</code>\n"
                    f"  <tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {gname}  ·  {amount}\n"
                    f"  🆚 vs @{opp}\n"
                    f"  <tg-emoji emoji-id='4956232383721374836'>📌</tg-emoji> {slabel}{score}\n"
                    f"  <tg-emoji emoji-id='4956282853882069908'>➡️</tg-emoji> Cancel: <code>/cancel {short}</code>"
                )

            await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # ── ID given → cancel the game ────────────────────────────────────────────
    short_id   = args[1].strip().upper()
    canceller  = uname

    # ── Try match first ──
    match_query = {
        "match_id": {"$regex": f"^{re.escape(short_id.lower())}", "$options": "i"},
        "group_id": message.chat.id,
        "status": "active",
    }
    if not is_admin:
        # Regular users can only cancel their own matches
        match_query["$or"] = [{"player1_id": uid}, {"player2_id": uid}]

    match = await db.matches.find_one(match_query)
    if match:
        # Extra check: if this match is a battle round, user cannot cancel it standalone
        if not is_admin and match.get("battle_id"):
            await message.answer(
                "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> This match is part of a paid battle — only an admin can cancel it.\n\n"
                f"Ask an admin: <code>/cancel {short_id}</code>",
                parse_mode="HTML",
            )
            return

        timeout_manager.cancel_all_for_match(match["match_id"])
        await db.matches.update_one(
            {"match_id": match["match_id"]},
            {"$set": {"status": "cancelled", "cancelled_at": now_utc(), "cancelled_by": uid}},
        )
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=match["group_id"], message_id=match["message_id"], reply_markup=None,
            )
        except Exception:
            pass

        game_name = GAME_NAMES.get(match["game"], match["game"])
        by_line = "Cancelled by admin" if is_admin else "Cancelled by player"
        await message.answer(
            f"<tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji> <b>Match Cancelled</b>\n\n"
            f"🆔 <code>{short_id}</code>  ·  {game_name}\n"
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> @{match['player1_name']} vs @{match['player2_name']}\n\n"
            f"{by_line} @{canceller}. No stats recorded.",
            parse_mode="HTML",
        )
        return

    # ── Try battle ──
    battle_query = {
        "battle_id": {"$regex": f"^{re.escape(short_id.lower())}", "$options": "i"},
        "group_id": message.chat.id,
        "status": {"$nin": ["completed", "cancelled", "declined"]},
    }
    if not is_admin:
        battle_query["$or"] = [{"challenger_id": uid}, {"opponent_id": uid}]

    battle = await db.battles.find_one(battle_query)
    if battle:
        # Cancel any active round match inside the battle
        active_round = await db.matches.find_one({"battle_id": battle["battle_id"], "status": "active"})
        if active_round:
            timeout_manager.cancel_all_for_match(active_round["match_id"])
            await db.matches.update_one(
                {"match_id": active_round["match_id"]},
                {"$set": {"status": "cancelled", "cancelled_at": now_utc()}},
            )
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=active_round["group_id"], message_id=active_round["message_id"], reply_markup=None,
                )
            except Exception:
                pass

        await db.battles.update_one(
            {"battle_id": battle["battle_id"]},
            {"$set": {"status": "cancelled", "cancelled_at": now_utc(), "cancelled_by": uid}},
        )
        game_label = GAME_NAMES.get(battle.get("game") or "", "—") if battle.get("game") else "—"
        by_line = "Cancelled by admin" if is_admin else "Cancelled by player"
        await message.answer(
            f"<tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji> <b>Battle Cancelled</b>\n\n"
            f"🆔 <code>{short_id}</code>  ·  {game_label}\n"
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> @{battle['challenger_name']} vs @{battle['opponent_name']}\n\n"
            f"{by_line} @{canceller}. No stats recorded.",
            parse_mode="HTML",
        )
        return

    # ── Not found / no permission ──
    if is_admin:
        await message.answer(
            f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> No active game found with ID <code>{short_id}</code>.\n\n"
            f"Use /cancel (no ID) to see all active game IDs.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> No active game found with ID <code>{short_id}</code> that you're part of.\n\n"
            f"Use /cancel (no ID) to see your current active games.",
            parse_mode="HTML",
        )


# ─── /cancelmatch — admin force-cancel an active match (legacy) ───────────────

@router.message(Command("cancelmatch"))
async def cmd_cancelmatch(message: Message):
    """Group admin cancels an active match by its 8-char ID.
    Usage: /cancelmatch A1B2C3D4
    """
    if message.chat.type == "private":
        await message.answer("Use <code>/cancelmatch &lt;ID&gt;</code> inside a group.", parse_mode="HTML")
        return

    if not await _is_group_admin(message):
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Only group admins can cancel matches.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Please provide the Match ID.\n\n"
            "Usage: <code>/cancelmatch A1B2C3D4</code>\n\n"
            "The Match ID is shown as 🆔 in every game board message.",
            parse_mode="HTML",
        )
        return

    short_id = args[1].strip().upper()
    db = get_db()
    match = await db.matches.find_one({
        "match_id": {"$regex": f"^{re.escape(short_id.lower())}", "$options": "i"},
        "status": "active",
    })
    if not match:
        await message.answer(
            f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> No active match found with ID <code>{short_id}</code>.\n\n"
            f"Make sure you copied the correct 8-character ID from the match message.",
            parse_mode="HTML",
        )
        return

    timeout_manager.cancel_all_for_match(match["match_id"])
    await db.matches.update_one(
        {"match_id": match["match_id"]},
        {"$set": {"status": "cancelled", "cancelled_at": now_utc(), "cancelled_by": message.from_user.id}},
    )

    try:
        await message.bot.edit_message_reply_markup(
            chat_id=match["group_id"], message_id=match["message_id"], reply_markup=None,
        )
    except Exception:
        pass

    admin_name = message.from_user.username or message.from_user.first_name
    await message.answer(
        f"<tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji> <b>Match Cancelled by Admin</b>\n\n"
        f"🆔 <code>Match {short_id}</code>\n"
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> @{match['player1_name']} vs @{match['player2_name']}\n\n"
        f"Cancelled by @{admin_name}. No stats were recorded.",
        parse_mode="HTML",
    )


# ─── /cancelbattle — admin force-cancel an active battle (legacy) ─────────────

@router.message(Command("cancelbattle"))
async def cmd_cancelbattle(message: Message):
    """Group admin cancels an active battle by its 8-char ID.
    Usage: /cancelbattle A1B2C3D4
    """
    if message.chat.type == "private":
        await message.answer("Use <code>/cancelbattle &lt;ID&gt;</code> inside a group.", parse_mode="HTML")
        return

    if not await _is_group_admin(message):
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Only group admins can cancel battles.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Please provide the Battle ID.\n\n"
            "Usage: <code>/cancelbattle A1B2C3D4</code>\n\n"
            "The Battle ID 🆔 is shown on every battle form and confirm screen.",
            parse_mode="HTML",
        )
        return

    short_id = args[1].strip().upper()
    db = get_db()
    battle = await db.battles.find_one({
        "battle_id": {"$regex": f"^{re.escape(short_id.lower())}", "$options": "i"},
        "status": {"$nin": ["completed", "cancelled", "declined"]},
    })
    if not battle:
        await message.answer(
            f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> No active battle found with ID <code>{short_id}</code>.\n\n"
            f"Make sure you copied the correct 8-character ID from the battle form.",
            parse_mode="HTML",
        )
        return

    await db.battles.update_one(
        {"battle_id": battle["battle_id"]},
        {"$set": {"status": "cancelled", "cancelled_at": now_utc(), "cancelled_by": message.from_user.id}},
    )

    active_round = await db.matches.find_one({"battle_id": battle["battle_id"], "status": "active"})
    if active_round:
        timeout_manager.cancel_all_for_match(active_round["match_id"])
        await db.matches.update_one(
            {"match_id": active_round["match_id"]},
            {"$set": {"status": "cancelled", "cancelled_at": now_utc()}},
        )
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=active_round["group_id"],
                message_id=active_round["message_id"],
                reply_markup=None,
            )
        except Exception:
            pass

    admin_name = message.from_user.username or message.from_user.first_name
    game_label = GAME_NAMES.get(battle.get("game") or "", "—") if battle.get("game") else "—"
    await message.answer(
        f"<tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji> <b>Battle Cancelled by Admin</b>\n\n"
        f"🆔 <code>Battle {short_id}</code>\n"
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> @{battle['challenger_name']} vs @{battle['opponent_name']}\n"
        f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> {game_label}\n\n"
        f"Cancelled by @{admin_name}. No stats were recorded.",
        parse_mode="HTML",
    )


# ─── /reset — OWNER ONLY: wipe entire bot database ───────────────────────────

@router.message(Command("reset"))
async def cmd_reset(message: Message):
    """Bot owner wipes ALL data from the database.
    This is irreversible. Only the OWNER_ID configured in .env can use this.
    """
    if message.chat.type != "private":
        await message.answer(
            "<tg-emoji emoji-id='4956611513369494230'>⚠️</tg-emoji> For safety, /reset only works in DM with the bot.\n"
            "Send me <code>/reset</code> in a private message.",
            parse_mode="HTML",
        )
        return

    if not OWNER_ID or message.from_user.id != OWNER_ID:
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> This command is only available to the bot owner.")
        return

    # Confirm step — user must send /resetconfirm
    await message.answer(
        "<tg-emoji emoji-id='4956611513369494230'>⚠️</tg-emoji> <b>DANGER ZONE</b>\n\n"
        "This will permanently delete <b>ALL</b> data:\n"
        "• All users and their stats\n"
        "• All matches, challenges, battles\n"
        "• All tournaments\n"
        "• All group settings\n\n"
        "To confirm, send: <code>/resetconfirm</code>\n\n"
        "<i>There is no undo.</i>",
        parse_mode="HTML",
    )


@router.message(Command("resetconfirm"))
async def cmd_resetconfirm(message: Message):
    """Second step of /reset — actually wipes the database."""
    if message.chat.type != "private":
        return

    if not OWNER_ID or message.from_user.id != OWNER_ID:
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> This command is only available to the bot owner.")
        return

    db = get_db()

    collections = [
        "users",
        "matches",
        "challenges",
        "challenge_selections",
        "battles",
        "battle_upi_waiting",
        "match_confirmations",
        "tournaments",
        "rematch_requests",
        "newgame_requests",
        "group_settings",
    ]

    deleted_counts = {}
    for col in collections:
        try:
            result = await db[col].delete_many({})
            deleted_counts[col] = result.deleted_count
        except Exception as e:
            deleted_counts[col] = f"error: {e}"

    summary_lines = [f"  • {col}: {count}" for col, count in deleted_counts.items()]
    await message.answer(
        "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> <b>Bot Reset Complete</b>\n\n"
        "All data has been permanently deleted:\n"
        + "\n".join(summary_lines)
        + "\n\n<i>The bot is now clean and ready to use.</i>",
        parse_mode="HTML",
    )
    logger.warning(f"OWNER RESET: All data wiped by user {message.from_user.id}")


# ─── /lookup <ID> — OWNER: full details of any past match or battle ───────────

@router.message(Command("lookup"))
async def cmd_lookup(message: Message):
    """Bot owner looks up any match or battle (active or finished) by its ID.
    Works in DM or group.  Usage: /lookup A1B2C3D4
    """
    if not OWNER_ID or message.from_user.id != OWNER_ID:
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Owner-only command.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "Usage: <code>/lookup A1B2C3D4</code>\n\n"
            "Provide the 8-character Game ID (match or battle).",
            parse_mode="HTML",
        )
        return

    short_id = args[1].strip().upper()
    db = get_db()

    # ── Try match ──
    match = await db.matches.find_one({
        "match_id": {"$regex": f"^{re.escape(short_id.lower())}", "$options": "i"},
    })
    if match:
        gname     = GAME_NAMES.get(match.get("game", ""), match.get("game", "—"))
        status    = match.get("status", "—")
        winner    = match.get("winner_name", "—")
        is_draw   = match.get("is_draw", False)
        outcome   = "<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draw" if is_draw else (f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> {winner}" if winner and winner != "—" else "—")
        forfeit   = "  _(forfeit)_" if match.get("forfeit") else ""
        created   = str(match.get("created_at", "—"))[:16]
        finished  = str(match.get("finished_at", "—"))[:16]
        group     = match.get("group_title", str(match.get("group_id", "—")))
        bid       = match.get("battle_id", "")
        battle_ln = f"\n<tg-emoji emoji-id='4958689671950369798'>🔗</tg-emoji> <b>Part of Battle:</b> <code>{bid[:8].upper()}</code>" if bid else ""

        lines = [
            f"<tg-emoji emoji-id='5397986013681295058'>🔍</tg-emoji> <b>Match Lookup</b>",
            f"🆔 <code>{short_id}</code>",
            f"",
            f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Game:</b> {gname}",
            f"<tg-emoji emoji-id='4956232383721374836'>📌</tg-emoji> <b>Status:</b> {status}",
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Players:</b> @{match.get('player1_name','?')} vs @{match.get('player2_name','?')}",
            f"<tg-emoji emoji-id='5440539497383087970'>🏅</tg-emoji> <b>Outcome:</b> {outcome}{forfeit}",
            f"<tg-emoji emoji-id='5416041192905265756'>🏠</tg-emoji> <b>Group:</b> {group}",
            f"<tg-emoji emoji-id='5440621591387980068'>🕐</tg-emoji> <b>Started:</b> {created}",
            f"<tg-emoji emoji-id='5440621591387980068'>🕑</tg-emoji> <b>Finished:</b> {finished}",
        ]
        if battle_ln:
            lines.append(battle_ln)
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # ── Try battle ──
    battle = await db.battles.find_one({
        "battle_id": {"$regex": f"^{re.escape(short_id.lower())}", "$options": "i"},
    })
    if battle:
        gname    = GAME_NAMES.get(battle.get("game") or "", "—") if battle.get("game") else "—"
        status   = battle.get("status", "—")
        winner   = battle.get("winner_name", "—") or "—"
        amount   = f"₹{battle['amount']}" if battle.get("amount") else "—"
        fee_pct  = battle.get("fee_percent", "—")
        prize    = f"₹{battle.get('prize_pool', '—')}"
        p1w      = battle.get("p1_wins", 0)
        p2w      = battle.get("p2_wins", 0)
        draws    = battle.get("round_draws", 0)
        total    = battle.get("total_rounds", "—")
        created  = str(battle.get("created_at", "—"))[:16]
        finished = str(battle.get("finished_at", "—"))[:16]
        group    = battle.get("group_title", str(battle.get("group_id", "—")))

        lines = [
            f"<tg-emoji emoji-id='5397986013681295058'>🔍</tg-emoji> <b>Battle Lookup</b>",
            f"🆔 <code>{short_id}</code>",
            f"",
            f"<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Game:</b> {gname}",
            f"<tg-emoji emoji-id='4956232383721374836'>📌</tg-emoji> <b>Status:</b> {status}",
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Players:</b> @{battle.get('challenger_name','?')} vs @{battle.get('opponent_name','?')}",
            f"<tg-emoji emoji-id='5440539497383087970'>🏅</tg-emoji> <b>Winner:</b> {winner}",
            f"📊 <b>Score:</b> {p1w}–{p2w}  ({draws} draw{'s' if draws != 1 else ''})  /{total} rounds",
            f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> <b>Bet:</b> {amount}  |  Fee: {fee_pct}%  |  Prize Pool: {prize}",
            f"<tg-emoji emoji-id='5416041192905265756'>🏠</tg-emoji> <b>Group:</b> {group}",
            f"<tg-emoji emoji-id='5440621591387980068'>🕐</tg-emoji> <b>Started:</b> {created}",
            f"<tg-emoji emoji-id='5440621591387980068'>🕑</tg-emoji> <b>Finished:</b> {finished}",
        ]
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    # ── Not found ──
    await message.answer(
        f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> No match or battle found with ID <code>{short_id}</code>.\n\n"
        f"IDs are case-insensitive — check the first 8 characters shown by 🆔.",
        parse_mode="HTML",
    )


# ─── /allhistory — OWNER: recent matches & battles across all groups ──────────

@router.message(Command("allhistory"))
async def cmd_allhistory(message: Message):
    """Bot owner views the last N completed matches and battles (all groups).
    Usage: /allhistory         → last 20
           /allhistory 50      → last 50
    Works in DM or group.
    """
    if not OWNER_ID or message.from_user.id != OWNER_ID:
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Owner-only command.")
        return

    args  = (message.text or "").split()
    limit = 20
    if len(args) >= 2:
        try:
            limit = max(1, min(int(args[1]), 100))
        except ValueError:
            pass

    db = get_db()

    # ── Fetch recent completed matches ──
    recent_matches = await db.matches.find(
        {"status": {"$in": ["finished", "cancelled", "forfeit"]}},
        sort=[("finished_at", -1)],
    ).to_list(length=limit)

    # ── Fetch recent completed battles ──
    recent_battles = await db.battles.find(
        {"status": {"$in": ["completed", "cancelled", "declined"]}},
        sort=[("finished_at", -1)],
    ).to_list(length=limit)

    if not recent_matches and not recent_battles:
        await message.answer("<tg-emoji emoji-id='6100206569507524717'>📭</tg-emoji> No completed matches or battles found yet.")
        return

    STATUS_ICON = {
        "finished": "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji>", "cancelled": "<tg-emoji emoji-id='6271674836628541366'>🛑</tg-emoji>", "forfeit": "<tg-emoji emoji-id='4956337889593000947'>🚫</tg-emoji>",
        "completed": "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji>", "declined": "↩️",
    }

    parts = []

    if recent_matches:
        parts.append(f"<b><tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> Recent Matches (last {len(recent_matches)})</b>")
        for m in recent_matches:
            short   = m["match_id"][:8].upper()
            gname   = GAME_NAMES.get(m.get("game", ""), m.get("game", "—"))
            icon    = STATUS_ICON.get(m.get("status", ""), "•")
            outcome = "<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draw" if m.get("is_draw") else (f"<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> @{m.get('winner_name','?')}" if m.get("winner_name") else m.get("status","—"))
            forfeit = " _(forfeit)_" if m.get("forfeit") else ""
            dt      = str(m.get("finished_at", ""))[:10]
            group   = m.get("group_title", str(m.get("group_id", "—")))
            parts.append(
                f"{icon} <code>{short}</code>  {gname}\n"
                f"    @{m.get('player1_name','?')} vs @{m.get('player2_name','?')}\n"
                f"    {outcome}{forfeit}  ·  {dt}  ·  {group}"
            )
        parts.append("")

    if recent_battles:
        parts.append(f"<b><tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Recent Battles (last {len(recent_battles)})</b>")
        for b in recent_battles:
            short   = b["battle_id"][:8].upper()
            gname   = GAME_NAMES.get(b.get("game") or "", "—") if b.get("game") else "—"
            icon    = STATUS_ICON.get(b.get("status", ""), "•")
            winner  = b.get("winner_name", "—") or "—"
            amount  = f"₹{b['amount']}" if b.get("amount") else "—"
            p1w     = b.get("p1_wins", 0)
            p2w     = b.get("p2_wins", 0)
            dt      = str(b.get("finished_at", ""))[:10]
            group   = b.get("group_title", str(b.get("group_id", "—")))
            parts.append(
                f"{icon} <code>{short}</code>  {gname}  {amount}\n"
                f"    @{b.get('challenger_name','?')} vs @{b.get('opponent_name','?')}\n"
                f"    <tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> @{winner}  ({p1w}–{p2w})  ·  {dt}  ·  {group}"
            )
        parts.append("")

    parts.append(
        f"<i>Showing last {limit} of each type. Use /lookup &lt;ID&gt; for full details.</i>"
    )

    # Telegram has a 4096 char limit — split if needed
    text = "\n".join(parts)
    if len(text) <= 4000:
        await message.answer(text, parse_mode="HTML")
    else:
        chunk, chunks = [], []
        for line in parts:
            chunk.append(line)
            if sum(len(l) for l in chunk) > 3500:
                chunks.append("\n".join(chunk))
                chunk = []
        if chunk:
            chunks.append("\n".join(chunk))
        for c in chunks:
            await message.answer(c, parse_mode="HTML")
