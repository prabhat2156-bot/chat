from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable


class GroupOnlyMiddleware(BaseMiddleware):
    """
    Pass-through middleware — bot works in ANY group and in private chats.
    No whitelist required. Individual command handlers check admin status
    where needed (e.g. /feeset).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        return await handler(event, data)
