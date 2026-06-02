import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database.mongodb import connect_db, disconnect_db
from handlers import misc, challenge, profile, match, tournament
from middlewares.group_only import GroupOnlyMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Please set it in your .env file.")
        sys.exit(1)

    await connect_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.message.outer_middleware(GroupOnlyMiddleware())

    dp.include_router(misc.router)
    dp.include_router(challenge.router)
    dp.include_router(profile.router)
    dp.include_router(match.router)
    dp.include_router(tournament.router)

    try:
        logger.info("Starting bot...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await disconnect_db()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
