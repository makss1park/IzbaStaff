from __future__ import annotations

from bot.database import execute
from bot.services.payroll import ensure_open_period
from bot.utils.dates import now_local


async def create_fine(user_id: int, amount: float, reason: str, created_by: int) -> None:
    period = await ensure_open_period(user_id)
    await execute(
        "INSERT INTO fines (user_id, payroll_period_id, amount, reason, created_at, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, period["id"], amount, reason, now_local().replace(tzinfo=None), created_by),
    )
