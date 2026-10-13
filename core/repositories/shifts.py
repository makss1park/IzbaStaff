from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one
from core.repositories._sql import Where, like, paginate


async def get_by_id(shift_id: int) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM shifts WHERE id=%s", (shift_id,))


async def get_with_user(shift_id: int) -> dict[str, Any] | None:
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


async def get_open_for_user(user_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM shifts WHERE user_id=%s AND closed_at IS NULL ORDER BY id DESC LIMIT 1",
        (user_id,),
    )


async def list_open_with_users() -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT s.*, u.full_name, u.username
        FROM shifts s
        JOIN users u ON u.id=s.user_id
        WHERE s.closed_at IS NULL AND u.is_active=1
        ORDER BY s.opened_at DESC
        """
    )


async def create(
    *,
    user_id: int,
    payroll_period_id: int,
    opened_at: datetime,
    late_seconds: int,
    is_scheduled: bool,
    now: datetime,
) -> int:
    return await execute(
        """
        INSERT INTO shifts (
            user_id, payroll_period_id, opened_at, late_seconds, is_scheduled,
            created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, payroll_period_id, opened_at, late_seconds, 1 if is_scheduled else 0, now, now),
    )


async def close(shift_id: int, *, closed_at: datetime, duration_seconds: int, now: datetime) -> None:
    await execute(
        """
        UPDATE shifts
        SET
            closed_at=%s,
            duration_seconds=%s,
            updated_at=%s
        WHERE id=%s
        """,
        (closed_at, duration_seconds, now, shift_id),
    )


async def set_duration(shift_id: int, duration_seconds: int, now: datetime) -> None:
    await execute(
        "UPDATE shifts SET duration_seconds=%s, updated_at=%s WHERE id=%s",
        (duration_seconds, now, shift_id),
    )


async def delete(shift_id: int) -> None:
    await execute("DELETE FROM shifts WHERE id=%s", (shift_id,))


# ---------- статистика периода ----------

async def closed_stats_for_period(user_id: int, period_id: int) -> dict[str, Any]:
    return await fetch_one(
        """
        SELECT COUNT(*) AS shift_count,
               COALESCE(SUM(duration_seconds), 0) AS work_seconds,
               COALESCE(SUM(CASE WHEN late_seconds > 0 THEN 1 ELSE 0 END), 0) AS late_count,
               COALESCE(SUM(late_seconds), 0) AS late_seconds
        FROM shifts
        WHERE user_id=%s AND payroll_period_id=%s AND closed_at IS NOT NULL
        """,
        (user_id, period_id),
    ) or {}


async def list_closed_for_period(user_id: int, period_id: int) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT id, opened_at, closed_at, duration_seconds
        FROM shifts
        WHERE user_id=%s AND payroll_period_id=%s AND closed_at IS NOT NULL
        ORDER BY opened_at DESC
        """,
        (user_id, period_id),
    )


# ---------- веб-админка ----------

async def search_page(
    *,
    employee_id: int | None = None,
    employee_query: str = "",
    status: str = "all",
    date_from: str = "",
    date_to: str = "",
    page: int,
    page_size: int,
) -> dict[str, Any]:
    where = Where()
    if employee_id:
        where.add("s.user_id = %s", employee_id)
    elif employee_query.strip():
        pattern = like(employee_query)
        where.add("(u.full_name LIKE %s OR u.username LIKE %s)", pattern, pattern)
    if status == "open":
        where.add("s.closed_at IS NULL")
    elif status == "closed":
        where.add("s.closed_at IS NOT NULL")
    if date_from.strip():
        where.add("DATE(s.opened_at) >= %s", date_from.strip())
    if date_to.strip():
        where.add("DATE(s.opened_at) <= %s", date_to.strip())

    base_query = f"""
        SELECT s.*, u.full_name, u.username, u.hourly_rate,
               ROUND(s.duration_seconds / 3600, 2) AS duration_hours,
               ROUND(s.late_seconds / 60, 0) AS late_minutes,
               CAST(ROUND((s.duration_seconds / 3600) * u.hourly_rate, 0) AS SIGNED) AS salary_amount
        FROM shifts s
        JOIN users u ON u.id=s.user_id
        WHERE {where.sql}
        ORDER BY s.opened_at DESC
    """
    count_query = f"SELECT COUNT(*) AS cnt FROM shifts s JOIN users u ON u.id=s.user_id WHERE {where.sql}"
    return await paginate(base_query, count_query, where.params, page, page_size)


async def get_detail(shift_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        """
        SELECT s.*, u.full_name, u.username, u.hourly_rate,
               ROUND(s.duration_seconds / 3600, 2) AS duration_hours,
               ROUND(s.late_seconds / 60, 0) AS late_minutes,
               CAST(ROUND((s.duration_seconds / 3600) * u.hourly_rate, 0) AS SIGNED) AS salary_amount,
               p.start_at AS period_start_at,
               p.end_at AS period_end_at,
               p.is_closed AS period_is_closed
        FROM shifts s
        JOIN users u ON u.id = s.user_id
        JOIN payroll_periods p ON p.id = s.payroll_period_id
        WHERE s.id = %s
        LIMIT 1
        """,
        (shift_id,),
    )


async def list_for_period_with_salary(period_id: int, hourly_rate: float) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT id, opened_at, closed_at,
               ROUND(duration_seconds/3600, 2) AS duration_hours,
               ROUND(late_seconds/60, 0) AS late_minutes,
               CAST(ROUND(duration_seconds/3600 * %s, 0) AS SIGNED) AS salary_amount
        FROM shifts
        WHERE payroll_period_id=%s
        ORDER BY opened_at ASC
        """,
        (hourly_rate, period_id),
    )


async def update_from_web(
    shift_id: int,
    *,
    opened_at: datetime,
    closed_at: datetime | None,
    duration_seconds: int,
    late_seconds: int,
    payroll_period_id: int,
    is_scheduled: bool,
) -> None:
    await execute(
        """
        UPDATE shifts
        SET opened_at=%s,
            closed_at=%s,
            duration_seconds=%s,
            late_seconds=%s,
            payroll_period_id=%s,
            is_scheduled=%s,
            updated_at=NOW()
        WHERE id=%s
        """,
        (opened_at, closed_at, duration_seconds, late_seconds, payroll_period_id, 1 if is_scheduled else 0, shift_id),
    )
