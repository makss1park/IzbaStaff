"""Ссылки на локально сохранённые фото отчётов и каталогов для страниц админки."""
from __future__ import annotations

from pathlib import Path

# Эти пути обслуживает само FastAPI-приложение (см. web/main.py), поэтому превью
# работают, даже если nginx отдельно не проксирует /reports и /catalogs.
REPORT_FILES_URL = "/web/report-files"
CATALOG_FILES_URL = "/web/catalog-files"


def resolve_image_url(item: dict, *, files_url: str, local_key: str, public_key: str) -> str | None:
    local_path = item.get(local_key)
    if local_path:
        return f"{files_url}/{Path(local_path).name}"
    return item.get(public_key) or None


def report_image_url(item: dict) -> str | None:
    return resolve_image_url(item, files_url=REPORT_FILES_URL, local_key="photo_local_path", public_key="photo_public_url")


def catalog_preview_url(item: dict) -> str | None:
    return resolve_image_url(item, files_url=CATALOG_FILES_URL, local_key="preview_local_path", public_key="preview_public_url")


def catalog_photo_url(photo: dict) -> str | None:
    return resolve_image_url(photo, files_url=CATALOG_FILES_URL, local_key="photo_local_path", public_key="photo_public_url")
