from __future__ import annotations

from bot.database import fetch_all, fetch_one


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


async def get_employee_options() -> list[dict]:
    rows = await fetch_all(
        """
        SELECT id, full_name, username, role, is_active
        FROM users
        ORDER BY is_active DESC, COALESCE(NULLIF(full_name, ''), NULLIF(username, ''), CONCAT('ID ', id)) ASC, id ASC
        """
    )
    options = []
    seen_ids: set[int] = set()
    for row in rows:
        user_id = int(row['id'])
        if user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        name = (row.get('full_name') or '').strip()
        username = (row.get('username') or '').strip()
        if name and username:
            label = f"{name} (@{username})"
        else:
            label = name or (f"@{username}" if username else f"ID {user_id}")
        options.append({'id': user_id, 'label': label})
    return options


async def get_selected_employee(employee_id: int | str | None) -> dict | None:
    normalized_id = parse_employee_id(employee_id)
    if not normalized_id:
        return None
    row = await fetch_one('SELECT id, full_name, username FROM users WHERE id=%s LIMIT 1', (normalized_id,))
    if not row:
        return None
    name = (row.get('full_name') or '').strip()
    username = (row.get('username') or '').strip()
    if name and username:
        label = f"{name} (@{username})"
    else:
        label = name or (f"@{username}" if username else f"ID {row['id']}")
    row['label'] = label
    return row
