import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database.mongodb import get_db

logger = logging.getLogger(__name__)
router = Router()

MEDALS = ["<tg-emoji emoji-id='5440539497383087970'>🥇</tg-emoji>", "<tg-emoji emoji-id='5447203607294265305'>🥈</tg-emoji>", "<tg-emoji emoji-id='5453902265922376865'>🥉</tg-emoji>", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "<tg-emoji emoji-id='5197397670724912036'>1</tg-emoji><tg-emoji emoji-id='5195439139868134115'>0</tg-emoji>"]


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    if message.chat.type == "private":
        await message.answer("<tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> This bot only works in groups.")
        return

    db = get_db()

    # ─── Free Match Top 10 ────────────────────────────────────────────────────
    cursor  = db.users.find({"total_matches": {"$gt": 0}}).sort("wins", -1).limit(10)
    players = await cursor.to_list(length=10)

    lines = ["<tg-emoji emoji-id='6194737030165959506'>🏆</tg-emoji> <b>Leaderboard — Free Matches (Top 10)</b>\n"]

    if players:
        for i, p in enumerate(players):
            name    = p.get("username") or p.get("first_name") or "Unknown"
            wins    = p.get("wins", 0)
            total   = p.get("total_matches", 0)
            losses  = p.get("losses", 0)
            draws   = p.get("draws", 0)
            win_pct = round((wins / total * 100), 1) if total > 0 else 0.0
            medal   = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
            lines.append(
                f"{medal} <b>@{name}</b>\n"
                f"   <tg-emoji emoji-id='4958610528588008305'>✅</tg-emoji> {wins}W  <tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> {losses}L  <tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> {draws}D  |  <tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>{win_pct}%</b>  ({total} played)"
            )
    else:
        lines.append("No free matches played yet. Use /challenge to start!")

    # ─── Battle Top 10 ────────────────────────────────────────────────────────
    battle_cursor  = db.users.find({"total_battles": {"$gt": 0}}).sort("battle_wins", -1).limit(10)
    battle_players = await battle_cursor.to_list(length=10)

    lines.append("")
    lines.append("<tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> <b>Leaderboard — Battles (Top 10)</b>\n")

    if battle_players:
        for i, p in enumerate(battle_players):
            name   = p.get("username") or p.get("first_name") or "Unknown"
            bw     = p.get("battle_wins", 0)
            bl     = p.get("battle_losses", 0)
            bd     = p.get("battle_draws", 0)
            bt     = p.get("total_battles", 0)
            bpct   = round((bw / bt * 100), 1) if bt > 0 else 0.0
            medal  = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
            lines.append(
                f"{medal} <b>@{name}</b>\n"
                f"   <tg-emoji emoji-id='5039775669496579510'>⚔️</tg-emoji> {bw}W  <tg-emoji emoji-id='4956612582816351459'>❌</tg-emoji> {bl}L  <tg-emoji emoji-id='4963323872943276909'>🤝</tg-emoji> {bd}D  |  <tg-emoji emoji-id='5310278924616356636'>🎯</tg-emoji> <b>{bpct}%</b>  ({bt} played)"
            )
    else:
        lines.append("No battles played yet. Use /battle to start!")

    await message.answer("\n".join(lines), parse_mode="HTML")
