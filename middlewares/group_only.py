from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable


class GroupOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            chat = event.chat
            if chat.type == "private":
                await event.answer(
                    "❌ This bot only works in groups.",
                    parse_mode=None,
                )
                return
        elif isinstance(event, CallbackQuery):
            if event.message and event.message.chat.type == "private":
                await event.answer(
                    "❌ This bot only works in groups.",
                    show_alert=True,
                )
                return
        return await handler(event, data)
