from __future__ import annotations

from core.repositories import users as users_repo


def parse_employee_id(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def employee_label(row: dict) -> str:
    """«ФИО (@username)», либо что есть, либо «ID n»."""
    name = (row.get("full_name") or "").strip()
    username = (row.get("username") or "").strip()
    if name and username:
        return f"{name} (@{username})"
    return name or (f"@{username}" if username else f"ID {row['id']}")


async def get_employee_options() -> list[dict]:
    options = []
    seen_ids: set[int] = set()
    for row in await users_repo.list_for_select():
        user_id = int(row["id"])
        if user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        options.append({"id": user_id, "label": employee_label(row)})
    return options


async def get_selected_employee(employee_id: int | str | None) -> dict | None:
    normalized_id = parse_employee_id(employee_id)
    if not normalized_id:
        return None
    row = await users_repo.get_brief(normalized_id)
    if not row:
        return None
    row["label"] = employee_label(row)
    return row


async def employee_filter_context(employee_id: int | None) -> dict:
    """Данные для фильтра «Сотрудник» на страницах смен, отчётов и зарплаты."""
    return {
        "employee_options": await get_employee_options(),
        "selected_employee": await get_selected_employee(employee_id),
    }
