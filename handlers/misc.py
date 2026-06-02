import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandStart

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "❌ This bot only works in groups.\n\n"
            "Add me to a group and use /help to see all commands!"
        )
        return

    await message.answer(
        "🎮 <b>PvP Gaming Arena Bot</b>\n\n"
        "Welcome! I'm the referee, match manager, and score tracker.\n\n"
        "Use /help to see all available commands.",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if message.chat.type == "private":
        await message.answer("❌ This bot only works in groups.")
        return

    text = (
        "🎮 <b>PvP Gaming Arena Bot</b>\n\n"
        "<b>Commands:</b>\n"
        "• /challenge @username — Challenge a player\n"
        "• /profile — View your stats\n"
        "• /profile (reply) — View another player's stats\n"
        "• /tournament — Create a tournament (admins only)\n"
        "• /games — List all available games\n"
        "• /help — Show this help\n\n"
        "<b>Available Games:</b>\n"
        "🎲 Dice Roll | 🎯 Dart | 🏀 Basketball\n"
        "⚽ Football | 🎳 Bowling | 🎰 Slots\n"
        "🪨 Rock Paper Scissors | ⭕ Tic Tac Toe\n"
        "🔢 Guess Number | 💎 Treasure Hunt\n\n"
        "<b>How to play:</b>\n"
        "1. Use /challenge @opponent to start\n"
        "2. Select a game from the menu\n"
        "3. Opponent accepts or declines\n"
        "4. Play the match!\n\n"
        "⏳ Each turn has a 60-second timeout."
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("games"))
async def cmd_games(message: Message):
    if message.chat.type == "private":
        await message.answer("❌ This bot only works in groups.")
        return

    text = (
        "🎮 <b>Available Games</b>\n\n"
        "<b>Telegram Native:</b>\n"
        "🎲 Dice Roll — Highest roll wins\n"
        "🎯 Dart — Highest score wins\n"
        "🏀 Basketball — Highest score wins\n"
        "⚽ Football — Highest score wins\n"
        "🎳 Bowling — Highest score wins\n"
        "🎰 Slot Machine — Best combo wins\n\n"
        "<b>Custom Games:</b>\n"
        "🪨 Rock Paper Scissors — Classic RPS\n"
        "⭕ Tic Tac Toe — Get 3 in a row\n"
        "🔢 Guess Number — Guess 1-100, hints given\n"
        "💎 Treasure Hunt — Find gems, avoid bombs\n\n"
        "Use /challenge @player to start a match!"
    )
    await message.answer(text, parse_mode="HTML")
