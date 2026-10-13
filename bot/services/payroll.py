from __future__ import annotations

from typing import Any

from core.clock import now_naive
from core.repositories import fines as fines_repo
from core.repositories import payroll as payroll_repo
from core.repositories import shifts as shifts_repo
from core.repositories import users as users_repo


async def ensure_open_period(user_id: int) -> dict[str, Any]:
    """Текущий открытый зарплатный период сотрудника; создаёт его, если открытого нет."""
    period = await payroll_repo.get_open_period(user_id)
    if period:
        return period
    now = now_naive()
    await payroll_repo.create_period(user_id, now, now)
    period = await payroll_repo.get_open_period(user_id)
    assert period is not None
    return period


async def get_current_period_stats(user_id: int) -> dict[str, Any]:
    period = await ensure_open_period(user_id)
    shift_stats = await shifts_repo.closed_stats_for_period(user_id, period["id"])
    fine_amount = await fines_repo.total_for_period(user_id, period["id"])
    hourly_rate = await users_repo.get_hourly_rate(user_id)

    work_seconds = int(shift_stats.get("work_seconds", 0) or 0)
    earned = hourly_rate * (work_seconds / 3600.0) - fine_amount
    return {
        "period_id": period["id"],
        "shift_count": int(shift_stats.get("shift_count", 0) or 0),
        "work_seconds": work_seconds,
        "late_count": int(shift_stats.get("late_count", 0) or 0),
        "late_seconds": int(shift_stats.get("late_seconds", 0) or 0),
        "fine_amount": fine_amount,
        "earned_amount": round(earned, 2),
    }


async def close_current_period_and_open_new(user_id: int) -> None:
    period = await ensure_open_period(user_id)
    now = now_naive()
    await payroll_repo.close_period(period["id"], now, now)
    await payroll_repo.create_period(user_id, now, now)


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
    return await shifts_repo.list_closed_for_period(user_id, period["id"])


async def get_current_period_fines(user_id: int) -> list[dict[str, Any]]:
    period = await ensure_open_period(user_id)
    return await fines_repo.list_for_user_period(user_id, period["id"])
