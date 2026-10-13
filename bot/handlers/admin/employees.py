"""Админ: выбор сотрудников и действия над ними (профиль, период, редактирование, удаление)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.handlers.admin.common import (
    ensure_admin,
    format_days,
    format_names_list,
    format_selected_users,
    selected_user_ids,
    skip_button,
)
from bot.keyboards.inline import (
    confirm_payroll_keyboard,
    employee_actions_keyboard,
    employees_selection_keyboard,
    period_info_actions_keyboard,
    role_change_keyboard,
)
from bot.services.notifications import notify_employee_schedule_changed, notify_fine_access_changed
from bot.services.payroll import get_current_period_fines, get_current_period_shift_list, get_current_period_stats
from bot.services.schedules import get_schedules_map
from bot.services.schedules import set_schedule as apply_user_schedule
from bot.services.permissions import can_assign_fines, fine_targets
from bot.services.settings_service import (
    get_fine_grantee_ids,
    set_fine_grantee_ids,
    set_new_report_recipient_ids,
    set_shift_event_recipient_ids,
)
from bot.services.users import (
    decorate_users_with_schedule,
    delete_users,
    display_name,
    get_user_by_id,
    list_all_users,
    update_user,
)
from bot.states import AdminFineState, EditEmployeeState
from bot.ui.navigation import back_to_main_menu
from bot.utils.formatters import format_period_stats, format_profile
from bot.utils.media import send_photo_screen
from bot.utils.telegram import edit_or_send
from bot.utils.validator import is_valid_full_name, is_valid_phone, parse_rate, parse_schedule_input

router = Router(name="admin.employees")

# Режимы, в которых тот же экран выбора сотрудников используется для выбора получателей уведомлений.
_RECIPIENT_MODES = {
    "report_recipients": (
        set_new_report_recipient_ids,
        texts.NEW_REPORT_RECIPIENTS_SAVED_INLINE,
        texts.NEW_REPORT_RECIPIENTS_CLEARED,
    ),
    "shift_event_recipients": (
        set_shift_event_recipient_ids,
        texts.SHIFT_EVENT_RECIPIENTS_SAVED_INLINE,
        texts.SHIFT_EVENT_RECIPIENTS_CLEARED,
    ),
    # «Настройки → Выдать доступ → Назначение штрафов»
    "fine_grantees": (
        set_fine_grantee_ids,
        texts.FINE_GRANTEES_SAVED_INLINE,
        texts.FINE_GRANTEES_CLEARED,
    ),
}

# Режим, в котором экраном выбора пользуется не только админ, но и сотрудник
# с выданным доступом: выбор тех, кому назначить штраф (кнопка «Назначить штраф»).
FINE_MODE = "fine"

_CHANGE_LABELS = {
    "full_name": texts.CHANGE_LABEL_FULL_NAME,
    "phone": texts.CHANGE_LABEL_PHONE,
    "hourly_rate": texts.CHANGE_LABEL_RATE,
    "role": texts.CHANGE_LABEL_ROLE,
}


async def manage_employees(message: Message, state: FSMContext, is_admin: bool) -> None:
    """Экран выбора сотрудников (кнопка меню и команда /employees)."""
    if not await ensure_admin(message, is_admin):
        return

    users = await list_all_users()
    await state.clear()
    await state.update_data(selected_user_ids=[])
    await send_photo_screen(
        message,
        asset_name="employee_manage",
        caption=texts.SELECT_EMPLOYEES,
        reply_markup=employees_selection_keyboard(users, set()),
    )


# =========================
# ВЫБОР СОТРУДНИКОВ
# =========================

async def _finish_recipients_selection(callback: CallbackQuery, state: FSMContext, mode: str, users: list[dict], selected_ids: list[int]) -> None:
    save, saved_text, cleared_text = _RECIPIENT_MODES[mode]
    previous_ids = set(await get_fine_grantee_ids()) if mode == "fine_grantees" else set()
    await save(selected_ids)
    if mode == "fine_grantees":
        await notify_fine_access_changed(
            callback.bot,
            granted_ids=set(selected_ids) - previous_ids,
            revoked_ids=previous_ids - set(selected_ids),
        )
    await state.clear()
    if selected_ids:
        text = saved_text.format(selected_text=format_selected_users(users, selected_ids))
    else:
        text = cleared_text
    await edit_or_send(callback, text, reply_markup=back_to_main_menu(True))
    await callback.answer(texts.SAVED)


@router.callback_query(F.data.startswith("emp_select:"))
async def employee_select(callback: CallbackQuery, state: FSMContext, is_admin: bool, db_user: dict) -> None:
    data = await state.get_data()
    selection_mode = data.get("selection_mode")

    # Не-админу экран выбора доступен только для назначения штрафа и только с выданным доступом.
    if not is_admin and not (selection_mode == FINE_MODE and await can_assign_fines(db_user)):
        await ensure_admin(callback, is_admin)
        return

    action = callback.data.split(":")[1]
    users = await list_all_users()
    if selection_mode in _RECIPIENT_MODES:
        users = [user for user in users if user.get("role") in {"employee", "manager"}]
    elif selection_mode == FINE_MODE:
        users = fine_targets(users, db_user)
    all_ids = {user["id"] for user in users}
    selected = set(selected_user_ids(data)) & all_ids

    if action in {"toggle", "all", "none"}:
        if action == "toggle":
            selected ^= {int(callback.data.split(":")[-1])}
        elif action == "all":
            selected = all_ids
        else:
            selected = set()
        await state.update_data(selected_user_ids=list(selected))
        await callback.message.edit_reply_markup(reply_markup=employees_selection_keyboard(users, selected))

    elif action == "done":
        selected_ids = sorted(selected)
        if selection_mode in _RECIPIENT_MODES:
            await _finish_recipients_selection(callback, state, selection_mode, users, selected_ids)
            return

        if not selected_ids:
            await callback.answer(texts.SELECT_AT_LEAST_ONE, show_alert=True)
            return

        if selection_mode == FINE_MODE:
            # Сразу к штрафу: дальше работают те же шаги, что и у админа (описание → сумма).
            await state.update_data(selected_user_ids=selected_ids)
            await state.set_state(AdminFineState.waiting_reason)
            await edit_or_send(callback, texts.ENTER_FINE_REASON)
            await callback.answer()
            return
        await state.update_data(selected_user_ids=selected_ids)
        await edit_or_send(
            callback,
            texts.CHOOSE_ACTION.format(selected_text=format_selected_users(users, selected_ids)),
            reply_markup=employee_actions_keyboard(),
        )

    await callback.answer()


# =========================
# ДЕЙСТВИЯ НАД ВЫБРАННЫМИ
# =========================

async def _remove_keyboard(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _show_profiles(callback: CallbackQuery, user_ids: list[int]) -> None:
    await _remove_keyboard(callback)
    schedules = await get_schedules_map(user_ids)
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if not user:
            continue
        await decorate_users_with_schedule([user], schedules)
        await callback.message.answer(format_profile(user), reply_markup=back_to_main_menu(True), parse_mode="HTML")


async def _show_period_info(callback: CallbackQuery, user_ids: list[int]) -> None:
    await _remove_keyboard(callback)
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if not user:
            continue
        stats = await get_current_period_stats(user_id)
        shifts = await get_current_period_shift_list(user_id)
        fines = await get_current_period_fines(user_id)
        await callback.message.answer(
            texts.PERIOD_INFO_HEADER.format(
                name=display_name(user),
                stats=format_period_stats(stats, shifts=shifts, fines=fines),
            ),
            reply_markup=period_info_actions_keyboard(user_id),
            parse_mode="HTML",
        )


async def _delete_employees(callback: CallbackQuery, state: FSMContext, user_ids: list[int]) -> bool:
    users_to_delete = []
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if user and user.get("role") in {"employee", "manager"}:
            users_to_delete.append(user)

    if not users_to_delete:
        await callback.answer(texts.SELECT_AT_LEAST_ONE, show_alert=True)
        return False

    await delete_users([user["id"] for user in users_to_delete])
    await state.clear()
    await edit_or_send(
        callback,
        texts.EMPLOYEES_DELETED.format(selected_text=format_names_list([display_name(u) for u in users_to_delete])),
        reply_markup=back_to_main_menu(True),
    )
    return True


async def _confirm_payroll_close(callback: CallbackQuery, user_ids: list[int]) -> None:
    lines = []
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if not user:
            continue
        stats = await get_current_period_stats(user_id)
        lines.append(texts.PAYROLL_LINE.format(name=display_name(user), amount=stats.get("earned_amount", 0)))
    await edit_or_send(
        callback,
        texts.CONFIRM_PAYROLL_INLINE.format(lines="\n".join(lines)),
        reply_markup=confirm_payroll_keyboard(),
    )


@router.callback_query(F.data.startswith("emp_action:"))
async def employee_action(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await ensure_admin(callback, is_admin):
        return

    code = callback.data.split(":")[-1]
    user_ids = selected_user_ids(await state.get_data())
    if not user_ids:
        await callback.answer(texts.SELECT_EMPLOYEES_FIRST, show_alert=True)
        return

    if code == "all_info":
        await _show_profiles(callback, user_ids)
    elif code == "period_info":
        await _show_period_info(callback, user_ids)
    elif code == "change_employee_info":
        await state.update_data(user_ids=user_ids, changes={})
        await state.set_state(EditEmployeeState.waiting_full_name)
        await callback.message.answer(texts.ENTER_NEW_FULL_NAME, reply_markup=skip_button("skip_full_name"))
    elif code == "delete_employee":
        if not await _delete_employees(callback, state, user_ids):
            return
    elif code == "fine":
        await state.set_state(AdminFineState.waiting_reason)
        await edit_or_send(callback, texts.ENTER_FINE_REASON)
    elif code == "payroll_close":
        await _confirm_payroll_close(callback, user_ids)

    await callback.answer()


# =========================
# РЕДАКТИРОВАНИЕ ПРОФИЛЯ: ФИО → телефон → ставка → график → роль
# =========================

async def _ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(EditEmployeeState.waiting_phone)
    await message.answer(texts.ENTER_PHONE, reply_markup=skip_button("skip_phone"))


async def _ask_rate(message: Message, state: FSMContext) -> None:
    await state.set_state(EditEmployeeState.waiting_rate)
    await message.answer(texts.ENTER_RATE, reply_markup=skip_button("skip_rate"))


async def _ask_schedule(message: Message, state: FSMContext) -> None:
    await state.set_state(EditEmployeeState.waiting_schedule)
    await message.answer(texts.ENTER_SCHEDULE, reply_markup=skip_button("skip_schedule"))


async def _ask_role(message: Message, state: FSMContext) -> None:
    await state.set_state(EditEmployeeState.waiting_role)
    await message.answer(texts.ENTER_ROLE, reply_markup=role_change_keyboard())


async def _store_change(state: FSMContext, key: str, value) -> None:
    data = await state.get_data()
    data.setdefault("changes", {})[key] = value
    await state.update_data(data)


@router.message(EditEmployeeState.waiting_full_name)
async def set_full_name(message: Message, state: FSMContext):
    full_name = " ".join((message.text or "").strip().split())
    if not is_valid_full_name(full_name):
        await message.answer(texts.INVALID_FULL_NAME)
        return
    await _store_change(state, "full_name", full_name)
    await _ask_phone(message, state)


@router.callback_query(F.data == "skip_full_name")
async def skip_full_name(callback: CallbackQuery, state: FSMContext):
    await _ask_phone(callback.message, state)


@router.message(EditEmployeeState.waiting_phone)
async def set_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not is_valid_phone(phone):
        await message.answer(texts.INVALID_PHONE_EDIT)
        return
    await _store_change(state, "phone", phone)
    await _ask_rate(message, state)


@router.callback_query(F.data == "skip_phone")
async def skip_phone(callback: CallbackQuery, state: FSMContext):
    await _ask_rate(callback.message, state)


@router.message(EditEmployeeState.waiting_rate)
async def set_rate(message: Message, state: FSMContext):
    try:
        rate = parse_rate(message.text)
    except Exception:
        await message.answer(texts.INVALID_RATE)
        return
    await _store_change(state, "hourly_rate", rate)
    await _ask_schedule(message, state)


@router.callback_query(F.data == "skip_rate")
async def skip_rate(callback: CallbackQuery, state: FSMContext):
    await _ask_schedule(callback.message, state)


@router.message(EditEmployeeState.waiting_schedule)
async def set_employee_schedule(message: Message, state: FSMContext):
    try:
        days, start_time, end_time = parse_schedule_input(message.text)
    except Exception:
        await message.answer(texts.INVALID_SCHEDULE)
        return
    await state.update_data(schedule={"days": days, "start_time": start_time, "end_time": end_time})
    await _ask_role(message, state)


@router.callback_query(F.data == "skip_schedule")
async def skip_schedule(callback: CallbackQuery, state: FSMContext):
    await _ask_role(callback.message, state)


@router.callback_query(EditEmployeeState.waiting_role, F.data.startswith("set_role:"))
async def set_employee_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[-1]
    if role in {"manager", "employee"}:
        await _store_change(state, "role", role)
    await _apply_changes_and_finish(callback.message, state)
    await callback.answer()


def _format_change(key: str, value) -> str:
    if key == "role":
        value = texts.ROLE_MANAGER_VALUE if value == "manager" else texts.ROLE_EMPLOYEE_VALUE
    return texts.ADMIN_CHANGE_ITEM.format(label=_CHANGE_LABELS.get(key, key), value=value) + "\n"


async def _apply_changes_and_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_ids = data.get("user_ids", [])
    changes = data.get("changes", {})
    schedule = data.get("schedule")

    if not changes and not schedule:
        await message.answer(texts.NO_CHANGES, reply_markup=back_to_main_menu(True))
        await state.clear()
        return

    result_text = texts.CHANGES_APPLIED
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if not user:
            continue

        if changes:
            await update_user(user_id, changes)

        if schedule:
            await apply_user_schedule([user_id], schedule["days"], schedule["start_time"], schedule["end_time"])
            await notify_employee_schedule_changed(
                message.bot, user_id, schedule["days"], schedule["start_time"], schedule["end_time"]
            )

        result_text += texts.APPLY_CHANGES_RESULT_NAME.format(name=display_name(user))
        for key, value in changes.items():
            result_text += _format_change(key, value)
        if schedule:
            result_text += texts.ADMIN_SCHEDULE_ITEM.format(
                label=texts.CHANGE_LABEL_SCHEDULE,
                days=format_days(schedule["days"]),
                start=schedule["start_time"],
                end=schedule["end_time"],
            ) + "\n"
        result_text += "\n"

    await message.answer(result_text, reply_markup=back_to_main_menu(True))
    await state.clear()
