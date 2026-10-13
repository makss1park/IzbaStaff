"""Штрафы и закрытие зарплатного периода для выбранных сотрудников.

Штраф может назначать админ (через «Управление сотрудниками») и сотрудник, которому
админ выдал доступ в «Настройки → Выдать доступ → Назначение штрафов» (кнопка
«Назначить штраф» в его главном меню).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.handlers.admin.common import ensure_admin, format_names_list, keep_selection_only, selected_user_ids
from bot.handlers.admin.employees import FINE_MODE
from bot.handlers.start import clear_profile_photo
from bot.keyboards.inline import employees_selection_keyboard
from bot.services.fines import create_fine
from bot.services.payroll import bulk_close_periods
from bot.services.permissions import can_assign_fines, fine_targets
from bot.services.users import display_name, get_user_by_id, list_all_users
from bot.states import AdminFineState
from bot.ui.navigation import back_to_main_menu
from bot.utils.media import open_photo_screen_from_callback
from bot.utils.telegram import edit_or_send

router = Router(name="admin.payroll")


async def _ensure_fine_access(event: Message | CallbackQuery, is_admin: bool, db_user: dict) -> bool:
    if is_admin or await can_assign_fines(db_user):
        return True
    return await ensure_admin(event, is_admin)  # отвечает «только для администратора»


# =========================
# ШТРАФЫ
# =========================

@router.callback_query(F.data == "menu:fine")
async def fine_menu(callback: CallbackQuery, state: FSMContext, is_admin: bool, db_user: dict) -> None:
    """Кнопка «Назначить штраф» в главном меню сотрудника с выданным доступом."""
    if not await _ensure_fine_access(callback, is_admin, db_user):
        return

    users = fine_targets(await list_all_users(), db_user)
    if not users:
        await callback.answer(texts.NO_EMPLOYEES_FOR_FINE, show_alert=True)
        return

    if callback.message is not None:
        await clear_profile_photo(state, callback.bot, callback.message.chat.id)
    await state.clear()
    await state.update_data(selection_mode=FINE_MODE, selected_user_ids=[])
    await open_photo_screen_from_callback(
        callback,
        asset_name="employee_manage",
        caption=texts.SELECT_EMPLOYEES_FOR_FINE,
        reply_markup=employees_selection_keyboard(users, set()),
    )
    await callback.answer()


@router.message(AdminFineState.waiting_reason)
async def admin_fine_reason(message: Message, state: FSMContext, is_admin: bool, db_user: dict) -> None:
    if not await _ensure_fine_access(message, is_admin, db_user):
        return
    await state.update_data(fine_reason=message.text.strip())
    await state.set_state(AdminFineState.waiting_amount)
    await message.answer(texts.ENTER_FINE_AMOUNT)


@router.message(AdminFineState.waiting_amount)
async def admin_fine_amount(message: Message, state: FSMContext, is_admin: bool, db_user: dict) -> None:
    if not await _ensure_fine_access(message, is_admin, db_user):
        return
    try:
        amount = float(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer(texts.INVALID_AMOUNT)
        return

    data = await state.get_data()
    user_ids = selected_user_ids(data)
    if not is_admin:
        # Сотрудник с доступом может штрафовать только тех, кого ему разрешено.
        allowed = {user["id"] for user in fine_targets(await list_all_users(), db_user)}
        user_ids = [user_id for user_id in user_ids if user_id in allowed]
    reason = data["fine_reason"]
    names = []

    for user_id in user_ids:
        await create_fine(user_id, amount, reason, db_user["id"])
        user = await get_user_by_id(user_id)
        if not user:
            continue
        names.append(display_name(user))
        try:
            await message.bot.send_message(
                user["tg_id"],
                texts.FINE_ASSIGNED_NOTIFICATION.format(reason=reason, amount=amount),
            )
        except Exception:
            pass

    await keep_selection_only(state, user_ids)
    await message.answer(
        texts.FINE_APPLIED.format(name=format_names_list(names), reason=reason, amount=amount),
        reply_markup=back_to_main_menu(is_admin),
    )


# =========================
# ЗАКРЫТИЕ ПЕРИОДА (только админ)
# =========================

@router.callback_query(F.data.startswith("payroll_confirm:"))
async def payroll_confirm(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(callback, is_admin):
        return
    if callback.data.split(":")[-1] == "no":
        await callback.answer(texts.CANCELLED)
        return

    user_ids = selected_user_ids(await state.get_data())
    await bulk_close_periods(user_ids)

    names = []
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if user:
            names.append(display_name(user))

    await edit_or_send(
        callback,
        texts.PAYROLL_DONE_INLINE.format(names=format_names_list(names)),
        reply_markup=back_to_main_menu(True),
    )
    await callback.answer()
