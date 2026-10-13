"""Админ: последние отчёты и карточка отчёта."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.services.reports import get_recent_reports, get_report_by_id
from bot.services.settings_service import get_latest_reports_days
from bot.ui.navigation import back_to_main_menu

router = Router(name="admin.reports")


@router.message(F.text == texts.MENU_LAST_REPORTS)
async def latest_reports(message: Message, is_admin: bool) -> None:
    # Сейчас экран отчётов открывается через inline-режим (menu:last_reports в start.py),
    # здесь отвечаем только когда отчётов нет.
    days = await get_latest_reports_days()
    if await get_recent_reports(days):
        return
    await message.answer(
        texts.REPORTS_EMPTY.format(days=days),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text=texts.BTN_MAIN_MENU,
                    callback_data="menu:main_admin" if is_admin else "menu:main_employee",
                )
            ]]
        ),
    )


@router.message(F.text.regexp(r"^/report_(\d+)$"))
async def open_report(message: Message, is_admin: bool) -> None:
    report = await get_report_by_id(int(message.text.split("_")[-1]))
    if not report:
        await message.answer(texts.REPORT_NOT_FOUND, reply_markup=back_to_main_menu(is_admin))
        return

    author = report.get("full_name") or report.get("username") or str(report["user_id"])
    caption = texts.REPORT_CARD.format(
        id=report["id"],
        author=author,
        created_at=report["created_at"].strftime("%d.%m.%Y %H:%M"),
        description=report.get("description") or texts.NO_DESCRIPTION,
    )

    if report.get("photo_file_id"):
        await message.answer_photo(report["photo_file_id"], caption=caption, reply_markup=back_to_main_menu(is_admin))
    else:
        await message.answer(caption, reply_markup=back_to_main_menu(is_admin))
