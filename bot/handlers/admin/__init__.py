"""Админские хендлеры бота.

Раньше всё лежало в одном admin.py (~1150 строк); теперь разбито по разделам.
Порядок подключения под-роутеров повторяет порядок хендлеров в старом файле —
это важно для aiogram: при совпадении фильтров срабатывает первый хендлер.
"""
from __future__ import annotations

from aiogram import Router

from bot.handlers.admin import employees, inline, payroll, reports, settings, shifts
from bot.handlers.admin.common import active_workers_open_keyboard
from bot.handlers.admin.employees import manage_employees
from bot.handlers.admin.reports import latest_reports
from bot.handlers.admin.settings import open_settings_menu
from bot.handlers.admin.shifts import active_workers

router = Router(name="admin")
router.include_routers(
    reports.router,
    inline.router,
    employees.router,
    payroll.router,
    settings.router,
    shifts.router,
)

__all__ = [
    "router",
    "active_workers",
    "active_workers_open_keyboard",
    "latest_reports",
    "manage_employees",
    "open_settings_menu",
]
