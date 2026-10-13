from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one
from core.repositories._sql import Where, in_placeholders, like, paginate

# Колонки, которые разрешено менять через update_by_id / update_by_tg_id.
_UPDATABLE_COLUMNS = {"username", "full_name", "phone", "hourly_rate", "role", "is_active"}


def _set_clause(changes: dict[str, Any]) -> tuple[str, list[Any]]:
    unknown = set(changes) - _UPDATABLE_COLUMNS
    if unknown:
        raise ValueError(f"Unsupported user columns: {sorted(unknown)}")
    return ", ".join(f"{column}=%s" for column in changes), list(changes.values())


# ---------- чтение ----------

async def get_by_id(user_id: int) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))


async def get_by_tg_id(tg_id: int) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM users WHERE tg_id=%s", (tg_id,))


async def get_hourly_rate(user_id: int) -> float:
    row = await fetch_one("SELECT hourly_rate FROM users WHERE id=%s", (user_id,)) or {"hourly_rate": 0}
    return float(row["hourly_rate"])


async def has_late_excuse_token(user_id: int) -> bool:
    row = await fetch_one("SELECT late_excuse_token FROM users WHERE id=%s LIMIT 1", (user_id,))
    return bool(row and row.get("late_excuse_token"))


async def list_active() -> list[dict[str, Any]]:
    return await fetch_all(
        "SELECT * FROM users WHERE is_active=1 ORDER BY COALESCE(full_name, username, tg_id)"
    )


async def list_active_admins() -> list[dict[str, Any]]:
    return await fetch_all(
        "SELECT tg_id, full_name, username FROM users WHERE role='admin' AND is_active=1"
    )


async def list_active_admin_ids() -> list[int]:
    rows = await fetch_all("SELECT id FROM users WHERE role='admin' AND is_active=1")
    return [int(row["id"]) for row in rows if row.get("id") is not None]


async def list_active_tg_ids(user_ids: list[int]) -> list[dict[str, Any]]:
    """tg_id активных пользователей из списка (получатели уведомлений о новых отчётах)."""
    if not user_ids:
        return []
    return await fetch_all(
        f"SELECT tg_id FROM users WHERE is_active=1 AND id IN ({in_placeholders(user_ids)})",
        tuple(user_ids),
    )


async def list_shift_event_tg_ids(user_ids: list[int]) -> list[dict[str, Any]]:
    """tg_id получателей уведомлений об открытии/закрытии смен."""
    if not user_ids:
        return []
    return await fetch_all(
        "SELECT tg_id FROM users WHERE is_active=1 AND role IN ('admin','employee','manager') "
        f"AND tg_id IS NOT NULL AND id IN ({in_placeholders(user_ids)})",
        tuple(user_ids),
    )


# ---------- запись ----------

async def create(tg_id: int, username: str | None, full_name: str | None, role: str, now: datetime) -> None:
    await execute(
        """
        INSERT INTO users (tg_id, username, full_name, role, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tg_id, username, full_name, role, now, now),
    )


async def update_by_tg_id(tg_id: int, changes: dict[str, Any], now: datetime) -> None:
    if not changes:
        return
    set_sql, args = _set_clause(changes)
    await execute(f"UPDATE users SET {set_sql}, updated_at=%s WHERE tg_id=%s", tuple([*args, now, tg_id]))


async def update_by_id(user_id: int, changes: dict[str, Any], now: datetime) -> None:
    if not changes:
        return
    set_sql, args = _set_clause(changes)
    await execute(f"UPDATE users SET {set_sql}, updated_at=%s WHERE id=%s", tuple([*args, now, user_id]))


async def update_rate(user_ids: list[int], rate: float, now: datetime) -> None:
    if not user_ids:
        return
    await execute(
        f"UPDATE users SET hourly_rate=%s, updated_at=%s WHERE id IN ({in_placeholders(user_ids)})",
        tuple([rate, now, *user_ids]),
    )


async def set_late_excuse_token(user_id: int, value: bool, now: datetime) -> None:
    await execute(
        "UPDATE users SET late_excuse_token=%s, updated_at=%s WHERE id=%s",
        (1 if value else 0, now, user_id),
    )


async def soft_delete(user_ids: list[int], now: datetime) -> None:
    """Деактивирует сотрудников/менеджеров, не трогая историю."""
    if not user_ids:
        return
    await execute(
        f"""
        UPDATE users
        SET is_active=0, updated_at=%s
        WHERE role IN ('employee','manager') AND id IN ({in_placeholders(user_ids)})
        """,
        tuple([now, *user_ids]),
    )


# ---------- веб-админка ----------

async def list_for_select() -> list[dict[str, Any]]:
    """Все пользователи для выпадающего списка: сначала активные, затем по имени."""
    return await fetch_all(
        """
        SELECT id, full_name, username, role, is_active
        FROM users
        ORDER BY is_active DESC, COALESCE(NULLIF(full_name, ''), NULLIF(username, ''), CONCAT('ID ', id)) ASC, id ASC
        """
    )


async def get_brief(user_id: int) -> dict[str, Any] | None:
    return await fetch_one("SELECT id, full_name, username FROM users WHERE id=%s LIMIT 1", (user_id,))


async def get_with_rate_int(user_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT *, CAST(ROUND(hourly_rate, 0) AS SIGNED) AS hourly_rate_int FROM users WHERE id=%s LIMIT 1",
        (user_id,),
    )


async def search_page(*, query: str = "", status: str = "all", page: int, page_size: int) -> dict[str, Any]:
    where = Where()
    if query.strip():
        pattern = like(query)
        where.add("(u.full_name LIKE %s OR u.username LIKE %s OR u.phone LIKE %s)", pattern, pattern, pattern)
    if status == "active":
        where.add("u.is_active=1")
    elif status == "inactive":
        where.add("u.is_active=0")

    base_query = f"""
        SELECT u.*, s.weekdays_json, s.start_time, s.end_time,
               (SELECT COUNT(*) FROM shifts sh WHERE sh.user_id = u.id AND sh.closed_at IS NULL) AS active_shift_count
        FROM users u
        LEFT JOIN user_schedules s ON s.user_id = u.id AND s.is_active=1
        WHERE {where.sql}
        ORDER BY u.is_active DESC, COALESCE(u.full_name, '') ASC, u.id DESC
    """
    count_query = f"SELECT COUNT(*) AS cnt FROM users u WHERE {where.sql}"
    return await paginate(base_query, count_query, where.params, page, page_size)


async def update_profile_from_web(
    user_id: int,
    *,
    full_name: str,
    phone: str,
    hourly_rate: float,
    is_active: bool,
) -> None:
    await execute(
        "UPDATE users SET full_name=%s, phone=%s, hourly_rate=%s, is_active=%s, updated_at=NOW() WHERE id=%s",
        (full_name, phone, hourly_rate, 1 if is_active else 0, user_id),
    )
