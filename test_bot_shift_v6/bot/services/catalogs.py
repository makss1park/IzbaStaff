from __future__ import annotations

from typing import Any

from bot.database import execute, fetch_all, fetch_one
from bot.utils.dates import now_local


async def create_catalog(user_id: int, title: str, tags_text: str) -> int:
    now = now_local().replace(tzinfo=None)
    return int(
        await execute(
            """
            INSERT INTO catalogs (user_id, title, tags_text, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, title, tags_text, now, now),
        )
    )


async def add_catalog_photo(
    catalog_id: int,
    photo_file_id: str,
    photo_public_url: str | None = None,
    photo_local_path: str | None = None,
) -> int:
    now = now_local().replace(tzinfo=None)
    return int(
        await execute(
            """
            INSERT INTO catalog_photos (catalog_id, photo_file_id, photo_public_url, photo_local_path, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (catalog_id, photo_file_id, photo_public_url, photo_local_path, now),
        )
    )


async def get_catalog_by_id(catalog_id: int) -> dict[str, Any] | None:
    catalog = await fetch_one(
        """
        SELECT c.*, u.full_name, u.username, u.tg_id,
               (SELECT cp.photo_public_url FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_public_url,
               (SELECT cp.photo_file_id FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_file_id,
               (SELECT COUNT(*) FROM catalog_photos cp WHERE cp.catalog_id = c.id) AS photos_count
        FROM catalogs c
        JOIN users u ON u.id = c.user_id
        WHERE c.id=%s
        LIMIT 1
        """,
        (catalog_id,),
    )
    if not catalog:
        return None
    catalog['photos'] = await fetch_all(
        """
        SELECT * FROM catalog_photos
        WHERE catalog_id=%s
        ORDER BY id ASC
        """,
        (catalog_id,),
    )
    return catalog


async def search_catalogs(
    *,
    text_query: str = '',
    date_query: str = '',
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ['1=1']
    args: list[Any] = []
    q = text_query.strip()
    if q:
        like = f"%{q}%"
        clauses.append('(c.title LIKE %s OR c.tags_text LIKE %s OR u.full_name LIKE %s OR u.username LIKE %s)')
        args.extend([like, like, like, like])
    if date_query.strip():
        clauses.append('DATE(c.created_at) = %s')
        args.append(date_query.strip())

    where_sql = ' AND '.join(clauses)
    args.extend([limit])
    return await fetch_all(
        f"""
        SELECT c.*, u.full_name, u.username,
               (SELECT cp.photo_public_url FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_public_url,
               (SELECT cp.photo_file_id FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_file_id,
               (SELECT COUNT(*) FROM catalog_photos cp WHERE cp.catalog_id = c.id) AS photos_count
        FROM catalogs c
        JOIN users u ON u.id = c.user_id
        WHERE {where_sql}
        ORDER BY c.created_at DESC
        LIMIT %s
        """,
        tuple(args),
    )


async def list_catalogs(limit: int = 50) -> list[dict[str, Any]]:
    return await search_catalogs(limit=limit)
