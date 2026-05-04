from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.handlers import admin, employee, reports, start

router = Router()

@router.message(Command("grafic"))
async def cmd_grafic(message: Message, db_user: dict) -> None:
    await employee.graph(message, db_user)


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext) -> None:
    await reports.quick_report(message, state)


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext, db_user: dict) -> None:
    await employee.profile(message, db_user, state)


@router.message(Command("last_reports"))
async def cmd_last_reports(message: Message, is_admin: bool) -> None:
    await admin.latest_reports(message, is_admin)


@router.message(Command("active_workers"))
async def cmd_active_workers(message: Message, is_admin: bool) -> None:
    await admin.active_workers(message, is_admin)


@router.message(Command("employees"))
async def cmd_employees(message: Message, state: FSMContext, is_admin: bool) -> None:
    await admin.manage_employees(message, state, is_admin)




@router.message(Command("settings"))
async def cmd_settings(message: Message, is_admin: bool) -> None:
    await admin.open_settings_menu(message, is_admin)
