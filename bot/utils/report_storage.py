from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot

from bot.config import BASE_DIR, settings


def ensure_reports_storage_dir() -> Path:
    storage_dir = Path(settings.reports_storage_dir)
    if not storage_dir.is_absolute():
        storage_dir = BASE_DIR / storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def build_public_report_url(filename: str) -> str:
    """Build a URL for a saved report photo.

    REPORTS_PUBLIC_BASE_URL can be set either to the site origin:
      http://82.115.50.89
    or directly to the public reports folder:
      http://82.115.50.89/reports/

    In both cases the result must be:
      http://82.115.50.89/reports/<filename>
    """
    prefix = settings.reports_url_prefix.rstrip('/') or '/reports'
    base = (settings.reports_public_base_url or '').rstrip('/')
    relative = f"{prefix}/{filename}"
    if not base:
        return relative

    parsed = urlparse(base)
    base_path = parsed.path.rstrip('/')
    if base_path == prefix:
        return f"{base}/{filename}"
    return f"{base}{relative}"


async def save_telegram_report_photo(bot: Bot, file_id: str, *, filename_prefix: str = 'report') -> tuple[str, str]:
    storage_dir = ensure_reports_storage_dir()
    tg_file = await bot.get_file(file_id)
    original_name = Path(tg_file.file_path or '').name
    suffix = Path(original_name).suffix or '.jpg'
    filename = f"{filename_prefix}_{secrets.token_hex(12)}{suffix}"
    destination = storage_dir / filename
    await bot.download_file(tg_file.file_path, destination=destination)
    return str(destination.relative_to(BASE_DIR)).replace('\\', '/'), build_public_report_url(filename)
