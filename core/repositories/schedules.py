from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one
from core.repositories._sql import in_placeholders


async def get_active(user_id: int) -> dict[str, Any] | None:
    """Актуальный (последний активный) график сотрудника."""
    return await fetch_one(
        "SELECT * FROM user_schedules WHERE user_id=%s AND is_active=1 ORDER BY id DESC LIMIT 1",
        (user_id,),
    )


async def list_active(user_ids: list[int] | None = None) -> list[dict[str, Any]]:
    """Активные графики (всех или указанных сотрудников), новые первыми."""
    query = "SELECT * FROM user_schedules WHERE is_active=1"
    args: tuple = ()
    if user_ids:
        query += f" AND user_id IN ({in_placeholders(user_ids)})"
        args = tuple(user_ids)
    query += " ORDER BY id DESC"
    return await fetch_all(query, args)


async def deactivate_for_user(user_id: int, now: datetime) -> None:
    await execute(
        "UPDATE user_schedules SET is_active=0, updated_at=%s WHERE user_id=%s AND is_active=1",
        (now, user_id),
    )


async def create(user_id: int, weekdays_json: str, start_time: str, end_time: str, now: datetime) -> None:
    await execute(
        """
        INSERT INTO user_schedules (user_id, weekdays_json, start_time, end_time, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, %s, 1, %s, %s)
        """,
        (user_id, weekdays_json, start_time, end_time, now, now),
    )


async def list_active_employee_schedules() -> list[dict[str, Any]]:
    """Графики активных сотрудников с Telegram — для напоминаний об открытии/закрытии смены."""
    return await fetch_all(
        """
        SELECT
            u.id AS user_id,
            u.tg_id,
            u.full_name,
            s.weekdays_json,
            s.start_time,
            s.end_time
        FROM users u
        JOIN user_schedules s ON s.user_id = u.id AND s.is_active = 1
        WHERE u.is_active = 1 AND u.role = 'employee' AND u.tg_id IS NOT NULL
        """
    )


# ---------- веб-админка ----------

async def update_in_place(schedule_id: int, weekdays_json: str, start_time: str, end_time: str) -> None:
    await execute(
        "UPDATE user_schedules SET weekdays_json=%s, start_time=%s, end_time=%s, updated_at=NOW() WHERE id=%s",
        (weekdays_json, start_time, end_time, schedule_id),
    )


async def create_now(user_id: int, weekdays_json: str, start_time: str, end_time: str) -> None:
    await execute(
        "INSERT INTO user_schedules (user_id, weekdays_json, start_time, end_time, is_active, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, 1, NOW(), NOW())",
        (user_id, weekdays_json, start_time, end_time),
    )
