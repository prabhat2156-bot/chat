import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandStart

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎮 <b>PvP Gaming Arena Bot</b>\n\n"
        "⚡ Your group's ultimate battle referee!\n\n"
        "Use /help to see all commands.",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "🎮 <b>PvP Gaming Arena Bot — Commands</b>\n\n"
        "<b>⚔️ Play:</b>\n"
        "• /challenge @user — Quick match (no admin needed)\n"
        "• /battle @user — <b>Paid battle</b> with stakes + admin approval\n\n"
        "<b>📊 Stats:</b>\n"
        "• /profile — Your match stats\n"
        "• /leaderboard — Top 10 players\n\n"
        "<b>🏆 Tournament:</b>\n"
        "• /tournament — Create tournament (admins only)\n\n"
        "<b>🎮 Games (10):</b>\n"
        "🎲 Dice  🎯 Dart  🏀 Basketball  ⚽ Football\n"
        "🎳 Bowling  🎰 Slots  🪨 RPS  ⭕ Tic Tac Toe\n"
        "🔢 Guess Number  💎 Treasure Hunt\n\n"
        "<b>⚡ /challenge vs /battle:</b>\n"
        "• <b>/challenge</b> — Free, both confirm → play\n"
        "• <b>/battle</b> — Set amount + rounds → both pay → admin approves → play → winner gets pot\n\n"
        "<b>📋 Rules:</b>\n"
        "• 1 match per player per group at a time\n"
        "• 60s per turn — timeout = forfeit\n"
        "• 🚫 Forfeit button available in every game"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("games"))
async def cmd_games(message: Message):
    text = (
        "🎮 <b>Available Games</b>\n\n"
        "<b>🎲 Telegram Native Dice:</b>\n"
        "🎲 <b>Dice Roll</b>  🎯 <b>Dart</b>  🏀 <b>Basketball</b>\n"
        "⚽ <b>Football</b>  🎳 <b>Bowling</b>  🎰 <b>Slots</b>\n\n"
        "<b>🕹️ Strategy Games:</b>\n"
        "🪨 <b>Rock Paper Scissors</b>\n"
        "⭕ <b>Tic Tac Toe</b>\n"
        "🔢 <b>Guess the Number</b> (1-100)\n"
        "💎 <b>Treasure Hunt</b> (avoid 💣 bombs!)\n\n"
        "Use /challenge @player or /battle @player to start!"
    )
    await message.answer(text, parse_mode="HTML")
