from __future__ import annotations


def parse_page(page: int | None) -> int:
    if not page or page < 1:
        return 1
    return page
