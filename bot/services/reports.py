from __future__ import annotations

from typing import Any

from bot.database import execute, fetch_all, fetch_one
from bot.utils.dates import now_local


async def create_report(
    user_id: int,
    description: str,
    photo_file_id: str,
    photo_public_url: str | None = None,
    photo_local_path: str | None = None,
) -> int:
    now = now_local().replace(tzinfo=None)
    report_id = await execute(
        """
        INSERT INTO reports (
            user_id, description, photo_file_id, photo_public_url, photo_local_path, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user_id, description, photo_file_id, photo_public_url, photo_local_path, now),
    )
    return int(report_id)


async def get_recent_reports(days: int) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT r.*, u.full_name, u.username
        FROM reports r
        JOIN users u ON u.id = r.user_id
        WHERE r.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY r.created_at DESC
        """,
        (days,),
    )


async def get_report_by_id(report_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        """
        SELECT r.*, u.full_name, u.username
        FROM reports r
        JOIN users u ON u.id = r.user_id
        WHERE r.id = %s
        LIMIT 1
        """,
        (report_id,),
    )


async def get_reports_by_user(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT *
        FROM reports
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (user_id, limit),
    )