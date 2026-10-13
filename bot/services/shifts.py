from __future__ import annotations

from typing import Any

from bot import texts
from bot.services.payroll import ensure_open_period
from bot.services.schedules import calculate_late_seconds_for_open, get_schedule_bounds_for_datetime
from bot.utils.dates import now_local
from core.clock import now_naive
from core.repositories import shifts as shifts_repo
from core.repositories import users as users_repo

# Переработка после конца смены, которая даёт право один раз не получить опоздание.
OVERTIME_FOR_EXCUSE_SECONDS = 3600


async def get_open_shift(user_id: int) -> dict[str, Any] | None:
    return await shifts_repo.get_open_for_user(user_id)


async def open_shift(user_id: int) -> dict[str, Any]:
    if await get_open_shift(user_id):
        raise ValueError(texts.SHIFT_ALREADY_OPEN)

    now = now_local()
    excuse_token = await users_repo.has_late_excuse_token(user_id)

    if excuse_token:
        late_seconds, is_scheduled = 0, True
    else:
        late_seconds, is_scheduled = await calculate_late_seconds_for_open(user_id, now)

    period = await ensure_open_period(user_id)
    now_naive_dt = now.replace(tzinfo=None)

    shift_id = await shifts_repo.create(
        user_id=user_id,
        payroll_period_id=period["id"],
        opened_at=now_naive_dt,
        late_seconds=late_seconds if is_scheduled else 0,
        is_scheduled=is_scheduled,
        now=now_naive_dt,
    )

    if excuse_token:
        await users_repo.set_late_excuse_token(user_id, False, now_naive_dt)

    shift = await shifts_repo.get_by_id(shift_id)
    assert shift is not None
    return shift


async def close_shift(user_id: int) -> dict[str, Any]:
    shift = await get_open_shift(user_id)
    if not shift:
        raise ValueError(texts.SHIFT_NOT_OPEN)

    now = now_local()
    opened_at = shift["opened_at"].replace(tzinfo=now.tzinfo)
    duration_seconds = max(0, int((now - opened_at).total_seconds()))
    now_naive_dt = now.replace(tzinfo=None)

    await shifts_repo.close(shift["id"], closed_at=now_naive_dt, duration_seconds=duration_seconds, now=now_naive_dt)

    _, scheduled_end, is_scheduled = await get_schedule_bounds_for_datetime(user_id, now)
    if is_scheduled and scheduled_end is not None:
        overtime_seconds = int((now - scheduled_end).total_seconds())
        if overtime_seconds >= OVERTIME_FOR_EXCUSE_SECONDS:
            await users_repo.set_late_excuse_token(user_id, True, now_naive_dt)

    shift["closed_at"] = now_naive_dt
    shift["duration_seconds"] = duration_seconds
    return shift


async def get_active_shifts() -> list[dict[str, Any]]:
    return await shifts_repo.list_open_with_users()


async def get_shift_by_id(shift_id: int) -> dict[str, Any] | None:
    return await shifts_repo.get_with_user(shift_id)


async def delete_shift(shift_id: int) -> None:
    await shifts_repo.delete(shift_id)


async def update_shift_duration_minutes(shift_id: int, minutes: int) -> None:
    await shifts_repo.set_duration(shift_id, max(0, int(minutes)) * 60, now_naive())
