from __future__ import annotations

import json
from typing import Any

from bot import texts
from bot.config import settings
from bot.database import execute, fetch_all, fetch_one
from bot.utils.dates import now_local


def _parse_weekdays(value: str | None) -> list[int]:
    if not value:
        return []

    raw = value.strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            result: list[int] = []
            for item in parsed:
                try:
                    result.append(int(item))
                except Exception:
                    continue
            return result
    except Exception:
        pass

    result: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except Exception:
            continue
    return result


def _weekday_name(day: int) -> str:
    mapping = {
        1: texts.WEEKDAYS_SHORT_TITLE[1],
        2: texts.WEEKDAYS_SHORT_TITLE[2],
        3: texts.WEEKDAYS_SHORT_TITLE[3],
        4: texts.WEEKDAYS_SHORT_TITLE[4],
        5: texts.WEEKDAYS_SHORT_TITLE[5],
        6: texts.WEEKDAYS_SHORT_TITLE[6],
        7: texts.WEEKDAYS_SHORT_TITLE[7],
    }
    return mapping.get(day, str(day))


def _build_schedule_display(schedule: dict[str, Any] | None) -> str:
    if not schedule:
        return texts.SCHEDULE_NOT_SET

    weekdays = _parse_weekdays(schedule.get("weekdays_json"))
    if weekdays:
        days_display = ", ".join(_weekday_name(day) for day in weekdays)
    else:
        days_display = texts.SCHEDULE_DAYS_NOT_SET

    start_time = schedule.get("start_time") or texts.DASH
    end_time = schedule.get("end_time") or texts.DASH

    return f"{days_display}; {start_time}-{end_time}"


async def _get_user_core_by_tg_id(tg_id: int) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM users WHERE tg_id=%s", (tg_id,))


async def get_user_by_tg_id(tg_id: int) -> dict[str, Any] | None:
    user = await _get_user_core_by_tg_id(tg_id)
    if not user:
        return None

    schedule = await fetch_one(
        "SELECT * FROM user_schedules WHERE user_id=%s AND is_active=1 ORDER BY id DESC LIMIT 1",
        (user["id"],),
    )
    user["schedule_display"] = _build_schedule_display(schedule)
    return user


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    user = await fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))
    if not user:
        return None

    schedule = await fetch_one(
        "SELECT * FROM user_schedules WHERE user_id=%s AND is_active=1 ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    user["schedule_display"] = _build_schedule_display(schedule)
    return user


async def ensure_user(tg_id: int, username: str | None, full_name: str | None) -> dict[str, Any]:
    existing = await _get_user_core_by_tg_id(tg_id)
    role = "admin" if tg_id in settings.admin_id_set else "employee"
    now = now_local().replace(tzinfo=None)

    if existing:
        update_fields: list[str] = []
        args: list[Any] = []

        if existing.get("username") != username:
            update_fields.append("username=%s")
            args.append(username)

        # Не перезаписываем вручную изменённое ФИО данными из Telegram.
        # Автообновление имени из Telegram допустимо только если ФИО в базе ещё пустое.
        if full_name and not existing.get("full_name"):
            update_fields.append("full_name=%s")
            args.append(full_name)

        # Не сбрасываем менеджера обратно в сотрудника при /start.
        # Автоматически повышаем до администратора только тех, кто указан в ADMIN_IDS.
        if tg_id in settings.admin_id_set and existing.get("role") != "admin":
            update_fields.append("role=%s")
            args.append("admin")

        if update_fields:
            update_fields.append("updated_at=%s")
            args.append(now)
            args.append(tg_id)

            await execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE tg_id=%s",
                tuple(args),
            )

            existing["updated_at"] = now
            if "username=%s" in update_fields:
                existing["username"] = username
            if "full_name=%s" in update_fields and full_name:
                existing["full_name"] = full_name
            if "role=%s" in update_fields:
                existing["role"] = role

        return existing

    await execute(
        """
        INSERT INTO users (tg_id, username, full_name, role, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tg_id, username, full_name, role, now, now),
    )

    user = await _get_user_core_by_tg_id(tg_id)
    assert user is not None
    return user


async def update_full_name(user_id: int, full_name: str) -> None:
    await execute(
        "UPDATE users SET full_name=%s, updated_at=%s WHERE id=%s",
        (full_name, now_local().replace(tzinfo=None), user_id),
    )


async def update_phone(user_id: int, phone: str) -> None:
    await execute(
        "UPDATE users SET phone=%s, updated_at=%s WHERE id=%s",
        (phone, now_local().replace(tzinfo=None), user_id),
    )


async def update_rate(user_ids: list[int], rate: float) -> None:
    if not user_ids:
        return
    placeholders = ",".join(["%s"] * len(user_ids))
    await execute(
        f"UPDATE users SET hourly_rate=%s, updated_at=%s WHERE id IN ({placeholders})",
        tuple([rate, now_local().replace(tzinfo=None), *user_ids]),
    )


async def update_user(user_id: int, changes: dict[str, Any]) -> None:
    if not changes:
        return

    allowed_fields = {
        "full_name": "full_name",
        "phone": "phone",
        "hourly_rate": "hourly_rate",
        "role": "role",
    }

    update_fields: list[str] = []
    args: list[Any] = []
    for key, value in changes.items():
        column = allowed_fields.get(key)
        if not column:
            continue
        update_fields.append(f"{column}=%s")
        args.append(value)

    if not update_fields:
        return

    update_fields.append("updated_at=%s")
    args.append(now_local().replace(tzinfo=None))
    args.append(user_id)

    await execute(
        f"UPDATE users SET {', '.join(update_fields)} WHERE id=%s",
        tuple(args),
    )


async def delete_users(user_ids: list[int]) -> None:
    """Soft-delete employees/managers without removing historical data."""
    if not user_ids:
        return

    placeholders = ",".join(["%s"] * len(user_ids))
    await execute(
        f"""
        UPDATE users
        SET is_active=0, updated_at=%s
        WHERE role IN ('employee','manager') AND id IN ({placeholders})
        """,
        tuple([now_local().replace(tzinfo=None), *user_ids]),
    )


async def list_all_users() -> list[dict[str, Any]]:
    users = await fetch_all(
        "SELECT * FROM users WHERE is_active=1 ORDER BY COALESCE(full_name, username, tg_id)"
    )

    if not users:
        return users

    user_ids = [user["id"] for user in users]
    placeholders = ",".join(["%s"] * len(user_ids))
    schedules = await fetch_all(
        f"""
        SELECT *
        FROM user_schedules
        WHERE is_active=1 AND user_id IN ({placeholders})
        ORDER BY id DESC
        """,
        tuple(user_ids),
    )

    schedules_map: dict[int, dict[str, Any]] = {}
    for schedule in schedules:
        if schedule["user_id"] not in schedules_map:
            schedules_map[schedule["user_id"]] = schedule

    for user in users:
        user["schedule_display"] = _build_schedule_display(schedules_map.get(user["id"]))

    return users


async def decorate_users_with_schedule(
    users: list[dict[str, Any]],
    schedules: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    for user in users:
        schedule = schedules.get(user["id"])
        user["schedule_display"] = _build_schedule_display(schedule)
    return users


async def get_admin_users():
    return await fetch_all(
        "SELECT tg_id, full_name, username FROM users WHERE role='admin' AND is_active=1"
    )