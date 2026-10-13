from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.commands import setup_default_commands
from bot.config import settings
from core.db import acquire, close_pool, init_pool
from bot.handlers import admin, catalogs, commands, employee, reports, start
from bot.logger import setup_logging
from bot.middlewares.access import AccessMiddleware, UserContextMiddleware
from bot.services.notifications import dispatch_schedule_shift_notifications

logger = logging.getLogger(__name__)


async def ensure_runtime_migrations() -> None:
    """Apply small safe migrations needed when an existing database is reused."""
    async with acquire() as conn:
        async with conn.cursor() as cur:
            # Existing installations may still have ENUM('employee','admin').
            # Without this ALTER MySQL raises: Data truncated for column 'role'
            # when admin assigns the manager role.
            await cur.execute(
                "ALTER TABLE users MODIFY COLUMN role "
                "ENUM('employee','manager','admin') NOT NULL DEFAULT 'employee'"
            )


async def notifications_job(bot: Bot) -> None:
    await dispatch_schedule_shift_notifications(bot)


async def main() -> None:
    setup_logging()
    await init_pool()
    await ensure_runtime_migrations()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.update.middleware(AccessMiddleware())
    dp.update.middleware(UserContextMiddleware())

    dp.include_router(start.router)
    dp.include_router(commands.router)
    dp.include_router(employee.router)
    dp.include_router(reports.router)
    dp.include_router(catalogs.router)
    dp.include_router(admin.router)

    await setup_default_commands(bot)

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(notifications_job, "interval", minutes=1, args=[bot], id="notifications_job", replace_existing=True)
    scheduler.start()

    try:
        logger.info("Bot started")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await close_pool()
        logger.info("Bot stopped")


def run() -> None:
    asyncio.run(main())
