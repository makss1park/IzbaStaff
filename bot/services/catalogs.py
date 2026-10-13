from __future__ import annotations

from typing import Any

from core.clock import now_naive
from core.repositories import catalogs as catalogs_repo


async def create_catalog(user_id: int, title: str, tags_text: str) -> int:
    return await catalogs_repo.create(user_id, title, tags_text, now_naive())


async def add_catalog_photo(
    catalog_id: int,
    photo_file_id: str,
    photo_public_url: str | None = None,
    photo_local_path: str | None = None,
) -> int:
    return await catalogs_repo.add_photo(
        catalog_id=catalog_id,
        photo_file_id=photo_file_id,
        photo_public_url=photo_public_url,
        photo_local_path=photo_local_path,
        now=now_naive(),
    )


async def get_catalog_by_id(catalog_id: int) -> dict[str, Any] | None:
    catalog = await catalogs_repo.get_with_user(catalog_id)
    if not catalog:
        return None
    catalog["photos"] = await catalogs_repo.list_photos(catalog_id)
    return catalog


async def search_catalogs(
    *,
    text_query: str = "",
    date_query: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    return await catalogs_repo.search(text_query=text_query, date_query=date_query, limit=limit)


async def list_catalogs(limit: int = 50) -> list[dict[str, Any]]:
    return await search_catalogs(limit=limit)
