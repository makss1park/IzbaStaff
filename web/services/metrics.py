from __future__ import annotations

from core.repositories import dashboard as dashboard_repo


async def dashboard_metrics() -> dict:
    summary = await dashboard_repo.summary_counts()
    salary_chart = await dashboard_repo.net_salary_by_month()
    return {
        "summary": summary,
        "salary_chart": list(reversed(salary_chart)),  # на графике — от старых месяцев к новым
        "top_staff": await dashboard_repo.top_staff(),
        "lateness": await dashboard_repo.lateness_by_day(),
    }
