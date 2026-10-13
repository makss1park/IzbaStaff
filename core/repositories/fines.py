from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one


async def create(
    *,
    user_id: int,
    payroll_period_id: int,
    amount: float,
    reason: str,
    created_by: int,
    now: datetime,
) -> None:
    await execute(
        "INSERT INTO fines (user_id, payroll_period_id, amount, reason, created_at, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, payroll_period_id, amount, reason, now, created_by),
    )


async def total_for_period(user_id: int, period_id: int) -> float:
    row = await fetch_one(
        "SELECT COALESCE(SUM(amount), 0) AS fine_amount FROM fines WHERE user_id=%s AND payroll_period_id=%s",
        (user_id, period_id),
    ) or {}
    return float(row.get("fine_amount", 0) or 0)


async def list_for_user_period(user_id: int, period_id: int) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT id, amount, reason, created_at
        FROM fines
        WHERE user_id=%s AND payroll_period_id=%s
        ORDER BY created_at DESC, id DESC
        """,
        (user_id, period_id),
    )


async def list_for_period(period_id: int) -> list[dict[str, Any]]:
    """Штрафы периода с округлённой суммой — для веб-админки."""
    return await fetch_all(
        "SELECT *, CAST(ROUND(amount, 0) AS SIGNED) AS amount_int FROM fines WHERE payroll_period_id=%s ORDER BY created_at DESC",
        (period_id,),
    )
