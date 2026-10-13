from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one
from core.repositories._sql import Where, like, paginate


async def get_open_period(user_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM payroll_periods WHERE user_id=%s AND is_closed=0 ORDER BY id DESC LIMIT 1",
        (user_id,),
    )


async def create_period(user_id: int, start_at: datetime, now: datetime) -> None:
    await execute(
        "INSERT INTO payroll_periods (user_id, start_at, is_closed, created_at, updated_at) VALUES (%s, %s, 0, %s, %s)",
        (user_id, start_at, now, now),
    )


async def close_period(period_id: int, end_at: datetime, now: datetime) -> None:
    await execute(
        "UPDATE payroll_periods SET is_closed=1, end_at=%s, updated_at=%s WHERE id=%s",
        (end_at, now, period_id),
    )


# ---------- веб-админка ----------

# Агрегаты смен по периоду. Используются и в списке, и в итоговой сводке.
_SHIFT_AGG_SQL = """
    SELECT s.payroll_period_id,
           COUNT(*) AS shift_count,
           SUM(CASE WHEN s.closed_at IS NOT NULL THEN s.duration_seconds ELSE 0 END) / 3600 AS hours_worked,
           SUM(CASE WHEN s.closed_at IS NOT NULL THEN s.duration_seconds ELSE 0 END) / 3600 * MAX(u.hourly_rate) AS salary_amount,
           SUM(CASE WHEN s.late_seconds > 0 THEN 1 ELSE 0 END) AS late_count,
           SUM(s.late_seconds) / 60 AS late_minutes
    FROM shifts s
    JOIN users u ON u.id = s.user_id
    GROUP BY s.payroll_period_id
"""

_FINES_AGG_SQL = """
    SELECT payroll_period_id, SUM(amount) AS fines_amount
    FROM fines GROUP BY payroll_period_id
"""

# Последний закрытый период сотрудника, предшествующий его текущему открытому.
_PREVIOUS_CLOSED_SQL = """
    p.is_closed = 1
    AND p.start_at = (
        SELECT MAX(pc.start_at)
        FROM payroll_periods pc
        WHERE pc.user_id = p.user_id
          AND pc.is_closed = 1
          AND pc.start_at < COALESCE(
              (
                  SELECT MIN(po.start_at)
                  FROM payroll_periods po
                  WHERE po.user_id = p.user_id AND po.is_closed = 0
              ),
              '2999-12-31 23:59:59'
          )
    )
"""


def _periods_where(
    *,
    employee_id: int | None,
    employee_query: str,
    date_from: str,
    date_to: str,
    status: str,
) -> Where:
    where = Where()
    if employee_id:
        where.add("p.user_id = %s", employee_id)
    elif employee_query.strip():
        pattern = like(employee_query)
        where.add("(u.full_name LIKE %s OR u.username LIKE %s)", pattern, pattern)
    if date_from.strip():
        where.add("DATE(p.start_at) >= %s", date_from.strip())
    if date_to.strip():
        where.add("DATE(COALESCE(p.end_at, p.start_at)) <= %s", date_to.strip())
    if status == "open":
        where.add("p.is_closed=0")
    elif status == "closed":
        where.add("p.is_closed=1")
    elif status == "previous_closed":
        where.add(_PREVIOUS_CLOSED_SQL)
    return where


