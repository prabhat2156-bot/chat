import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database.mongodb import get_db
from utils.db_helpers import get_or_create_user
from config import GAME_NAMES, GAME_EMOJI

logger = logging.getLogger(__name__)
router = Router()


async def _build_profile_text(user: dict, username_display: str) -> str:
    total    = user.get("total_matches", 0)
    wins     = user.get("wins", 0)
    losses   = user.get("losses", 0)
    draws    = user.get("draws", 0)
    win_rate = round((wins / total * 100) if total > 0 else 0, 1)

    lines = [
        f"<tg-emoji emoji-id='5870994129244131212'>👤</tg-emoji> <b>Player: {username_display}</b>",
        "",
        "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji> <b>Free Matches</b>",
        f"  Played: {total}  |  <tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {wins}W  <tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> {losses}L  <tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> {draws}D",
        f"  <tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Win Rate: <b>{win_rate}%</b>",
    ]

    # Per-game breakdown
    game_stats = user.get("game_stats", {})
    if game_stats:
        played_games = [(k, v) for k, v in game_stats.items() if isinstance(v, dict) and v.get("matches", 0) > 0]
        if played_games:
            lines.append("")
            lines.append("<tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>Per-Game Stats:</b>")
            for game_key, stats in played_games:
                g_total  = stats.get("matches", 0)
                g_wins   = stats.get("wins", 0)
                g_losses = stats.get("losses", 0)
                g_wr     = round((g_wins / g_total * 100) if g_total > 0 else 0, 1)
                emoji    = GAME_EMOJI.get(game_key, "<tg-emoji emoji-id='5361741454685256344'>🎮</tg-emoji>")
                name     = GAME_NAMES.get(game_key, game_key)
                lines.append(f"  {emoji} {name}: {g_total} played  |  {g_wins}W {g_losses}L  |  {g_wr}%")

    # Battle stats
    total_battles = user.get("total_battles", 0)
    battle_wins   = user.get("battle_wins", 0)
    battle_losses = user.get("battle_losses", 0)
    battle_draws  = user.get("battle_draws", 0)
    bw_rate       = round((battle_wins / total_battles * 100) if total_battles > 0 else 0, 1)

    if total_battles > 0:
        lines.append("")
        lines.append("<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Battle Stats</b>")
        lines.append(
            f"  Played: {total_battles}  |  <tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {battle_wins}W  <tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> {battle_losses}L  <tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> {battle_draws}D"
        )
        lines.append(f"  <tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Win Rate: <b>{bw_rate}%</b>")

    joined = user.get("joined_at")
    if joined:
        date_str = joined.strftime("%Y-%m-%d") if hasattr(joined, "strftime") else str(joined)[:10]
        lines.append("")
        lines.append(f"<tg-emoji emoji-id='5274055917766202507'>📅</tg-emoji> Joined: {date_str}")

    return "\n".join(lines)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    if message.chat.type == "private":
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> This bot only works in groups.")
        return

    db               = get_db()
    user             = None
    username_display = None

    args = (message.text or "").split()
    if len(args) >= 2:
        raw = args[1].lstrip("@").strip()

        if message.entities:
            for ent in message.entities:
                if hasattr(ent, "type") and ent.type == "text_mention" and getattr(ent, "user", None):
                    u    = ent.user
                    user = await db.users.find_one({"user_id": u.id})
                    if not user:
                        user = await get_or_create_user(u.id, u.username or "", u.first_name or "")
                    username_display = f"@{u.username}" if u.username else u.first_name
                    break

        if user is None and raw:
            doc = await db.users.find_one({"username": {"$regex": f"^{raw}$", "$options": "i"}})
            if doc:
                user             = doc
                uname            = doc.get("username") or doc.get("first_name") or raw
                username_display = f"@{uname}"
            else:
                await message.answer(
                    f"<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> <b>@{raw}</b> not found.\n\n"
                    f"They must have played at least one match in this group.",
                    parse_mode="HTML",
                )
                return

    if user is None and message.reply_to_message:
        target           = message.reply_to_message.from_user
        user             = await get_or_create_user(target.id, target.username or "", target.first_name or "")
        username_display = f"@{target.username}" if target.username else target.first_name

    if user is None:
        target           = message.from_user
        user             = await get_or_create_user(target.id, target.username or "", target.first_name or "")
        username_display = f"@{target.username}" if target.username else target.first_name

    if username_display is None:
        username_display = f"@{user.get('username')}" if user.get("username") else user.get("first_name", "Unknown")

    text = await _build_profile_text(user, username_display)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    await cmd_profile(message)


