"""Журнал отправленных напоминаний по графику (schedule_notification_logs)."""
from __future__ import annotations

from datetime import date, datetime

from core.db import execute, fetch_one


async def was_sent(user_id: int, reminder_type: str, reminder_date: date) -> bool:
    row = await fetch_one(
        "SELECT id FROM schedule_notification_logs WHERE user_id=%s AND reminder_type=%s AND reminder_date=%s LIMIT 1",
        (user_id, reminder_type, reminder_date),
    )
    return row is not None


async def mark_sent(user_id: int, reminder_type: str, reminder_date: date, now: datetime) -> None:
    await execute(
        "INSERT INTO schedule_notification_logs (user_id, reminder_type, reminder_date, created_at) VALUES (%s, %s, %s, %s)",
        (user_id, reminder_type, reminder_date, now),
    )
