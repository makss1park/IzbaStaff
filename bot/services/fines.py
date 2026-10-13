from __future__ import annotations

from bot.services.payroll import ensure_open_period
from core.clock import now_naive
from core.repositories import fines as fines_repo


async def create_fine(user_id: int, amount: float, reason: str, created_by: int) -> None:
    """Штраф всегда привязывается к текущему открытому периоду сотрудника."""
    period = await ensure_open_period(user_id)
    await fines_repo.create(
        user_id=user_id,
        payroll_period_id=period["id"],
        amount=amount,
        reason=reason,
        created_by=created_by,
        now=now_naive(),
    )
