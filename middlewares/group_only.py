import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable

logger = logging.getLogger(__name__)


class GroupOnlyMiddleware(BaseMiddleware):
    """
    - Private messages: always allowed (owner uses DM for management commands).
    - Group messages: only allowed if the group is whitelisted by the bot owner.
      If not whitelisted, messages are silently ignored.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            chat = event.chat
            if chat.type == "private":
                # Allow all DMs (owner commands, UPI input, etc.)
                return await handler(event, data)

            if chat.type in ("group", "supergroup"):
                if not await self._is_group_allowed(chat.id):
                    # Silently ignore — don't even respond
                    return
                return await handler(event, data)

        elif isinstance(event, CallbackQuery):
            if event.message:
                chat = event.message.chat
                if chat.type == "private":
                    return await handler(event, data)
                if chat.type in ("group", "supergroup"):
                    if not await self._is_group_allowed(chat.id):
                        await event.answer("❌ This bot is not enabled in this group.", show_alert=True)
                        return
            return await handler(event, data)

        return await handler(event, data)

    @staticmethod
    async def _is_group_allowed(group_id: int) -> bool:
        try:
            from database.mongodb import get_db
            db = get_db()
            settings = await db.group_settings.find_one({"group_id": group_id, "allowed": True})
            return settings is not None
        except Exception as e:
            logger.error(f"GroupWhitelist check failed: {e}")
            return False
