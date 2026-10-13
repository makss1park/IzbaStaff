from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import execute, fetch_all, fetch_one
from core.repositories._sql import Where, in_placeholders, like, paginate

# Превью (первое фото) и количество фото каталога — общие подзапросы для списков и карточки.
_PREVIEW_PUBLIC_URL = (
    "(SELECT cp.photo_public_url FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_public_url"
)
_PREVIEW_FILE_ID = (
    "(SELECT cp.photo_file_id FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_file_id"
)
_PREVIEW_LOCAL_PATH = (
    "(SELECT cp.photo_local_path FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_local_path"
)
_PHOTOS_COUNT = "(SELECT COUNT(*) FROM catalog_photos cp WHERE cp.catalog_id = c.id) AS photos_count"


def _text_filter(where: Where, query: str) -> None:
    if query.strip():
        pattern = like(query)
        where.add(
            "(c.title LIKE %s OR c.tags_text LIKE %s OR u.full_name LIKE %s OR u.username LIKE %s)",
            pattern, pattern, pattern, pattern,
        )


async def create(user_id: int, title: str, tags_text: str, now: datetime) -> int:
    return int(
        await execute(
            """
            INSERT INTO catalogs (user_id, title, tags_text, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, title, tags_text, now, now),
        )
    )


async def add_photo(
    *,
    catalog_id: int,
    photo_file_id: str,
    photo_public_url: str | None,
    photo_local_path: str | None,
    now: datetime,
) -> int:
    return int(
        await execute(
            """
            INSERT INTO catalog_photos (catalog_id, photo_file_id, photo_public_url, photo_local_path, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (catalog_id, photo_file_id, photo_public_url, photo_local_path, now),
        )
    )


async def get_with_user(catalog_id: int) -> dict[str, Any] | None:
    return await fetch_one(
        f"""
        SELECT c.*, u.full_name, u.username, u.tg_id,
               {_PREVIEW_PUBLIC_URL},
               {_PREVIEW_FILE_ID},
               {_PHOTOS_COUNT}
        FROM catalogs c
        JOIN users u ON u.id = c.user_id
        WHERE c.id=%s
        LIMIT 1
        """,
        (catalog_id,),
    )


async def list_photos(catalog_id: int) -> list[dict[str, Any]]:
    return await fetch_all(
        """
        SELECT * FROM catalog_photos
        WHERE catalog_id=%s
        ORDER BY id ASC
        """,
        (catalog_id,),
    )


async def list_photos_for_catalogs(catalog_ids: list[int]) -> list[dict[str, Any]]:
    if not catalog_ids:
        return []
    return await fetch_all(
        f"""
        SELECT id, catalog_id, photo_public_url, photo_local_path, created_at
        FROM catalog_photos
        WHERE catalog_id IN ({in_placeholders(catalog_ids)})
        ORDER BY catalog_id ASC, id ASC
        """,
        tuple(catalog_ids),
    )


async def search(*, text_query: str = "", date_query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Поиск каталогов для inline-режима бота."""
    where = Where()
    _text_filter(where, text_query)
    if date_query.strip():
        where.add("DATE(c.created_at) = %s", date_query.strip())

    return await fetch_all(
        f"""
        SELECT c.*, u.full_name, u.username,
               {_PREVIEW_PUBLIC_URL},
               {_PREVIEW_FILE_ID},
               {_PHOTOS_COUNT}
        FROM catalogs c
        JOIN users u ON u.id = c.user_id
        WHERE {where.sql}
        ORDER BY c.created_at DESC
        LIMIT %s
        """,
        where.params + (limit,),
    )


async def search_page(
    *,
    query: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """Постраничный поиск каталогов для веб-админки."""
    where = Where()
    _text_filter(where, query)
    if date_from.strip():
        where.add("DATE(c.created_at) >= %s", date_from.strip())
    if date_to.strip():
        where.add("DATE(c.created_at) <= %s", date_to.strip())

    base_query = f"""
        SELECT c.*, u.full_name, u.username,
               {_PREVIEW_PUBLIC_URL},
               {_PREVIEW_LOCAL_PATH},
               {_PHOTOS_COUNT}
        FROM catalogs c
        JOIN users u ON u.id = c.user_id
        WHERE {where.sql}
        ORDER BY c.created_at DESC
    """
    count_query = f"SELECT COUNT(*) AS cnt FROM catalogs c JOIN users u ON u.id=c.user_id WHERE {where.sql}"
    return await paginate(base_query, count_query, where.params, page, page_size)
