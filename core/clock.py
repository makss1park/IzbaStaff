from __future__ import annotations

from datetime import datetime

from bot.config import settings


def now_naive() -> datetime:
    """Текущее время в часовом поясе приложения без tzinfo — в таком виде даты пишутся в БД."""
    return datetime.now(settings.tzinfo).replace(tzinfo=None)
