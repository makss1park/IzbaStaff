from __future__ import annotations

from bot.database import fetch_all, fetch_one


async def dashboard_metrics() -> dict:
    summary = await fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM users WHERE is_active=1) AS active_users,
            (SELECT COUNT(*) FROM shifts WHERE closed_at IS NULL) AS active_shifts,
            (SELECT COUNT(*) FROM reports) AS reports_total,
            (SELECT COUNT(*) FROM notifications WHERE is_active=1) AS active_notifications
        """
    ) or {}

    salary_chart = await fetch_all(
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
        LIMIT 12
        """
    )

    top_staff = await fetch_all(
        """
        SELECT u.full_name,
               ROUND(SUM(s.duration_seconds) / 3600, 2) AS hours_worked,
               ROUND(SUM(s.duration_seconds) / 3600 * MAX(u.hourly_rate), 2) AS salary_amount
        FROM users u
        LEFT JOIN shifts s ON s.user_id = u.id AND s.closed_at IS NOT NULL
        GROUP BY u.id, u.full_name
        ORDER BY salary_amount DESC, hours_worked DESC
        LIMIT 8
        """
    )

    lateness = await fetch_all(
        """
        SELECT DATE_FORMAT(opened_at, '%%d.%%m') AS label,
               ROUND(SUM(late_seconds) / 60, 0) AS value
        FROM shifts
        WHERE opened_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
        GROUP BY DATE_FORMAT(opened_at, '%%Y-%%m-%%d'), DATE_FORMAT(opened_at, '%%d.%%m')
        ORDER BY MIN(opened_at)
        """
    )

    return {
        'summary': summary,
        'salary_chart': list(reversed(salary_chart)),
        'top_staff': top_staff,
        'lateness': lateness,
    }
