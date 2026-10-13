"""Админ: настройки бота (срок показа отчётов, получатели уведомлений)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.handlers.admin.common import ensure_admin, send_admin_main_menu
from bot.keyboards.inline import employees_selection_keyboard, settings_menu
from bot.services.settings_service import (
    get_new_report_recipient_ids,
    get_shift_event_recipient_ids,
    set_latest_reports_days,
)
from bot.services.users import list_all_users
from bot.states import AdminReportRecipientsState, AdminSettingsState
from bot.ui.navigation import with_back_button
from bot.utils.media import send_photo_screen
from bot.utils.telegram import edit_or_send

router = Router(name="admin.settings")


async def open_settings_menu(message: Message, is_admin: bool) -> None:
    """Экран настроек (кнопка меню и команда /settings)."""
    if not await ensure_admin(message, is_admin):
        return
    await send_photo_screen(
        message,
        asset_name="settings",
        caption="",
        reply_markup=with_back_button(settings_menu(), True),
    )


@router.message(F.text == texts.MENU_SETTINGS)
async def settings_open(message: Message, is_admin: bool) -> None:
    await open_settings_menu(message, is_admin)


@router.callback_query(F.data == "settings:reports_days")
async def settings_reports_days(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(callback, is_admin):
        return
    await state.set_state(AdminSettingsState.waiting_reports_days)
    await edit_or_send(callback, texts.REPORT_DAYS_PROMPT)
    await callback.answer()


@router.message(AdminSettingsState.waiting_reports_days)
async def settings_reports_days_save(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(message, is_admin):
        return
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except Exception:
        await message.answer(texts.POSITIVE_INTEGER_REQUIRED)
        return

    await set_latest_reports_days(days)
    await state.clear()
    await message.answer(texts.REPORT_DAYS_UPDATED.format(days=days))
    await send_admin_main_menu(message)


async def _open_recipients_selection(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    mode: str,
    current_ids: list[int],
    hint: str,
) -> None:
    """Экран выбора получателей; сохранение — в employees.employee_select (action=done)."""
    users = [user for user in await list_all_users() if user.get("role") in {"employee", "manager"}]
    selected_ids = set(current_ids) & {user["id"] for user in users}

    await state.set_state(AdminReportRecipientsState.selecting_users)
    await state.update_data(selection_mode=mode, selected_user_ids=list(selected_ids))
    await edit_or_send(callback, hint, reply_markup=employees_selection_keyboard(users, selected_ids))
    await callback.answer()


@router.callback_query(F.data == "settings:new_report_recipients")
async def settings_new_report_recipients(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(callback, is_admin):
        return
    await _open_recipients_selection(
        callback,
        state,
        mode="report_recipients",
        current_ids=await get_new_report_recipient_ids(),
        hint=texts.NEW_REPORT_RECIPIENTS_HINT,
    )


@router.callback_query(F.data == "settings:shift_event_recipients")
async def settings_shift_event_recipients(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(callback, is_admin):
        return
    await _open_recipients_selection(
        callback,
        state,
        mode="shift_event_recipients",
        current_ids=await get_shift_event_recipient_ids(),
        hint=texts.SHIFT_EVENT_RECIPIENTS_HINT,
    )