@router.message(Command("mystats"))
async def cmd_mystats(message: Message):
    """Show your own stats — works in groups and DMs."""
    db      = get_db()
    user_tg = message.from_user
    user    = await get_or_create_user(user_tg.id, user_tg.username or "", user_tg.first_name or "")
    display = f"@{user_tg.username}" if user_tg.username else user_tg.first_name
    text    = await _build_profile_text(user, display)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("mybattles"))
async def cmd_mybattles(message: Message):
    """Show last 10 completed paid battles — works in groups and DMs."""
    db    = get_db()
    uid   = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    cursor  = db.battles.find(
        {
            "status": "completed",
            "$or": [{"challenger_id": uid}, {"opponent_id": uid}],
        }
    ).sort("updated_at", -1).limit(10)
    battles = await cursor.to_list(length=10)

    if not battles:
        await message.answer(
            f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Battle History — {uname}</b>\n\n"
            "No completed battles yet.\n"
            "Use /battle @player to start one!",
            parse_mode="HTML",
        )
        return

    lines = [
        f"<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Battle History — {uname}</b>",
        "",
    ]

    total_won  = 0.0
    total_lost = 0.0

    for b in battles:
        short         = b["battle_id"][:8].upper()
        game          = GAME_NAMES.get(b.get("game") or "", "—") if b.get("game") else "—"
        amount        = b.get("amount") or 0
        fee           = b.get("fee_per_player") or 0
        prize         = b.get("prize_pool") or 0
        rounds        = b.get("total_rounds") or 1
        winner_id     = b.get("winner_id")
        is_challenger = (b["challenger_id"] == uid)

        opp_name = (
            b.get("opponent_name") or b.get("opponent_username") or "?"
            if is_challenger
            else b.get("challenger_name") or "?"
        )

        p1_wins  = b.get("p1_wins", 0)
        p2_wins  = b.get("p2_wins", 0)
        my_wins  = p1_wins if is_challenger else p2_wins
        opp_wins = p2_wins if is_challenger else p1_wins

        if winner_id is None:
            outcome     = "<tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> Draw"
            result_line = f"  Draw  ·  {my_wins}-{opp_wins} rounds"
        elif winner_id == uid:
            outcome     = "<tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> Won"
            net         = (prize - fee) if prize else (amount - fee)
            result_line = f"  Won  ·  {my_wins}-{opp_wins} rounds  ·  <b>+₹{net:.0f}</b>"
            total_won  += max(net, 0)
        else:
            outcome     = "<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> Lost"
            result_line = f"  Lost  ·  {my_wins}-{opp_wins} rounds  ·  <b>-₹{fee:.0f}</b>"
            total_lost += fee

        date_obj = b.get("updated_at")
        date_str = date_obj.strftime("%d %b") if date_obj and hasattr(date_obj, "strftime") else "—"

        lines += [
            f"{outcome}  vs <b>@{opp_name}</b>  ·  {game}  ·  {date_str}",
            result_line,
            f"  🆔 <code>{short}</code>  ·  {rounds} round{'s' if rounds != 1 else ''}  ·  ₹{amount}/player",
            "",
        ]

    lines += [
        "─────────────────────",
        f"<tg-emoji emoji-id='4965219701572503640'>💰</tg-emoji> Total won:   <b>+₹{total_won:.0f}</b>",
        f"<tg-emoji emoji-id='4958506272551863292'>📉</tg-emoji> Total lost:  <b>-₹{total_lost:.0f}</b>",
        f"<tg-emoji emoji-id='4958506272551863292'>📊</tg-emoji> Net:         <b>₹{total_won - total_lost:+.0f}</b>",
    ]

    await message.answer("\n".join(lines), parse_mode="HTML")
