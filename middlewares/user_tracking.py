from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from typing import Callable, Dict, Any, Awaitable


class UserTrackingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            user = event.from_user
            if user and not user.is_bot and event.chat.type != "private":
                try:
                    from utils.db_helpers import get_or_create_user
                    await get_or_create_user(
                        user.id,
                        user.username or "",
                        user.first_name or "",
                    )
                except Exception:
                    pass
        return await handler(event, data)
