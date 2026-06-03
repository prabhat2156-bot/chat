import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("DB_NAME", "pvp_arena_bot")

# Bot owner (Telegram user ID) — set via env var
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))

# Timeouts (seconds)
CHALLENGE_TIMEOUT: int = 120
TURN_TIMEOUT: int = 60
TURN_WARNING_TIMEOUT: int = 60
BATTLE_FORM_TIMEOUT: int = 600   # 10 min to fill form
BATTLE_PAY_TIMEOUT: int = 1800   # 30 min to pay
BATTLE_READY_TIMEOUT: int = 300  # 5 min to confirm ready

# Fee defaults (owner can override per-group via /setfee)
DEFAULT_FEE_PERCENT: float = float(os.getenv("DEFAULT_FEE_PERCENT", "10"))

GAME_NAMES = {
    "dice": "🎲 Dice Roll",
    "dart": "🎯 Dart",
    "basketball": "🏀 Basketball",
    "football": "⚽ Football",
    "bowling": "🎳 Bowling",
    "slots": "🎰 Slot Machine",
    "rps": "🪨 Rock Paper Scissors",
    "tictactoe": "⭕ Tic Tac Toe",
    "guess": "🔢 Guess Number",
    "treasure": "💎 Treasure Hunt",
}

GAME_EMOJI = {
    "dice": "🎲",
    "dart": "🎯",
    "basketball": "🏀",
    "football": "⚽",
    "bowling": "🎳",
    "slots": "🎰",
    "rps": "🪨",
    "tictactoe": "⭕",
    "guess": "🔢",
    "treasure": "💎",
}

NATIVE_DICE_GAMES = ["dice", "dart", "basketball", "football", "bowling", "slots"]
CUSTOM_GAMES = ["rps", "tictactoe", "guess", "treasure"]

DICE_EMOJI_MAP = {
    "dice": "🎲",
    "dart": "🎯",
    "basketball": "🏀",
    "football": "⚽",
    "bowling": "🎳",
    "slots": "🎰",
}

DICE_MAX_VALUE = {
    "dice": 6,
    "dart": 6,
    "basketball": 5,
    "football": 5,
    "bowling": 6,
    "slots": 64,
}
