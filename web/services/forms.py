"""Разбор значений из HTML-форм."""
from __future__ import annotations

from datetime import datetime

_DATETIME_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def parse_dt_local(value: str | None) -> datetime | None:
    """Значение <input type="datetime-local"> (и пары похожих форматов) → datetime или None."""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
