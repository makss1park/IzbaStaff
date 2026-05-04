from __future__ import annotations

from typing import Any

from bot.database import execute, fetch_all, fetch_one
from bot.utils.dates import now_local


async def ensure_open_period(user_id: int) -> dict[str, Any]:
    period = await fetch_one(
        "SELECT * FROM payroll_periods WHERE user_id=%s AND is_closed=0 ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    if period:
        return period
    now = now_local().replace(tzinfo=None)
    await execute(
        "INSERT INTO payroll_periods (user_id, start_at, is_closed, created_at, updated_at) VALUES (%s, %s, 0, %s, %s)",
        (user_id, now, now, now),
    )
    period = await fetch_one(
        "SELECT * FROM payroll_periods WHERE user_id=%s AND is_closed=0 ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    assert period is not None
    return period


async def get_current_period_stats(user_id: int) -> dict[str, Any]:
    period = await ensure_open_period(user_id)
    shift_stats = await fetch_one(
        """
        SELECT COUNT(*) AS shift_count,
               COALESCE(SUM(duration_seconds), 0) AS work_seconds,
               COALESCE(SUM(CASE WHEN late_seconds > 0 THEN 1 ELSE 0 END), 0) AS late_count,
               COALESCE(SUM(late_seconds), 0) AS late_seconds
        FROM shifts
        WHERE user_id=%s AND payroll_period_id=%s AND closed_at IS NOT NULL
        """,
        (user_id, period["id"]),
    ) or {}
    fine_stats = await fetch_one(
        "SELECT COALESCE(SUM(amount), 0) AS fine_amount FROM fines WHERE user_id=%s AND payroll_period_id=%s",
        (user_id, period["id"]),
    ) or {}
    user = await fetch_one("SELECT hourly_rate FROM users WHERE id=%s", (user_id,)) or {"hourly_rate": 0}
    earned = (float(user["hourly_rate"]) * (int(shift_stats.get("work_seconds", 0)) / 3600.0)) - float(fine_stats.get("fine_amount", 0))
    return {
        "period_id": period["id"],
        "shift_count": int(shift_stats.get("shift_count", 0) or 0),
        "work_seconds": int(shift_stats.get("work_seconds", 0) or 0),
        "late_count": int(shift_stats.get("late_count", 0) or 0),
        "late_seconds": int(shift_stats.get("late_seconds", 0) or 0),
        "fine_amount": float(fine_stats.get("fine_amount", 0) or 0),
        "earned_amount": round(earned, 2),
    }


async def close_current_period_and_open_new(user_id: int) -> None:
    period = await ensure_open_period(user_id)
    now = now_local().replace(tzinfo=None)
    await execute(
        "UPDATE payroll_periods SET is_closed=1, end_at=%s, updated_at=%s WHERE id=%s",
        (now, now, period["id"]),
    )
    await execute(
        "INSERT INTO payroll_periods (user_id, start_at, is_closed, created_at, updated_at) VALUES (%s, %s, 0, %s, %s)",
        (user_id, now, now, now),
    )


async def bulk_close_periods(user_ids: list[int]) -> None:
    for user_id in user_ids:
        await close_current_period_and_open_new(user_id)


async def get_period_stats_for_users(user_ids: list[int]) -> list[dict[str, Any]]:
    result = []
    for user_id in user_ids:
        stats = await get_current_period_stats(user_id)
        stats["user_id"] = user_id
        result.append(stats)
    return result


async def get_current_period_shift_list(user_id: int) -> list[dict[str, Any]]:
    period = await ensure_open_period(user_id)
    return await fetch_all(
        """
        SELECT id, opened_at, closed_at, duration_seconds
        FROM shifts
        WHERE user_id=%s AND payroll_period_id=%s AND closed_at IS NOT NULL
        ORDER BY opened_at DESC
        """,
        (user_id, period["id"]),
    )


async def get_current_period_fines(user_id: int) -> list[dict[str, Any]]:
    period = await ensure_open_period(user_id)
    return await fetch_all(
        """
        SELECT id, amount, reason, created_at
        FROM fines
        WHERE user_id=%s AND payroll_period_id=%s
        ORDER BY created_at DESC, id DESC
        """,
        (user_id, period["id"]),
    )
