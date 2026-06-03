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
    # FIX: missing indexes for frequently queried collections
    await db.battles.create_index("battle_id", unique=True)
    await db.battles.create_index([("group_id", 1), ("status", 1)])
    await db.battles.create_index([("challenger_id", 1), ("status", 1)])
    await db.battles.create_index([("opponent_id", 1), ("status", 1)])
    await db.battle_upi_waiting.create_index([("user_id", 1), ("group_id", 1)], unique=True)
    await db.match_confirmations.create_index("confirm_id", unique=True)
    await db.match_confirmations.create_index([("player1_id", 1), ("status", 1)])
    await db.match_confirmations.create_index([("player2_id", 1), ("status", 1)])
    await db.rematch_requests.create_index("req_id", unique=True)
    await db.rematch_requests.create_index([("opponent_id", 1), ("status", 1)])
    await db.newgame_requests.create_index("req_id", unique=True)
    await db.newgame_requests.create_index([("opponent_id", 1), ("status", 1)])


def get_db():
    return db
