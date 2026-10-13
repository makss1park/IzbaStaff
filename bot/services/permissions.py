"""Права, которые админ выдаёт отдельным сотрудникам в «Настройки → Выдать доступ»."""
from __future__ import annotations

from typing import Any

from bot.services.settings_service import get_fine_grantee_ids


async def can_assign_fines(user: dict[str, Any] | None) -> bool:
    """Админ может всегда; сотрудник или менеджер — если ему выдан доступ."""
    if not user or not user.get("is_active", 1):
        return False
    if user.get("role") == "admin":
        return True
    return int(user["id"]) in await get_fine_grantee_ids()


def fine_targets(users: list[dict[str, Any]], actor: dict[str, Any]) -> list[dict[str, Any]]:
    """Кого можно оштрафовать: админ — любого из списка; сотрудник с доступом — сотрудников
    и менеджеров, кроме себя."""
    if actor.get("role") == "admin":
        return users
    return [u for u in users if u.get("role") in {"employee", "manager"} and u["id"] != actor["id"]]
