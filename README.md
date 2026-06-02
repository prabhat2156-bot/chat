# 🎮 PvP Gaming Arena Bot

A fully-featured Telegram Group PvP Challenge Arena Bot built with Python and Aiogram 3.x.

## Features

- **10 Games**: Dice, Dart, Basketball, Football, Bowling, Slots, Rock-Paper-Scissors, Tic Tac Toe, Guess Number, Treasure Hunt
- **Challenge System**: /challenge @user → select game → accept/decline flow
- **Anti-Spam**: One active challenge/match per user, 2-minute challenge expiry
- **Timeout System**: 60s per turn with warning, auto-forfeit on second timeout
- **Profile System**: Full stats per player and per game
- **Rematch System**: Same players, same game, instant restart
- **Tournament System**: Admin-only, brackets, multi-game, Best of 3/5 finals
- **Live Spectator Mode**: All matches visible to group members
- **Group-Only**: Works only in groups/supergroups
- **Multi-group & Multi-match**: Supports simultaneous matches across groups

## Setup

### 1. Clone / Extract
```bash
unzip telegram_pvp_bot.zip
cd telegram-pvp-bot
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env and fill in BOT_TOKEN and MONGODB_URI
```

### 4. Start MongoDB
Make sure MongoDB is running locally, or use a MongoDB Atlas cloud URI.

### 5. Run the bot
```bash
python bot.py
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Show all commands |
| `/games` | List all games |
| `/challenge @user` | Challenge a player |
| `/profile` | View your stats |
| `/profile` (reply) | View another player's stats |
| `/tournament` | Create tournament (admins only) |

## Games

### Telegram Native Games (turn-based, use real emoji dice)
- 🎲 **Dice Roll** — Each player rolls, highest wins
- 🎯 **Dart** — Each player throws, highest wins
- 🏀 **Basketball** — Each player shoots, highest wins
- ⚽ **Football** — Each player kicks, highest wins
- 🎳 **Bowling** — Each player rolls, highest wins
- 🎰 **Slot Machine** — Each player spins, best combo wins

### Custom Games
- 🪨 **Rock Paper Scissors** — Both pick simultaneously, reveal after
- ⭕ **Tic Tac Toe** — Classic 3x3 board on inline keyboard
- 🔢 **Guess Number** — Bot picks 1-100, take turns guessing with hints
- 💎 **Treasure Hunt** — 3x3 grid, 7 diamonds + 2 bombs, hit bomb = instant loss

## Tournament System

1. Admin runs `/tournament`
2. Select games (one or multiple)
3. Set size (4/8/16/32/64 or custom even number)
4. Choose final format (Single / Best of 3 / Best of 5)
5. Players join via button
6. Brackets auto-generate and matches begin
7. Winners advance automatically
8. Champion announced at the end

## Architecture

```
telegram-pvp-bot/
├── bot.py                  # Entry point
├── config.py               # Configuration constants
├── requirements.txt
├── .env.example
├── database/
│   ├── mongodb.py          # DB connection & indexes
│   └── models.py           # Document schemas
├── games/
│   ├── native_dice.py      # Dice/Dart/Basketball/Football/Bowling/Slots
│   ├── rps.py              # Rock Paper Scissors
│   ├── tictactoe.py        # Tic Tac Toe
│   ├── guess_number.py     # Guess the Number
│   └── treasure_hunt.py    # Treasure Hunt
├── handlers/
│   ├── misc.py             # /start /help /games
│   ├── challenge.py        # Challenge flow
│   ├── match.py            # In-game actions & timeouts
│   ├── profile.py          # /profile command
│   └── tournament.py       # Tournament system
├── middlewares/
│   └── group_only.py       # Blocks private chat usage
└── utils/
    ├── keyboards.py        # All inline keyboards
    ├── timeout_manager.py  # Async timeout scheduling
    └── db_helpers.py       # DB utility functions
```

## Requirements

- Python 3.10+
- MongoDB 5.0+ (or MongoDB Atlas)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

## BotFather Setup

1. Create a bot via @BotFather → `/newbot`
2. Get the token, paste into `.env`
3. Set commands via `/setcommands`:
```
start - Start the bot
help - Show help
games - List all games
challenge - Challenge a player
profile - View your stats
tournament - Create a tournament
```
4. Enable inline mode is NOT required
5. Enable group privacy to OFF: `/setprivacy` → Disable (so bot can read messages for Guess Number game)
