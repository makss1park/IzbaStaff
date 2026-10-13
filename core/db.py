from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import aiomysql

from bot.config import settings

logger = logging.getLogger(__name__)

_pool: aiomysql.Pool | None = None


async def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            db=settings.mysql_db,
            autocommit=False,
            minsize=1,
            maxsize=10,
            charset="utf8mb4",
        )
        logger.info("MySQL pool initialized")


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("MySQL pool closed")


@asynccontextmanager
async def acquire():
    if _pool is None:
        await init_pool()
    assert _pool is not None
    conn = await _pool.acquire()
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        _pool.release(conn)


async def fetch_one(query: str, args: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    async with acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, args or ())
            return await cur.fetchone()


async def fetch_all(query: str, args: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    async with acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, args or ())
            return list(await cur.fetchall())


async def execute(query: str, args: tuple[Any, ...] | None = None) -> int:
    async with acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, args or ())
            return cur.lastrowid


async def executemany(query: str, args_list: list[tuple[Any, ...]]) -> None:
    async with acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(query, args_list)
