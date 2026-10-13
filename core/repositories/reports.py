from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one
from core.repositories._sql import Where, like, paginate


async def create(
    *,
    user_id: int,
    description: str,
    photo_file_id: str,
    photo_public_url: str | None,
    photo_local_path: str | None,
    now: datetime,
) -> int:
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


async def list_recent_with_users(days: int) -> list[dict[str, Any]]:
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


async def get_with_user(report_id: int) -> dict[str, Any] | None:
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


async def list_for_user(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
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


# ---------- веб-админка ----------

async def search_page(
    *,
    employee_id: int | None = None,
    employee_query: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int,
    page_size: int,
) -> dict[str, Any]:
    where = Where()
    if employee_id:
        where.add("r.user_id = %s", employee_id)
    elif employee_query.strip():
        pattern = like(employee_query)
        where.add("(u.full_name LIKE %s OR u.username LIKE %s)", pattern, pattern)
    if date_from.strip():
        where.add("DATE(r.created_at) >= %s", date_from.strip())
    if date_to.strip():
        where.add("DATE(r.created_at) <= %s", date_to.strip())

    base_query = (
        "SELECT r.*, u.full_name, u.username FROM reports r JOIN users u ON u.id=r.user_id "
        f"WHERE {where.sql} ORDER BY r.created_at DESC"
    )
    count_query = f"SELECT COUNT(*) AS cnt FROM reports r JOIN users u ON u.id=r.user_id WHERE {where.sql}"
    return await paginate(base_query, count_query, where.params, page, page_size)


# ---------- миграция фото отчётов ----------

async def list_missing_local_copy() -> list[dict[str, Any]]:
    """Отчёты с фото в Telegram, у которых ещё нет локального файла или публичной ссылки."""
    return await fetch_all(
        """
        SELECT id, photo_file_id, photo_public_url, photo_local_path
        FROM reports
        WHERE photo_file_id IS NOT NULL
          AND photo_file_id <> ''
          AND (photo_public_url IS NULL OR photo_public_url = '' OR photo_local_path IS NULL OR photo_local_path = '')
        ORDER BY id ASC
        """
    )


async def list_with_local_path() -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT id, photo_local_path, photo_public_url
        FROM reports
        WHERE photo_local_path IS NOT NULL AND photo_local_path <> ''
        ORDER BY id ASC
        """
    )


async def set_photo_location(report_id: int, local_path: str, public_url: str) -> None:
    await execute(
        "UPDATE reports SET photo_local_path=%s, photo_public_url=%s WHERE id=%s",
        (local_path, public_url, report_id),
    )


async def set_public_url(report_id: int, public_url: str) -> None:
    await execute("UPDATE reports SET photo_public_url=%s WHERE id=%s", (public_url, report_id))
