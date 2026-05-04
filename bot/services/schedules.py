from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from bot.database import execute, fetch_all, fetch_one
from bot.utils.dates import now_local, parse_hhmm


async def get_active_schedule(user_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM user_schedules WHERE user_id=%s AND is_active=1 ORDER BY id DESC LIMIT 1",
        (user_id,),
    )


async def get_schedules_map(user_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    query = "SELECT * FROM user_schedules WHERE is_active=1"
    args: tuple = ()
    if user_ids:
        placeholders = ",".join(["%s"] * len(user_ids))
        query += f" AND user_id IN ({placeholders})"
        args = tuple(user_ids)
    query += " ORDER BY id DESC"
    rows = await fetch_all(query, args)

    schedules_map: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row["user_id"] not in schedules_map:
            schedules_map[row["user_id"]] = row
    return schedules_map


async def set_schedule(user_ids: list[int], weekdays: list[int], start_time: str, end_time: str) -> None:
    now = now_local().replace(tzinfo=None)
    for user_id in user_ids:
        await execute(
            "UPDATE user_schedules SET is_active=0, updated_at=%s WHERE user_id=%s AND is_active=1",
            (now, user_id),
        )
        await execute(
            """
            INSERT INTO user_schedules (user_id, weekdays_json, start_time, end_time, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
            """,
            (user_id, json.dumps(weekdays), start_time, end_time, now, now),
        )


async def get_schedule_bounds_for_datetime(user_id: int, target_dt: datetime) -> tuple[datetime | None, datetime | None, bool]:
    schedule = await get_active_schedule(user_id)
    if not schedule:
        return None, None, False

    weekdays = json.loads(schedule["weekdays_json"])
    weekday = target_dt.isoweekday()
    if weekday not in weekdays:
        return None, None, False

    start_hour, start_minute = parse_hhmm(schedule["start_time"])
    end_hour, end_minute = parse_hhmm(schedule["end_time"])

    scheduled_start = target_dt.replace(
        hour=start_hour,
        minute=start_minute,
        second=0,
        microsecond=0,
    )
    scheduled_end = target_dt.replace(
        hour=end_hour,
        minute=end_minute,
        second=0,
        microsecond=0,
    )

    return scheduled_start, scheduled_end, True


async def calculate_late_seconds_for_open(user_id: int, opened_at: datetime) -> tuple[int, bool]:
    scheduled_start, scheduled_end, is_scheduled = await get_schedule_bounds_for_datetime(user_id, opened_at)
    if not is_scheduled or scheduled_start is None or scheduled_end is None:
        return 0, False

    if opened_at > scheduled_end:
        return 0, False

    if opened_at <= scheduled_start:
        return 0, True

    late_seconds = int((opened_at - scheduled_start).total_seconds())
    return late_seconds, True
