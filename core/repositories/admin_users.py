"""Учётные записи веб-админки (admin_users)."""
from __future__ import annotations

from typing import Any

from core.db import execute, fetch_one
from core.repositories._sql import paginate


async def get_by_username(username: str) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT id, username, role, is_active, password_hash FROM admin_users WHERE username=%s LIMIT 1",
        (username,),
    )


async def set_password_hash(admin_id: int, password_hash: str) -> None:
    await execute(
        "UPDATE admin_users SET password_hash=%s, updated_at=NOW() WHERE id=%s",
        (password_hash, admin_id),
    )


async def list_page(page: int, page_size: int) -> dict[str, Any]:
    return await paginate(
        "SELECT id, username, role, is_active, created_at, updated_at FROM admin_users ORDER BY username ASC",
        "SELECT COUNT(*) AS cnt FROM admin_users",
        (),
        page,
        page_size,
    )


async def create(username: str, password_hash: str, role: str) -> None:
    await execute(
        "INSERT INTO admin_users (username, password_hash, role, is_active, created_at, updated_at) "
        "VALUES (%s, %s, %s, 1, NOW(), NOW())",
        (username, password_hash, role),
    )


async def toggle_active(admin_id: int) -> None:
    await execute(
        "UPDATE admin_users SET is_active = IF(is_active=1,0,1), updated_at=NOW() WHERE id=%s",
        (admin_id,),
    )
