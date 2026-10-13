"""Таблица bot_settings: простое хранилище «ключ → значение»."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one

LATEST_REPORTS_DAYS = "latest_reports_days"
NEW_REPORT_RECIPIENT_IDS = "new_report_recipient_ids"
SHIFT_EVENT_RECIPIENT_IDS = "shift_event_recipient_ids"
FINE_GRANTEE_IDS = "fine_grantee_ids"  # сотрудники, которым админ разрешил назначать штрафы


async def get_value(key: str) -> str | None:
    row = await fetch_one("SELECT `value` FROM bot_settings WHERE `key`=%s", (key,))
    if not row:
        return None
    return row.get("value")


async def set_value(key: str, value: str, now: datetime | None = None) -> None:
    """Создаёт или обновляет настройку. Без ``now`` время берётся из MySQL (NOW())."""
    if now is None:
        await execute(
            "INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) "
            "ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)",
            (key, value),
        )
        return
    await execute(
        """
        INSERT INTO bot_settings (`key`, `value`, updated_at)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)
        """,
        (key, value, now),
    )


async def list_all() -> list[dict[str, Any]]:
    return await fetch_all("SELECT * FROM bot_settings ORDER BY `key` ASC")
