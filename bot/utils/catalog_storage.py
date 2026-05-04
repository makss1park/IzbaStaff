from __future__ import annotations

import secrets
from pathlib import Path

from aiogram import Bot

from bot.config import BASE_DIR
from bot.config import settings
from bot.utils.report_storage import ensure_reports_storage_dir


def ensure_catalogs_storage_dir() -> Path:
    storage_dir = BASE_DIR / 'storage' / 'catalogs'
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def build_public_catalog_url(filename: str) -> str:
    prefix = '/catalogs'
    base = (getattr(settings, 'reports_public_base_url', '') or '').rstrip('/')
    relative = f"{prefix}/{filename}"
    return f"{base}{relative}" if base else relative


async def save_telegram_catalog_photo(bot: Bot, file_id: str, *, filename_prefix: str = 'catalog') -> tuple[str, str]:
    storage_dir = ensure_catalogs_storage_dir()
    ensure_reports_storage_dir()
    tg_file = await bot.get_file(file_id)
    original_name = Path(tg_file.file_path or '').name
    suffix = Path(original_name).suffix or '.jpg'
    filename = f"{filename_prefix}_{secrets.token_hex(12)}{suffix}"
    destination = storage_dir / filename
    await bot.download_file(tg_file.file_path, destination=destination)
    return str(destination.relative_to(BASE_DIR)).replace('\\', '/'), build_public_catalog_url(filename)
