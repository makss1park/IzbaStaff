from __future__ import annotations

from bot.config import settings
from bot.database import execute, fetch_one
from bot.utils.dates import now_local


async def get_latest_reports_days() -> int:
    row = await fetch_one("SELECT `value` FROM bot_settings WHERE `key`='latest_reports_days'")
    if not row:
        return settings.default_reports_days
    return int(row["value"])


async def set_latest_reports_days(days: int) -> None:
    await execute(
        """
        INSERT INTO bot_settings (`key`, `value`, updated_at)
        VALUES ('latest_reports_days', %s, %s)
        ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)
        """,
        (str(days), now_local().replace(tzinfo=None)),
    )


async def get_new_report_recipient_ids() -> list[int]:
    row = await fetch_one("SELECT `value` FROM bot_settings WHERE `key`='new_report_recipient_ids'")
    if not row or not row.get("value"):
        return []
    result: list[int] = []
    for item in str(row["value"]).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except Exception:
            continue
    return sorted(set(result))


async def set_new_report_recipient_ids(user_ids: list[int]) -> None:
    normalized = ",".join(str(int(user_id)) for user_id in sorted(set(user_ids)))
    await execute(
        """
        INSERT INTO bot_settings (`key`, `value`, updated_at)
        VALUES ('new_report_recipient_ids', %s, %s)
        ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)
        """,
        (normalized, now_local().replace(tzinfo=None)),
    )



async def get_shift_event_recipient_ids() -> list[int]:
    row = await fetch_one("SELECT `value` FROM bot_settings WHERE `key`='shift_event_recipient_ids'")
    if not row or not row.get("value"):
        return []
    result: list[int] = []
    for item in str(row["value"]).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except Exception:
            continue
    return sorted(set(result))


async def set_shift_event_recipient_ids(user_ids: list[int]) -> None:
    normalized = ",".join(str(int(user_id)) for user_id in sorted(set(user_ids)))
    await execute(
        """
        INSERT INTO bot_settings (`key`, `value`, updated_at)
        VALUES ('shift_event_recipient_ids', %s, %s)
        ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)
        """,
        (normalized, now_local().replace(tzinfo=None)),
    )
