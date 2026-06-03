import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database.mongodb import get_db
from utils.db_helpers import get_or_create_user
from config import GAME_NAMES, GAME_EMOJI

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    if message.chat.type == "private":
        await message.answer("❌ This bot only works in groups.")
        return

    target_user = message.from_user
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user

    db = get_db()
    user = await get_or_create_user(
        target_user.id,
        target_user.username or "",
        target_user.first_name or "",
    )

    total = user.get("total_matches", 0)
    wins = user.get("wins", 0)
    losses = user.get("losses", 0)
    draws = user.get("draws", 0)
    win_rate = round((wins / total * 100) if total > 0 else 0, 1)

    username_display = f"@{user.get('username')}" if user.get("username") else user.get("first_name", "Unknown")

    lines = [
        f"👤 <b>Player: {username_display}</b>",
        "",
        f"🎮 Matches: {total}",
        f"🏆 Wins: {wins}",
        f"❌ Losses: {losses}",
        f"🤝 Draws: {draws}",
        "",
        f"📊 Win Rate: {win_rate}%",
    ]

    game_stats = user.get("game_stats", {})
    if game_stats:
        lines.append("")
        lines.append("🎯 <b>Per-Game Stats:</b>")
        for game_key, stats in game_stats.items():
            if not isinstance(stats, dict):
                continue
            g_total = stats.get("matches", 0)
            if g_total == 0:
                continue
            g_wins = stats.get("wins", 0)
            g_losses = stats.get("losses", 0)
            g_wr = round((g_wins / g_total * 100) if g_total > 0 else 0, 1)
            emoji = GAME_EMOJI.get(game_key, "🎮")
            name = GAME_NAMES.get(game_key, game_key)
            lines.append(f"  {emoji} {name}: {g_total} played | {g_wins}W {g_losses}L | {g_wr}%")

    joined = user.get("joined_at")
    if joined:
        date_str = joined.strftime("%Y-%m-%d") if hasattr(joined, "strftime") else str(joined)[:10]
        lines.append("")
        lines.append(f"📅 Joined: {date_str}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    await cmd_profile(message)
