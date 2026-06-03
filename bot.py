import asyncio
import logging
import sys
import os
import threading

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask, jsonify

from config import BOT_TOKEN
from database.mongodb import connect_db, disconnect_db
from handlers import misc, challenge, profile, match, tournament
from handlers import battle, leaderboard, owner
from middlewares.group_only import GroupOnlyMiddleware
from middlewares.user_tracking import UserTrackingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─── Flask health server ──────────────────────────────────────────────────────
flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return jsonify({"status": "ok", "bot": "PvP Gaming Arena Bot"})


@flask_app.route("/health")
def health():
    return jsonify({"status": "healthy"})


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False, debug=False)


# ─── Bot startup ─────────────────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Add it to your .env file.")
        sys.exit(1)

    flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskHealth")
    flask_thread.start()
    logger.info(f"🌐 Flask health server started on port {os.environ.get('PORT', 8080)}")

    await connect_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.message.outer_middleware(GroupOnlyMiddleware())
    dp.callback_query.outer_middleware(GroupOnlyMiddleware())  # FIX: also filter button presses
    dp.message.middleware(UserTrackingMiddleware())

    # Routers — ORDER MATTERS:
    # 1. misc (start/help/games) — always first
    # 2. owner — DM-only owner commands
    # 3. leaderboard — /leaderboard
    # 4. profile — /profile
    # 5. tournament — /tournament + FSM
    # 6. battle — /battle + paid battle system (has FSM states)
    # 7. match — game callbacks + guess number + rematch/newgame
    # 8. challenge — /challenge (no catch-all; placed last)

    dp.include_router(misc.router)
    dp.include_router(owner.router)
    dp.include_router(leaderboard.router)
    dp.include_router(profile.router)
    dp.include_router(tournament.router)
    dp.include_router(battle.router)    # battle FSM states + UPI catch before match
    dp.include_router(match.router)     # guess number + rematch/newgame
    dp.include_router(challenge.router)

    try:
        logger.info("🎮 PvP Gaming Arena Bot starting up...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await disconnect_db()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
