from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from core.db import fetch_all, fetch_one


def in_placeholders(values: Sequence[Any]) -> str:
    """``%s,%s,%s`` для условия ``IN (...)``."""
    return ",".join(["%s"] * len(values))


class Where:
    """Небольшой построитель WHERE: условия склеиваются через AND, аргументы копятся по порядку."""

    def __init__(self) -> None:
        self.clauses: list[str] = ["1=1"]
        self.args: list[Any] = []

    def add(self, clause: str, *args: Any) -> None:
        self.clauses.append(clause)
        self.args.extend(args)

    @property
    def sql(self) -> str:
        return " AND ".join(self.clauses)

    @property
    def params(self) -> tuple[Any, ...]:
        return tuple(self.args)


def like(value: str) -> str:
    return f"%{value.strip()}%"


async def paginate(
    base_query: str,
    count_query: str,
    args: tuple[Any, ...],
    page: int,
    page_size: int,
) -> dict[str, Any]:
    total_row = await fetch_one(count_query, args)
    total = int((total_row or {}).get("cnt", 0))
    pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(page, pages)
    offset = (page - 1) * page_size
    rows = await fetch_all(base_query + " LIMIT %s OFFSET %s", args + (page_size, offset))
    return {"items": rows, "page": page, "page_size": page_size, "total": total, "pages": pages}
