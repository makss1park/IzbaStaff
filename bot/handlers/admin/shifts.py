"""Админ: активные смены, карточка смены, удаление и правка длительности."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.handlers.admin.common import active_workers_open_keyboard, ensure_admin
from bot.keyboards.inline import cancel_shift_edit_keyboard, shift_admin_actions_keyboard
from bot.services.shifts import delete_shift, get_active_shifts, get_shift_by_id, update_shift_duration_minutes
from bot.states import AdminShiftEditState
from bot.ui.navigation import back_to_main_menu, with_back_button
from bot.utils.dates import seconds_to_human
from bot.utils.media import send_photo_screen
from bot.utils.telegram import edit_or_send

router = Router(name="admin.shifts")


async def active_workers(message: Message, is_admin: bool) -> None:
    """Экран активных смен (команда /active_workers)."""
    if not await ensure_admin(message, is_admin):
        return

    if not await get_active_shifts():
        await message.answer(texts.ACTIVE_SHIFTS_EMPTY, reply_markup=back_to_main_menu(True))
        return

    await send_photo_screen(
        message,
        asset_name="active_employee",
        caption=texts.ACTIVE_SHIFTS_SCREEN,
        reply_markup=with_back_button(active_workers_open_keyboard(), True),
    )


def _format_admin_shift_card(shift: dict) -> str:
    name = shift.get("full_name") or shift.get("username") or str(shift.get("tg_id") or shift.get("user_id"))
    opened_at = shift.get("opened_at")
    closed_at = shift.get("closed_at")
    return texts.ADMIN_SHIFT_CARD.format(
        name=html.escape(name),
        opened_at=opened_at.strftime("%d.%m.%Y %H:%M") if opened_at else texts.UNKNOWN,
        closed_at=closed_at.strftime("%d.%m.%Y %H:%M") if closed_at else texts.DASH,
        duration=seconds_to_human(int(shift.get("duration_seconds", 0) or 0)),
        late=seconds_to_human(int(shift.get("late_seconds", 0) or 0)),
    )


@router.message(F.text.regexp(r"^/admin_shift_(\d+)$"))
async def open_admin_shift(message: Message, is_admin: bool) -> None:
    if not await ensure_admin(message, is_admin):
        return
    shift_id = int(message.text.split("_")[-1])
    shift = await get_shift_by_id(shift_id)
    if not shift:
        await message.answer(texts.SHIFT_NOT_FOUND_ADMIN, reply_markup=back_to_main_menu(True))
        return
    await message.answer(
        _format_admin_shift_card(shift),
        reply_markup=shift_admin_actions_keyboard(shift_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_shift:"))
async def admin_shift_action(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(callback, is_admin):
        return

    parts = callback.data.split(":")
    action = parts[1]

    if action == "cancel_edit":
        await state.clear()
        await edit_or_send(callback, texts.CANCELLED, reply_markup=back_to_main_menu(True))
        await callback.answer(texts.CANCELLED)
        return

    shift_id = int(parts[2])
    if not await get_shift_by_id(shift_id):
        await edit_or_send(callback, texts.SHIFT_NOT_FOUND_ADMIN, reply_markup=back_to_main_menu(True))
        await callback.answer()
        return

    if action == "delete":
        await delete_shift(shift_id)
        await edit_or_send(callback, texts.SHIFT_DELETED, reply_markup=back_to_main_menu(True))
        await callback.answer(texts.SAVED)
    elif action == "edit":
        await state.set_state(AdminShiftEditState.waiting_minutes)
        await state.update_data(edit_shift_id=shift_id)
        await edit_or_send(callback, texts.ENTER_SHIFT_MINUTES, reply_markup=cancel_shift_edit_keyboard())
        await callback.answer()


@router.message(AdminShiftEditState.waiting_minutes)
async def admin_shift_set_minutes(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(message, is_admin):
        return
    try:
        minutes = int((message.text or "").strip())
        if minutes < 0:
            raise ValueError
    except Exception:
        await message.answer(texts.INVALID_SHIFT_MINUTES, reply_markup=cancel_shift_edit_keyboard())
        return

    data = await state.get_data()
    shift_id = int(data.get("edit_shift_id") or 0)
    if not shift_id or not await get_shift_by_id(shift_id):
        await state.clear()
        await message.answer(texts.SHIFT_NOT_FOUND_ADMIN, reply_markup=back_to_main_menu(True))
        return

    await update_shift_duration_minutes(shift_id, minutes)
    await state.clear()
    await message.answer(texts.SHIFT_UPDATED, reply_markup=back_to_main_menu(True))
