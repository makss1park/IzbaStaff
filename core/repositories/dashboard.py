"""Агрегаты для дашборда веб-админки."""
from __future__ import annotations

from typing import Any

from core.db import fetch_all, fetch_one


async def summary_counts() -> dict[str, Any]:
    return await fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM users WHERE is_active=1) AS active_users,
            (SELECT COUNT(*) FROM shifts WHERE closed_at IS NULL) AS active_shifts,
            (SELECT COUNT(*) FROM reports) AS reports_total
        """
    ) or {}


async def net_salary_by_month(limit: int = 12) -> list[dict[str, Any]]:
    """Начислено минус штрафы по месяцам начала периода, от новых к старым."""
    return await fetch_all(
        """
        SELECT DATE_FORMAT(p.start_at, '%%Y-%%m') AS label,
               ROUND(SUM(COALESCE(agg.salary_amount, 0) - COALESCE(agg.fines_amount, 0)), 2) AS value
        FROM payroll_periods p
        LEFT JOIN (
            SELECT pp.id AS payroll_period_id,
                   COALESCE(SUM(s.duration_seconds / 3600 * u.hourly_rate), 0) AS salary_amount,
                   COALESCE((SELECT SUM(f.amount) FROM fines f WHERE f.payroll_period_id = pp.id), 0) AS fines_amount
            FROM payroll_periods pp
            LEFT JOIN shifts s ON s.payroll_period_id = pp.id AND s.closed_at IS NOT NULL
            LEFT JOIN users u ON u.id = pp.user_id
            GROUP BY pp.id
        ) agg ON agg.payroll_period_id = p.id
        GROUP BY DATE_FORMAT(p.start_at, '%%Y-%%m')
        ORDER BY label DESC
        LIMIT %s
        """,
        (limit,),
    )


async def top_staff(limit: int = 8) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT u.full_name,
               ROUND(SUM(s.duration_seconds) / 3600, 2) AS hours_worked,
               ROUND(SUM(s.duration_seconds) / 3600 * MAX(u.hourly_rate), 2) AS salary_amount
        FROM users u
        LEFT JOIN shifts s ON s.user_id = u.id AND s.closed_at IS NOT NULL
        GROUP BY u.id, u.full_name
        ORDER BY salary_amount DESC, hours_worked DESC
        LIMIT %s
        """,
        (limit,),
    )


async def lateness_by_day(days: int = 14) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT DATE_FORMAT(opened_at, '%%d.%%m') AS label,
               ROUND(SUM(late_seconds) / 60, 0) AS value
        FROM shifts
        WHERE opened_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY DATE_FORMAT(opened_at, '%%Y-%%m-%%d'), DATE_FORMAT(opened_at, '%%d.%%m')
        ORDER BY MIN(opened_at)
        """,
        (days,),
    )
