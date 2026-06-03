import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database.mongodb import get_db

logger = logging.getLogger(__name__)
router = Router()

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    if message.chat.type == "private":
        await message.answer("❌ This bot only works in groups.")
        return

    db = get_db()

    # Top 10 by total wins, min 1 match played
    cursor = db.users.find({"total_matches": {"$gt": 0}}).sort("wins", -1).limit(10)
    players = await cursor.to_list(length=10)

    if not players:
        await message.answer("📊 <b>No matches played yet!</b>\nUse /challenge to start playing.", parse_mode="HTML")
        return

    lines = ["🏆 <b>Leaderboard — Top 10 Players</b>\n"]

    for i, p in enumerate(players):
        name = p.get("username") or p.get("first_name") or "Unknown"
        wins = p.get("wins", 0)
        total = p.get("total_matches", 0)
        losses = p.get("losses", 0)
        draws = p.get("draws", 0)
        win_pct = round((wins / total * 100), 1) if total > 0 else 0.0
        medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."

        lines.append(
            f"{medal} <b>@{name}</b>\n"
            f"   ✅ {wins}W  ❌ {losses}L  🤝 {draws}D  |  🎯 <b>{win_pct}%</b>  ({total} played)"
        )

    # Battle stats section
    battle_cursor = db.users.find({"total_battles": {"$gt": 0}}).sort("battle_wins", -1).limit(5)
    battle_players = await battle_cursor.to_list(length=5)

    if battle_players:
        lines.append("\n⚔️ <b>Battle Leaderboard — Top 5</b>\n")
        for i, p in enumerate(battle_players):
            name = p.get("username") or p.get("first_name") or "Unknown"
            bw = p.get("battle_wins", 0)
            bt = p.get("total_battles", 0)
            bpct = round((bw / bt * 100), 1) if bt > 0 else 0.0
            medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
            lines.append(f"{medal} <b>@{name}</b>  ⚔️ {bw} battle wins  ({bpct}%)")

    await message.answer("\n".join(lines), parse_mode="HTML")
