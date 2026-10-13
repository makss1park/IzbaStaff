"""Совместимость со старыми импортами.

Подключение к MySQL переехало в :mod:`core.db`. Новый код должен импортировать
оттуда (а лучше — работать через :mod:`core.repositories`).
"""
from core.db import acquire, close_pool, execute, executemany, fetch_all, fetch_one, init_pool

__all__ = ["acquire", "close_pool", "execute", "executemany", "fetch_all", "fetch_one", "init_pool"]