async def search_page_with_summary(
    *,
    employee_id: int | None = None,
    employee_query: str = "",
    date_from: str = "",
    date_to: str = "",
    status: str = "all",
    page: int,
    page_size: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Страница периодов с начислениями и сводка по всем периодам, попавшим под фильтр."""
    where = _periods_where(
        employee_id=employee_id,
        employee_query=employee_query,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )

    base_query = f"""
        SELECT p.*, u.full_name, u.username, u.hourly_rate,
               ROUND(COALESCE(sh.hours_worked, 0), 2) AS hours_worked,
               CAST(ROUND(COALESCE(sh.salary_amount, 0), 0) AS SIGNED) AS salary_amount,
               CAST(ROUND(COALESCE(fi.fines_amount, 0), 0) AS SIGNED) AS fines_amount,
               CAST(ROUND(COALESCE(sh.salary_amount, 0) - COALESCE(fi.fines_amount, 0), 0) AS SIGNED) AS net_amount,
               COALESCE(sh.shift_count, 0) AS shift_count,
               COALESCE(sh.late_count, 0) AS late_count,
               COALESCE(sh.late_minutes, 0) AS late_minutes
        FROM payroll_periods p
        JOIN users u ON u.id = p.user_id
        LEFT JOIN ({_SHIFT_AGG_SQL}) sh ON sh.payroll_period_id = p.id
        LEFT JOIN ({_FINES_AGG_SQL}) fi ON fi.payroll_period_id = p.id
        WHERE {where.sql}
        ORDER BY p.start_at DESC, p.id DESC
    """
    count_query = f"SELECT COUNT(*) AS cnt FROM payroll_periods p JOIN users u ON u.id=p.user_id WHERE {where.sql}"

    summary_query = f"""
        SELECT
            COALESCE(SUM(periods.shift_count), 0) AS total_shifts,
            ROUND(COALESCE(SUM(periods.hours_worked), 0), 2) AS total_hours,
            CAST(ROUND(COALESCE(SUM(periods.salary_amount), 0), 0) AS SIGNED) AS total_salary_amount,
            CAST(ROUND(COALESCE(SUM(periods.fines_amount), 0), 0) AS SIGNED) AS total_fines_amount,
            CAST(ROUND(COALESCE(SUM(periods.salary_amount) - SUM(periods.fines_amount), 0), 0) AS SIGNED) AS total_net_amount
        FROM (
            SELECT p.id,
                   COALESCE(sh.shift_count, 0) AS shift_count,
                   COALESCE(sh.hours_worked, 0) AS hours_worked,
                   COALESCE(sh.salary_amount, 0) AS salary_amount,
                   COALESCE(fi.fines_amount, 0) AS fines_amount
            FROM payroll_periods p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN ({_SHIFT_AGG_SQL}) sh ON sh.payroll_period_id = p.id
            LEFT JOIN ({_FINES_AGG_SQL}) fi ON fi.payroll_period_id = p.id
            WHERE {where.sql}
        ) periods
    """

    data = await paginate(base_query, count_query, where.params, page, page_size)
    summary = await fetch_one(summary_query, where.params) or {}
    return data, summary


async def get_with_user(period_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT p.*, u.full_name, u.username, u.hourly_rate "
        "FROM payroll_periods p JOIN users u ON u.id=p.user_id WHERE p.id=%s LIMIT 1",
        (period_id,),
    )


async def list_recent_for_user(user_id: int, hourly_rate: float, limit: int = 20) -> list[dict[str, Any]]:
    """Последние периоды сотрудника с часами, начислениями и штрафами (карточка сотрудника)."""
    return await fetch_all(
        """
        SELECT p.*,
               ROUND(COALESCE((SELECT SUM(duration_seconds) FROM shifts WHERE payroll_period_id=p.id AND closed_at IS NOT NULL), 0)/3600, 2) AS hours_worked,
               CAST(ROUND(COALESCE((SELECT SUM(duration_seconds) FROM shifts WHERE payroll_period_id=p.id AND closed_at IS NOT NULL), 0)/3600 * %s, 0) AS SIGNED) AS salary_amount,
               CAST(ROUND(COALESCE((SELECT SUM(amount) FROM fines WHERE payroll_period_id=p.id), 0), 0) AS SIGNED) AS fines_amount
        FROM payroll_periods p
        WHERE p.user_id=%s
        ORDER BY p.start_at DESC
        LIMIT %s
        """,
        (hourly_rate, user_id, limit),
    )


async def update_from_web(
    period_id: int,
    *,
    start_at: datetime,
    end_at: datetime | None,
    is_closed: bool,
) -> None:
    await execute(
        """
        UPDATE payroll_periods
        SET start_at=%s,
            end_at=%s,
            is_closed=%s,
            updated_at=NOW()
        WHERE id=%s
        """,
        (start_at, end_at, 1 if is_closed else 0, period_id),
    )
