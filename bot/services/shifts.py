from __future__ import annotations

from typing import Any

from bot import texts
from bot.database import execute, fetch_all, fetch_one
from bot.services.payroll import ensure_open_period
from bot.services.schedules import calculate_late_seconds_for_open, get_schedule_bounds_for_datetime
from bot.utils.dates import now_local


async def get_open_shift(user_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM shifts WHERE user_id=%s AND closed_at IS NULL ORDER BY id DESC LIMIT 1",
        (user_id,),
    )


async def open_shift(user_id: int) -> dict[str, Any]:
    existing = await get_open_shift(user_id)
    if existing:
        raise ValueError(texts.SHIFT_ALREADY_OPEN)

    now = now_local()
    user = await fetch_one("SELECT late_excuse_token FROM users WHERE id=%s LIMIT 1", (user_id,))
    excuse_token = bool(user and user.get("late_excuse_token"))

    if excuse_token:
        late_seconds, is_scheduled = 0, True
    else:
        late_seconds, is_scheduled = await calculate_late_seconds_for_open(user_id, now)

    period = await ensure_open_period(user_id)
    now_naive = now.replace(tzinfo=None)

    shift_id = await execute(
        """
        INSERT INTO shifts (
            user_id, payroll_period_id, opened_at, late_seconds, is_scheduled,
            created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            period["id"],
            now_naive,
            late_seconds if is_scheduled else 0,
            1 if is_scheduled else 0,
            now_naive,
            now_naive,
        ),
    )

    if excuse_token:
        await execute(
            "UPDATE users SET late_excuse_token=0, updated_at=%s WHERE id=%s",
            (now_naive, user_id),
        )

    shift = await fetch_one("SELECT * FROM shifts WHERE id=%s", (shift_id,))
    assert shift is not None
    return shift


async def close_shift(user_id: int) -> dict[str, Any]:
    shift = await get_open_shift(user_id)
    if not shift:
        raise ValueError(texts.SHIFT_NOT_OPEN)

    now = now_local()
    opened_at = shift["opened_at"].replace(tzinfo=now.tzinfo)
    duration_seconds = max(0, int((now - opened_at).total_seconds()))
    now_naive = now.replace(tzinfo=None)

    await execute(
        """
        UPDATE shifts
        SET
            closed_at=%s,
            duration_seconds=%s,
            updated_at=%s
        WHERE id=%s
        """,
        (
            now_naive,
            duration_seconds,
            now_naive,
            shift["id"],
        ),
    )

    scheduled_start, scheduled_end, is_scheduled = await get_schedule_bounds_for_datetime(user_id, now)
    if is_scheduled and scheduled_end is not None:
        overtime_seconds = int((now - scheduled_end).total_seconds())
        if overtime_seconds >= 3600:
            await execute(
                "UPDATE users SET late_excuse_token=1, updated_at=%s WHERE id=%s",
                (now_naive, user_id),
            )

    shift["closed_at"] = now_naive
    shift["duration_seconds"] = duration_seconds
    return shift


async def get_active_shifts() -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT s.*, u.full_name, u.username
        FROM shifts s
        JOIN users u ON u.id=s.user_id
        WHERE s.closed_at IS NULL AND u.is_active=1
        ORDER BY s.opened_at DESC
        """
    )

async def get_shift_by_id(shift_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        """
        SELECT s.*, u.full_name, u.username, u.tg_id
        FROM shifts s
        JOIN users u ON u.id=s.user_id
        WHERE s.id=%s
        LIMIT 1
        """,
        (shift_id,),
    )


async def delete_shift(shift_id: int) -> None:
    await execute("DELETE FROM shifts WHERE id=%s", (shift_id,))


async def update_shift_duration_minutes(shift_id: int, minutes: int) -> None:
    now_naive = now_local().replace(tzinfo=None)
    await execute(
        "UPDATE shifts SET duration_seconds=%s, updated_at=%s WHERE id=%s",
        (max(0, int(minutes)) * 60, now_naive, shift_id),
    )
