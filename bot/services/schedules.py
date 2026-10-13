from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from bot.utils.dates import parse_hhmm
from core.clock import now_naive
from core.repositories import schedules as schedules_repo


async def get_active_schedule(user_id: int) -> dict[str, Any] | None:
    return await schedules_repo.get_active(user_id)


async def get_schedules_map(user_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    """{user_id: актуальный график}. Если у сотрудника несколько активных, берётся последний."""
    schedules_map: dict[int, dict[str, Any]] = {}
    for row in await schedules_repo.list_active(user_ids):
        schedules_map.setdefault(row["user_id"], row)
    return schedules_map


async def set_schedule(user_ids: list[int], weekdays: list[int], start_time: str, end_time: str) -> None:
    """Деактивирует прежний график и создаёт новый для каждого сотрудника."""
    now = now_naive()
    for user_id in user_ids:
        await schedules_repo.deactivate_for_user(user_id, now)
        await schedules_repo.create(user_id, json.dumps(weekdays), start_time, end_time, now)


async def get_schedule_bounds_for_datetime(user_id: int, target_dt: datetime) -> tuple[datetime | None, datetime | None, bool]:
    schedule = await get_active_schedule(user_id)
    if not schedule:
        return None, None, False

    weekdays = json.loads(schedule["weekdays_json"])
    if target_dt.isoweekday() not in weekdays:
        return None, None, False

    start_hour, start_minute = parse_hhmm(schedule["start_time"])
    end_hour, end_minute = parse_hhmm(schedule["end_time"])

    scheduled_start = target_dt.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    scheduled_end = target_dt.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
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
