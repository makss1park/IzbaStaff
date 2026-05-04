from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot

from bot.config import BASE_DIR
from bot.config import settings


def ensure_catalogs_storage_dir() -> Path:
    storage_dir = Path(getattr(settings, 'catalogs_storage_dir', 'storage/catalogs'))
    if not storage_dir.is_absolute():
        storage_dir = BASE_DIR / storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def build_public_catalog_url(filename: str) -> str:
    prefix = getattr(settings, 'catalogs_url_prefix', '/catalogs').rstrip('/') or '/catalogs'
    base = (getattr(settings, 'catalogs_public_base_url', '') or getattr(settings, 'reports_public_base_url', '') or '').rstrip('/')
    relative = f"{prefix}/{filename}"
    if not base:
        return relative

    parsed = urlparse(base)
    if parsed.path.rstrip('/') == prefix:
        return f"{base}/{filename}"
    return f"{base}{relative}"


async def save_telegram_catalog_photo(bot: Bot, file_id: str, *, filename_prefix: str = 'catalog') -> tuple[str, str]:
    storage_dir = ensure_catalogs_storage_dir()
    tg_file = await bot.get_file(file_id)
    original_name = Path(tg_file.file_path or '').name
    suffix = Path(original_name).suffix or '.jpg'
    filename = f"{filename_prefix}_{secrets.token_hex(12)}{suffix}"
    destination = storage_dir / filename
    await bot.download_file(tg_file.file_path, destination=destination)
    return str(destination.relative_to(BASE_DIR)).replace('\\', '/'), build_public_catalog_url(filename)
