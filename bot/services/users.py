from __future__ import annotations

import json
from typing import Any

from bot import texts
from bot.config import settings
from bot.services.schedules import get_schedules_map
from core.clock import now_naive
from core.repositories import schedules as schedules_repo
from core.repositories import users as users_repo

# Поля профиля, которые админ может менять через бота.
_EDITABLE_FIELDS = ("full_name", "phone", "hourly_rate", "role")


def parse_weekdays(value: str | None) -> list[int]:
    """Дни недели из JSON-списка ``[1, 2, 3]`` или строки ``1,2,3``; мусор пропускается."""
    if not value:
        return []

    raw = value.strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None

    items = parsed if isinstance(parsed, list) else [part.strip() for part in raw.split(",")]
    result: list[int] = []
    for item in items:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def build_schedule_display(schedule: dict[str, Any] | None) -> str:
    if not schedule:
        return texts.SCHEDULE_NOT_SET

    weekdays = parse_weekdays(schedule.get("weekdays_json"))
    if weekdays:
        days_display = ", ".join(texts.WEEKDAYS_SHORT_TITLE.get(day, str(day)) for day in weekdays)
    else:
        days_display = texts.SCHEDULE_DAYS_NOT_SET

    start_time = schedule.get("start_time") or texts.DASH
    end_time = schedule.get("end_time") or texts.DASH
    return f"{days_display}; {start_time}-{end_time}"


def display_name(user: dict[str, Any]) -> str:
    """Как показывать сотрудника в сообщениях бота: ФИО → username → tg_id."""
    return user.get("full_name") or user.get("username") or str(user.get("tg_id"))


async def _with_schedule(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    user["schedule_display"] = build_schedule_display(await schedules_repo.get_active(user["id"]))
    return user


async def get_user_by_tg_id(tg_id: int) -> dict[str, Any] | None:
    return await _with_schedule(await users_repo.get_by_tg_id(tg_id))


async def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    return await _with_schedule(await users_repo.get_by_id(user_id))


async def ensure_user(tg_id: int, username: str | None, full_name: str | None) -> dict[str, Any]:
    """Находит пользователя по tg_id или регистрирует нового; синхронизирует username и роль админа."""
    existing = await users_repo.get_by_tg_id(tg_id)
    is_configured_admin = tg_id in settings.admin_id_set
    now = now_naive()

    if not existing:
        role = "admin" if is_configured_admin else "employee"
        await users_repo.create(tg_id, username, full_name, role, now)
        user = await users_repo.get_by_tg_id(tg_id)
        assert user is not None
        return user

    changes: dict[str, Any] = {}
    if existing.get("username") != username:
        changes["username"] = username
    # Не перезаписываем вручную изменённое ФИО данными из Telegram:
    # автообновление допустимо, только если ФИО в базе ещё пустое.
    if full_name and not existing.get("full_name"):
        changes["full_name"] = full_name
    # Не сбрасываем менеджера обратно в сотрудника при /start.
    # Автоматически повышаем до администратора только тех, кто указан в ADMIN_IDS.
    if is_configured_admin and existing.get("role") != "admin":
        changes["role"] = "admin"

    if changes:
        await users_repo.update_by_tg_id(tg_id, changes, now)
        existing.update(changes)
        existing["updated_at"] = now

    return existing


async def update_full_name(user_id: int, full_name: str) -> None:
    await users_repo.update_by_id(user_id, {"full_name": full_name}, now_naive())


async def update_phone(user_id: int, phone: str) -> None:
    await users_repo.update_by_id(user_id, {"phone": phone}, now_naive())


async def update_rate(user_ids: list[int], rate: float) -> None:
    await users_repo.update_rate(user_ids, rate, now_naive())


async def update_user(user_id: int, changes: dict[str, Any]) -> None:
    allowed = {key: value for key, value in changes.items() if key in _EDITABLE_FIELDS}
    await users_repo.update_by_id(user_id, allowed, now_naive())


async def delete_users(user_ids: list[int]) -> None:
    """Мягкое удаление сотрудников/менеджеров без потери истории."""
    await users_repo.soft_delete(user_ids, now_naive())


async def list_all_users() -> list[dict[str, Any]]:
    users = await users_repo.list_active()
    if not users:
        return users
    schedules = await get_schedules_map([user["id"] for user in users])
    return await decorate_users_with_schedule(users, schedules)


async def decorate_users_with_schedule(
    users: list[dict[str, Any]],
    schedules: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    for user in users:
        user["schedule_display"] = build_schedule_display(schedules.get(user["id"]))
    return users


async def get_admin_users() -> list[dict[str, Any]]:
    return await users_repo.list_active_admins()
