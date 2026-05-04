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
