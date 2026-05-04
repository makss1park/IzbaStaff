from __future__ import annotations

from bot import texts

from datetime import datetime, timedelta

from bot.config import settings


def now_local() -> datetime:
    return datetime.now(settings.tzinfo)


def parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("invalid time format")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("invalid time value")
    return hour, minute


def seconds_to_human(seconds: int) -> str:
    total_minutes = max(seconds, 0) // 60
    hours, minutes = divmod(total_minutes, 60)
    return texts.DURATION_HOURS_MINUTES.format(hours=hours, minutes=minutes)


def daterange_start(days: int) -> datetime:
    return now_local() - timedelta(days=days)
