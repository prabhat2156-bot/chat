from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGODB_URI, DB_NAME
import logging

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DB_NAME]
    await _create_indexes()
    logger.info("Connected to MongoDB")


async def disconnect_db():
    global client
    if client:
        client.close()
        logger.info("Disconnected from MongoDB")


async def _create_indexes():
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("username")
    await db.matches.create_index("match_id", unique=True)
    await db.matches.create_index([("status", 1), ("group_id", 1)])
    await db.matches.create_index([("player1_id", 1), ("status", 1)])
    await db.matches.create_index([("player2_id", 1), ("status", 1)])
    await db.challenges.create_index("challenge_id", unique=True)
    await db.challenges.create_index([("challenger_id", 1), ("status", 1)])
    await db.challenges.create_index([("opponent_id", 1), ("status", 1)])
    await db.challenge_selections.create_index("user_id", unique=True)
    await db.tournaments.create_index("tournament_id", unique=True)
    await db.tournaments.create_index([("group_id", 1), ("status", 1)])


def get_db():
    return db
