from __future__ import annotations

import math
from typing import Any

from bot.database import fetch_all, fetch_one


def parse_page(page: int | None) -> int:
    if not page or page < 1:
        return 1
    return page


def offset_for(page: int, page_size: int) -> int:
    return (page - 1) * page_size


async def paginate_query(base_query: str, count_query: str, args: tuple[Any, ...], page: int, page_size: int) -> dict[str, Any]:
    total_row = await fetch_one(count_query, args)
    total = int((total_row or {}).get('cnt', 0))
    pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(page, pages)
    rows = await fetch_all(base_query + ' LIMIT %s OFFSET %s', args + (page_size, offset_for(page, page_size)))
    return {'items': rows, 'page': page, 'page_size': page_size, 'total': total, 'pages': pages}
