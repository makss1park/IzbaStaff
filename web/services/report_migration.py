from __future__ import annotations

from pathlib import Path

from aiogram import Bot

from bot.utils.report_storage import build_public_report_url, save_telegram_report_photo
from core.repositories import reports as reports_repo


async def backfill_report_public_urls(bot: Bot) -> int:
    """Скачивает из Telegram фото старых отчётов, у которых нет локальной копии или ссылки."""
    processed = 0
    for report in await reports_repo.list_missing_local_copy():
        local_path, public_url = await save_telegram_report_photo(
            bot,
            report["photo_file_id"],
            filename_prefix=f"report_{report['id']}",
        )
        await reports_repo.set_photo_location(report["id"], local_path, public_url)
        processed += 1
    return processed


async def normalize_report_urls() -> int:
    """Пересобирает публичные ссылки по текущим настройкам REPORTS_PUBLIC_BASE_URL / REPORTS_URL_PREFIX."""
    updated = 0
    for report in await reports_repo.list_with_local_path():
        expected_url = build_public_report_url(Path(report["photo_local_path"]).name)
        if report.get("photo_public_url") != expected_url:
            await reports_repo.set_public_url(report["id"], expected_url)
            updated += 1
    return updated
