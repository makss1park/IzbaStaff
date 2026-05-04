from __future__ import annotations

from pathlib import Path

from aiogram import Bot

from bot.database import execute, fetch_all
from bot.utils.report_storage import save_telegram_report_photo


async def backfill_report_public_urls(bot: Bot) -> int:
    reports = await fetch_all(
        """
        SELECT id, photo_file_id, photo_public_url, photo_local_path
        FROM reports
        WHERE photo_file_id IS NOT NULL
          AND photo_file_id <> ''
          AND (photo_public_url IS NULL OR photo_public_url = '' OR photo_local_path IS NULL OR photo_local_path = '')
        ORDER BY id ASC
        """
    )

    processed = 0
    for report in reports:
        local_path, public_url = await save_telegram_report_photo(
            bot,
            report['photo_file_id'],
            filename_prefix=f"report_{report['id']}",
        )
        await execute(
            "UPDATE reports SET photo_local_path=%s, photo_public_url=%s WHERE id=%s",
            (local_path, public_url, report['id']),
        )
        processed += 1
    return processed


async def normalize_report_urls() -> int:
    reports = await fetch_all(
        """
        SELECT id, photo_local_path, photo_public_url
        FROM reports
        WHERE photo_local_path IS NOT NULL AND photo_local_path <> ''
        ORDER BY id ASC
        """
    )
    from bot.utils.report_storage import build_public_report_url

    updated = 0
    for report in reports:
        file_name = Path(report['photo_local_path']).name
        expected_url = build_public_report_url(file_name)
        if report.get('photo_public_url') != expected_url:
            await execute(
                "UPDATE reports SET photo_public_url=%s WHERE id=%s",
                (expected_url, report['id']),
            )
            updated += 1
    return updated
