from __future__ import annotations

from typing import Any

from core.clock import now_naive
from core.repositories import reports as reports_repo


async def create_report(
    user_id: int,
    description: str,
    photo_file_id: str,
    photo_public_url: str | None = None,
    photo_local_path: str | None = None,
) -> int:
    return await reports_repo.create(
        user_id=user_id,
        description=description,
        photo_file_id=photo_file_id,
        photo_public_url=photo_public_url,
        photo_local_path=photo_local_path,
        now=now_naive(),
    )


async def get_recent_reports(days: int) -> list[dict[str, Any]]:
    return await reports_repo.list_recent_with_users(days)


async def get_report_by_id(report_id: int) -> dict[str, Any] | None:
    return await reports_repo.get_with_user(report_id)


async def get_reports_by_user(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await reports_repo.list_for_user(user_id, limit)
