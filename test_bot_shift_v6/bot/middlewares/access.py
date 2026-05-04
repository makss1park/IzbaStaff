from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject, Update

from bot import texts
from bot.config import settings
from bot.services.users import ensure_user
from bot.texts import ACCESS_DENIED

_ACCESS_CACHE_TTL_SECONDS = 300
_access_cache: dict[int, tuple[float, bool]] = {}


def _extract_from_user(event: TelegramObject):
    from_user = getattr(event, "from_user", None)
    if from_user is not None:
        return from_user

    if isinstance(event, Update):
        for attr in (
            "message",
            "edited_message",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
            "my_chat_member",
            "chat_member",
            "chat_join_request",
        ):
            obj = getattr(event, attr, None)
            if obj is None:
                continue
            user = getattr(obj, "from_user", None) or getattr(obj, "from", None)
            if user is not None:
                return user

    return None


def _get_cached_access(user_id: int) -> bool | None:
    cached = _access_cache.get(user_id)
    if not cached:
        return None

    expires_at, value = cached
    if expires_at <= time.monotonic():
        _access_cache.pop(user_id, None)
        return None

    return value


def _set_cached_access(user_id: int, value: bool) -> None:
    _access_cache[user_id] = (time.monotonic() + _ACCESS_CACHE_TTL_SECONDS, value)


async def _has_group_access(bot, user_id: int) -> bool:
    cached = _get_cached_access(user_id)
    if cached is not None:
        return cached

    try:
        member = await bot.get_chat_member(settings.allowed_group_id, user_id)
        allowed = member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    except Exception:
        allowed = False

    _set_cached_access(user_id, allowed)
    return allowed


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        from_user = _extract_from_user(event)
        bot = data.get("bot")

        if from_user and bot:
            allowed = await _has_group_access(bot, from_user.id)
            if not allowed:
                if isinstance(event, Message):
                    await event.answer(ACCESS_DENIED)
                elif isinstance(event, CallbackQuery):
                    await event.answer(ACCESS_DENIED, show_alert=True)
                elif isinstance(event, InlineQuery):
                    await event.answer(
                        [],
                        cache_time=1,
                        is_personal=True,
                        switch_pm_text=texts.INLINE_SWITCH_PM_NO_ACCESS,
                        switch_pm_parameter="start",
                    )
                elif isinstance(event, Update):
                    if event.message:
                        await event.message.answer(ACCESS_DENIED)
                    elif event.callback_query:
                        await event.callback_query.answer(ACCESS_DENIED, show_alert=True)
                    elif event.inline_query:
                        await event.inline_query.answer(
                            [],
                            cache_time=1,
                            is_personal=True,
                            switch_pm_text=texts.INLINE_SWITCH_PM_NO_ACCESS,
                            switch_pm_parameter="start",
                        )
                return None

        return await handler(event, data)


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = _extract_from_user(event)
        if user:
            full_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip() or None
            db_user = await ensure_user(user.id, user.username, full_name)
            data["db_user"] = db_user
            data["is_admin"] = db_user["role"] == "admin"
            data["settings"] = settings
        return await handler(event, data)