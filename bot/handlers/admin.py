from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from bot import texts
from bot.keyboards.inline import (
    confirm_payroll_keyboard,
    employee_actions_keyboard,
    period_info_actions_keyboard,
    shift_admin_actions_keyboard,
    cancel_shift_edit_keyboard,
    employees_selection_keyboard,
    latest_reports_open_keyboard,
    main_menu_admin,
    role_change_keyboard,
    settings_menu,
)
from bot.ui.navigation import back_to_main_menu, with_back_button
from bot.services.fines import create_fine
from bot.services.notifications import (
    notify_employee_rate_changed,
    notify_employee_schedule_changed,
)
from bot.services.payroll import (
    bulk_close_periods,
    get_current_period_fines,
    get_current_period_shift_list,
    get_current_period_stats,
)
from bot.services.reports import get_recent_reports, get_report_by_id
from bot.services.schedules import get_schedules_map, set_schedule as apply_user_schedule
from bot.services.settings_service import (
    get_latest_reports_days,
    get_new_report_recipient_ids,
    get_shift_event_recipient_ids,
    set_latest_reports_days,
    set_new_report_recipient_ids,
    set_shift_event_recipient_ids,
)
from bot.services.shifts import get_active_shifts, get_shift_by_id, delete_shift, update_shift_duration_minutes
from bot.services.users import (
    decorate_users_with_schedule,
    delete_users,
    get_user_by_id,
    list_all_users,
    update_rate,
    update_user,
)
from bot.states import (
    AdminFineState,
    AdminRateState,
    AdminReportRecipientsState,
    AdminScheduleState,
    AdminSettingsState,
    AdminShiftEditState,
    EditEmployeeState
)
from bot.texts import INVALID_AMOUNT, INVALID_DAYS, INVALID_TIME, NOT_ADMIN
from bot.utils.dates import parse_hhmm, seconds_to_human
from bot.utils.formatters import format_period_stats, format_profile
from bot.utils.media import send_photo_screen
from bot.utils.telegram import edit_or_send
from bot.utils.validator import (
    is_valid_full_name,
    is_valid_phone,
    parse_days_list,
    parse_rate,
    parse_schedule_input,
)

router = Router()

def format_days(days: list[int]) -> str:
    mapping = {
        **texts.WEEKDAYS_SHORT_TITLE,
    }
    return ", ".join(mapping.get(day, str(day)) for day in sorted(days))

async def _send_admin_main_menu(message: Message) -> None:
    await send_photo_screen(
        message,
        asset_name="main_menu",
        caption="",
        reply_markup=main_menu_admin(),
    )

def skip_button(action):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_SKIP, callback_data=action)]
        ]
    )


async def ask_employee_role(message: Message, state: FSMContext) -> None:
    await state.set_state(EditEmployeeState.waiting_role)
    await message.answer(texts.ENTER_ROLE, reply_markup=role_change_keyboard())


async def apply_changes_and_finish(message, state):
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

        name = user.get("full_name") or user.get("username") or str(user["tg_id"])

        if changes:
            await update_user(user_id, changes)

        if schedule:
            await apply_user_schedule([user_id], schedule["days"], schedule["start_time"], schedule["end_time"])
            await notify_employee_schedule_changed(
                message.bot,
                user_id,
                schedule["days"],
                schedule["start_time"],
                schedule["end_time"],
            )

        result_text += texts.APPLY_CHANGES_RESULT_NAME.format(name=name)
        for key, value in changes.items():
            labels = {
                "full_name": texts.CHANGE_LABEL_FULL_NAME,
                "phone": texts.CHANGE_LABEL_PHONE,
                "hourly_rate": texts.CHANGE_LABEL_RATE,
                "role": texts.CHANGE_LABEL_ROLE,
            }
            display_value = value
            if key == "role":
                display_value = texts.ROLE_MANAGER_VALUE if value == "manager" else texts.ROLE_EMPLOYEE_VALUE
            result_text += texts.ADMIN_CHANGE_ITEM.format(label=labels.get(key, key), value=display_value) + "\n"

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

def _selected_user_ids(data: dict) -> list[int]:
    return list(sorted(set(data.get("selected_user_ids", []))))

async def _ensure_admin(message_or_callback, is_admin: bool) -> bool:
    if not is_admin:
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.answer(NOT_ADMIN, show_alert=True)
        else:
            await message_or_callback.answer(NOT_ADMIN)
        return False
    return True


def _active_workers_open_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_OPEN_ACTIVE_SHIFTS_LIST,
                    switch_inline_query_current_chat="#active_shifts",
                )
            ]
        ]
    )


def _format_selected_users(users: list[dict], selected_ids: list[int]) -> str:
    selected_map = {user["id"]: user for user in users if user["id"] in set(selected_ids)}
    lines = []
    for user_id in selected_ids:
        user = selected_map.get(user_id)
        if not user:
            continue
        lines.append(texts.ADMIN_LIST_ITEM.format(name=user.get("full_name") or user.get("username") or str(user["tg_id"])))
    return "\n".join(lines)


async def manage_employees(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
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


async def active_workers(message: Message, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return

    items = await get_active_shifts()
    if not items:
        await message.answer(
            texts.ACTIVE_SHIFTS_EMPTY,
            reply_markup=back_to_main_menu(True),
        )
        return

    await send_photo_screen(
        message,
        asset_name="active_employee",
        caption=texts.ACTIVE_SHIFTS_SCREEN,
        reply_markup=with_back_button(_active_workers_open_keyboard(), True),
    )


async def open_settings_menu(message: Message, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    await send_photo_screen(
        message,
        asset_name="settings",
        caption="",
        reply_markup=with_back_button(settings_menu(), True),
    )




# =========================
# ОТЧЕТЫ
# =========================

@router.message(F.text == texts.MENU_LAST_REPORTS)
async def latest_reports(message: Message, is_admin: bool) -> None:
    days = await get_latest_reports_days()
    reports = await get_recent_reports(days)
    if not reports:
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
        return


@router.message(F.text == "/last_reports")
async def latest_reports_command(message: Message, is_admin: bool) -> None:
    days = await get_latest_reports_days()
    reports = await get_recent_reports(days)
    if not reports:
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
        return
    await message.answer(
        texts.REPORTS_SCREEN.format(days=days),
        reply_markup=latest_reports_open_keyboard(),
    )


@router.inline_query()
async def inline_dispatcher(query: InlineQuery, is_admin: bool) -> None:

    raw_q = (query.query or "").strip()
    q = raw_q.lower()

    if q.startswith("#reports") or q.startswith("reports"):
        if q.startswith("#reports"):
            search_q = q.replace("#reports", "", 1).strip()
        else:
            search_q = q.replace("reports", "", 1).strip()

        days = await get_latest_reports_days()
        reports = await get_recent_reports(days)

        if search_q:
            reports = [
                report
                for report in reports
                if search_q in (report.get("description") or "").lower()
                or search_q in (report.get("full_name") or "").lower()
                or search_q in str(report["id"])
            ]

        results = []
        for report in reports[:50]:
            author = report.get("full_name") or report.get("username") or str(report["user_id"])
            title = (report.get("description") or texts.NO_DESCRIPTION).strip()
            if len(title) > 60:
                title = title[:57] + "..."

            description = texts.REPORT_INLINE_DESCRIPTION.format(author=author, created_at=report["created_at"].strftime("%d.%m.%Y %H:%M"))
            preview_url = report.get("photo_public_url") or "https://placehold.co/200x200"

            results.append(
                InlineQueryResultArticle(
                    id=str(report["id"]),
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=f"/report_{report['id']}"
                    ),
                    thumbnail_url=preview_url,
                )
            )

        await query.answer(
            results,
            cache_time=1,
            is_personal=True,
            switch_pm_text=texts.INLINE_OPEN_BOT,
            switch_pm_parameter="start",
        )
        return

    if q.startswith("#active_shifts") or q.startswith("active_shifts"):
        if q.startswith("#active_shifts"):
            search_q = q.replace("#active_shifts", "", 1).strip()
        else:
            search_q = q.replace("active_shifts", "", 1).strip()

        items = await get_active_shifts()

        if search_q:
            items = [
                item
                for item in items
                if search_q in (item.get("full_name") or "").lower()
                or search_q in (item.get("username") or "").lower()
            ]

        results = []
        for index, item in enumerate(items[:50], start=1):
            name = item.get("full_name") or item.get("username") or str(item.get("tg_id", "unknown"))
            opened_at_raw = item.get("opened_at")
            opened_at = opened_at_raw.strftime("%d.%m.%Y %H:%M") if opened_at_raw else texts.UNKNOWN

            text = (
                texts.ADMIN_HTML_USER_PREFIX.format(name=html.escape(name))
                + texts.INLINE_ACTIVE_SHIFT_DESCRIPTION.format(opened_at=opened_at)
            )

            safe_id = item.get("id") or item.get("user_id") or item.get("tg_id") or index

            results.append(
                InlineQueryResultArticle(
                    id=f"active_{safe_id}",
                    title=name,
                    description=texts.INLINE_ACTIVE_SHIFT_DESCRIPTION.format(opened_at=opened_at),
                    input_message_content=InputTextMessageContent(message_text=text),
                )
            )

        await query.answer(
            results,
            cache_time=1,
            is_personal=True,
            switch_pm_text=texts.INLINE_OPEN_BOT,
            switch_pm_parameter="start",
        )
        return

    if q.startswith("#employee_shifts:") or q.startswith("employee_shifts:"):
        prefix = "#employee_shifts:" if q.startswith("#employee_shifts:") else "employee_shifts:"
        tail = raw_q[len(prefix):].strip()
        parts = tail.split(maxsplit=1)
        try:
            user_id = int(parts[0])
        except Exception:
            await query.answer([], cache_time=1, is_personal=True)
            return
        search_q = parts[1].lower().strip() if len(parts) > 1 else ""
        shifts = await get_current_period_shift_list(user_id)
        if search_q:
            shifts = [shift for shift in shifts if search_q in str(shift.get("id")) or search_q in ((shift.get("opened_at").strftime("%d.%m.%Y %H:%M") if shift.get("opened_at") else "").lower())]
        results = []
        for shift in shifts[:50]:
            opened_at_raw = shift.get("opened_at")
            closed_at_raw = shift.get("closed_at")
            opened_at = opened_at_raw.strftime("%d.%m.%Y %H:%M") if opened_at_raw else texts.UNKNOWN
            closed_at = closed_at_raw.strftime("%H:%M") if closed_at_raw else texts.DASH
            duration = seconds_to_human(int(shift.get("duration_seconds", 0) or 0))
            results.append(
                InlineQueryResultArticle(
                    id=f"employee_shift_{shift['id']}",
                    title=f"Смена {opened_at}",
                    description=texts.SHIFT_INLINE_DESCRIPTION.format(opened_at=opened_at, duration=duration),
                    input_message_content=InputTextMessageContent(message_text=f"/admin_shift_{shift['id']}"),
                )
            )
        if not results:
            results.append(
                InlineQueryResultArticle(
                    id="no_employee_shifts",
                    title=texts.NO_SHIFTS_FOR_EDIT,
                    description=texts.NO_SHIFTS_FOR_EDIT,
                    input_message_content=InputTextMessageContent(message_text=texts.NO_SHIFTS_FOR_EDIT),
                )
            )
        await query.answer(results, cache_time=1, is_personal=True, switch_pm_text=texts.INLINE_OPEN_BOT, switch_pm_parameter="start")
        return

    await query.answer([], cache_time=1, is_personal=True)


@router.message(F.text.regexp(r"^/report_(\d+)$"))
async def open_report(message: Message, is_admin: bool) -> None:
    report_id = int(message.text.split("_")[-1])
    report = await get_report_by_id(report_id)
    if not report:
        await message.answer(texts.REPORT_NOT_FOUND, reply_markup=back_to_main_menu(is_admin))
        return

    author = report.get("full_name") or report.get("username") or str(report["user_id"])
    caption = (
        texts.REPORT_CARD.format(id=report["id"], author=author, created_at=report["created_at"].strftime("%d.%m.%Y %H:%M"), description=report.get("description") or texts.NO_DESCRIPTION)
    )

    if report.get("photo_file_id"):
        await message.answer_photo(
            report["photo_file_id"],
            caption=caption,
            reply_markup=back_to_main_menu(is_admin),
        )
    else:
        await message.answer(caption, reply_markup=back_to_main_menu(is_admin))


# =========================
# СОТРУДНИКИ
# =========================

@router.callback_query(F.data.startswith("emp_select:"))
async def employee_select(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(callback, is_admin):
        return

    action = callback.data.split(":")[1]
    data = await state.get_data()
    selected = set(_selected_user_ids(data))
    selection_mode = data.get("selection_mode")

    users = await list_all_users()
    if selection_mode in {"report_recipients", "shift_event_recipients"}:
        users = [user for user in users if user.get("role") in {"employee", "manager"}]
    all_ids = {u["id"] for u in users}
    selected &= all_ids

    if action == "toggle":
        user_id = int(callback.data.split(":")[-1])
        if user_id in selected:
            selected.remove(user_id)
        else:
            selected.add(user_id)
        await state.update_data(selected_user_ids=list(selected))
        await callback.message.edit_reply_markup(
            reply_markup=employees_selection_keyboard(users, selected)
        )

    elif action == "all":
        selected = all_ids
        await state.update_data(selected_user_ids=list(selected))
        await callback.message.edit_reply_markup(
            reply_markup=employees_selection_keyboard(users, selected)
        )

    elif action == "none":
        selected = set()
        await state.update_data(selected_user_ids=[])
        await callback.message.edit_reply_markup(
            reply_markup=employees_selection_keyboard(users, selected)
        )

    elif action == "done":
        selected_ids = list(sorted(selected))
        if selection_mode == "report_recipients":
            await set_new_report_recipient_ids(selected_ids)
            await state.clear()
            if selected_ids:
                selected_text = _format_selected_users(users, selected_ids)
                await edit_or_send(
                    callback,
                    texts.NEW_REPORT_RECIPIENTS_SAVED_INLINE.format(selected_text=selected_text),
                    reply_markup=back_to_main_menu(True),
                )
            else:
                await edit_or_send(
                    callback,
                    texts.NEW_REPORT_RECIPIENTS_CLEARED,
                    reply_markup=back_to_main_menu(True),
                )
            await callback.answer(texts.SAVED)
            return

        if selection_mode == "shift_event_recipients":
            await set_shift_event_recipient_ids(selected_ids)
            await state.clear()
            if selected_ids:
                selected_text = _format_selected_users(users, selected_ids)
                await edit_or_send(
                    callback,
                    texts.SHIFT_EVENT_RECIPIENTS_SAVED_INLINE.format(selected_text=selected_text),
                    reply_markup=back_to_main_menu(True),
                )
            else:
                await edit_or_send(
                    callback,
                    texts.SHIFT_EVENT_RECIPIENTS_CLEARED,
                    reply_markup=back_to_main_menu(True),
                )
            await callback.answer(texts.SAVED)
            return

        if not selected:
            await callback.answer(texts.SELECT_AT_LEAST_ONE, show_alert=True)
            return
        selected_text = _format_selected_users(users, selected_ids)
        await state.update_data(selected_user_ids=selected_ids)
        await edit_or_send(
            callback,
            texts.CHOOSE_ACTION.format(selected_text=selected_text),
            reply_markup=employee_actions_keyboard(),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("emp_action:"))
async def employee_action(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(callback, is_admin):
        return

    code = callback.data.split(":")[-1]
    data = await state.get_data()
    user_ids = _selected_user_ids(data)

    if not user_ids:
        await callback.answer(texts.SELECT_EMPLOYEES_FIRST, show_alert=True)
        return

    if code == "all_info":
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        schedules = await get_schedules_map(user_ids)

        for user_id in user_ids:
            user = await get_user_by_id(user_id)
            if not user:
                continue

            await decorate_users_with_schedule([user], schedules)

            await callback.message.answer(
                format_profile(user),
                reply_markup=back_to_main_menu(True),
                parse_mode="HTML",
            )

    elif code == "period_info":
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        for user_id in user_ids:
            user = await get_user_by_id(user_id)
            if not user:
                continue

            name = user.get("full_name") or user.get("username") or str(user["tg_id"])
            stats = await get_current_period_stats(user_id)
            shifts = await get_current_period_shift_list(user_id)
            fines = await get_current_period_fines(user_id)

            await callback.message.answer(
                texts.PERIOD_INFO_HEADER.format(name=name, stats=format_period_stats(stats, shifts=shifts, fines=fines)),
                reply_markup=period_info_actions_keyboard(user_id),
                parse_mode="HTML",
            )
    elif code == "change_employee_info":
        await state.update_data(
            user_ids=user_ids,
            changes={}
        )

        await state.set_state(EditEmployeeState.waiting_full_name)

        await callback.message.answer(
            texts.ENTER_NEW_FULL_NAME,
            reply_markup=skip_button("skip_full_name")
        )
    elif code == "delete_employee":
        users_to_delete = []
        for user_id in user_ids:
            user = await get_user_by_id(user_id)
            if user and user.get("role") in {"employee", "manager"}:
                users_to_delete.append(user)

        if not users_to_delete:
            await callback.answer(texts.SELECT_AT_LEAST_ONE, show_alert=True)
            return

        selected_text = "\n".join(
            texts.ADMIN_LIST_ITEM.format(
                name=user.get("full_name") or user.get("username") or str(user["tg_id"])
            )
            for user in users_to_delete
        )
        await delete_users([user["id"] for user in users_to_delete])
        await state.clear()
        await edit_or_send(
            callback,
            texts.EMPLOYEES_DELETED.format(selected_text=selected_text),
            reply_markup=back_to_main_menu(True),
        )

    elif code == "fine":
        await state.set_state(AdminFineState.waiting_reason)
        await edit_or_send(callback, texts.ENTER_FINE_REASON)

    elif code == "payroll_close":
        lines = []
        for user_id in user_ids:
            user = await get_user_by_id(user_id)
            if not user:
                continue
            name = user.get("full_name") or user.get("username") or str(user["tg_id"])
            stats = await get_current_period_stats(user_id)
            lines.append(texts.PAYROLL_LINE.format(name=name, amount=stats.get("earned_amount", 0)))
        await edit_or_send(
            callback,
            texts.CONFIRM_PAYROLL_INLINE.format(lines="\n".join(lines)),
            reply_markup=confirm_payroll_keyboard(),
        )

    await callback.answer()

@router.message(EditEmployeeState.waiting_full_name)
async def set_full_name(message: Message, state: FSMContext):
    full_name = " ".join((message.text or "").strip().split())
    if not is_valid_full_name(full_name):
        await message.answer(texts.INVALID_FULL_NAME)
        return

    data = await state.get_data()
    data["changes"]["full_name"] = full_name
    await state.update_data(data)

    await state.set_state(EditEmployeeState.waiting_phone)
    await message.answer(texts.ENTER_PHONE, reply_markup=skip_button("skip_phone"))

@router.callback_query(F.data == "skip_full_name")
async def skip_full_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditEmployeeState.waiting_phone)
    await callback.message.answer(texts.ENTER_PHONE, reply_markup=skip_button("skip_phone"))

@router.message(EditEmployeeState.waiting_phone)
async def set_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not is_valid_phone(phone):
        await message.answer(texts.INVALID_PHONE_EDIT)
        return

    data = await state.get_data()
    data["changes"]["phone"] = phone
    await state.update_data(data)

    await state.set_state(EditEmployeeState.waiting_rate)
    await message.answer(texts.ENTER_RATE, reply_markup=skip_button("skip_rate"))

@router.callback_query(F.data == "skip_phone")
async def skip_phone(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditEmployeeState.waiting_rate)
    await callback.message.answer(texts.ENTER_RATE, reply_markup=skip_button("skip_rate"))

@router.message(EditEmployeeState.waiting_rate)
async def set_rate(message: Message, state: FSMContext):
    try:
        rate = parse_rate(message.text)
    except Exception:
        await message.answer(texts.INVALID_RATE)
        return

    data = await state.get_data()
    data["changes"]["hourly_rate"] = rate
    await state.update_data(data)
    await state.set_state(EditEmployeeState.waiting_schedule)
    await message.answer(
        texts.ENTER_SCHEDULE,
        reply_markup=skip_button("skip_schedule")
    )

@router.callback_query(F.data == "skip_rate")
async def skip_rate(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditEmployeeState.waiting_schedule)
    await callback.message.answer(texts.ENTER_SCHEDULE, reply_markup=skip_button("skip_schedule"))

@router.message(EditEmployeeState.waiting_schedule)
async def set_employee_schedule(message: Message, state: FSMContext):
    try:
        days, start_time, end_time = parse_schedule_input(message.text)
    except Exception:
        await message.answer(
            texts.INVALID_SCHEDULE
        )
        return

    data = await state.get_data()
    data["schedule"] = {
        "days": days,
        "start_time": start_time,
        "end_time": end_time,
    }
    await state.update_data(data)
    await ask_employee_role(message, state)

@router.callback_query(F.data == "skip_schedule")
async def skip_schedule(callback: CallbackQuery, state: FSMContext):
    await ask_employee_role(callback.message, state)


@router.callback_query(EditEmployeeState.waiting_role, F.data.startswith("set_role:"))
async def set_employee_role(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[-1]
    if action in {"manager", "employee"}:
        data = await state.get_data()
        data.setdefault("changes", {})
        data["changes"]["role"] = action
        await state.update_data(data)

    await apply_changes_and_finish(callback.message, state)
    await callback.answer()


@router.message(AdminScheduleState.waiting_days)
async def admin_schedule_days(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    try:
        days = parse_days_list(message.text)
    except Exception:
        await message.answer(INVALID_DAYS)
        return
    await state.update_data(schedule_days=days)
    await state.set_state(AdminScheduleState.waiting_start_time)
    await message.answer(texts.ENTER_SHIFT_START)


@router.message(AdminScheduleState.waiting_start_time)
async def admin_schedule_start(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    try:
        parse_hhmm(message.text)
    except Exception:
        await message.answer(INVALID_TIME)
        return
    await state.update_data(schedule_start=message.text.strip())
    await state.set_state(AdminScheduleState.waiting_end_time)
    await message.answer(texts.ENTER_SHIFT_END)


@router.message(AdminScheduleState.waiting_end_time)
async def admin_schedule_end(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    try:
        end_hour, end_minute = parse_hhmm(message.text)
    except Exception:
        await message.answer(INVALID_TIME)
        return

    data = await state.get_data()
    start_hour, start_minute = parse_hhmm(data["schedule_start"])
    if (end_hour, end_minute) <= (start_hour, start_minute):
        await message.answer(texts.INVALID_END_TIME)
        return

    user_ids = _selected_user_ids(data)
    end_time = message.text.strip()

    await apply_user_schedule(
        user_ids,
        data["schedule_days"],
        data["schedule_start"],
        end_time,
    )

    names = []
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if user:
            names.append(user.get("full_name") or user.get("username") or str(user["tg_id"]))
            await notify_employee_schedule_changed(
                message.bot,
                user_id,
                data["schedule_days"],
                data["schedule_start"],
                end_time,
            )

    await state.clear()
    await state.update_data(selected_user_ids=user_ids)

    await message.answer(
        texts.SCHEDULE_APPLIED.format(
            name="\n".join(texts.ADMIN_LIST_ITEM.format(name=name) for name in names),
            days=format_days(data["schedule_days"]),
            start=data["schedule_start"],
            end=end_time,
        )
    )
    await _send_admin_main_menu(message)


@router.message(AdminRateState.waiting_rate)
async def admin_rate(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    try:
        rate = float(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer(INVALID_AMOUNT)
        return

    data = await state.get_data()
    user_ids = _selected_user_ids(data)

    await update_rate(user_ids, rate)

    names = []
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if user:
            names.append(user.get("full_name") or user.get("username") or str(user["tg_id"]))
            await notify_employee_rate_changed(message.bot, user_id, rate)

    await state.clear()
    await state.update_data(selected_user_ids=user_ids)

    await message.answer(
        texts.RATE_APPLIED.format(
            name="\n".join(texts.ADMIN_LIST_ITEM.format(name=name) for name in names),
            rate=rate,
        )
    )
    await _send_admin_main_menu(message)


@router.message(AdminFineState.waiting_reason)
async def admin_fine_reason(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    await state.update_data(fine_reason=message.text.strip())
    await state.set_state(AdminFineState.waiting_amount)
    await message.answer(texts.ENTER_FINE_AMOUNT)


@router.message(AdminFineState.waiting_amount)
async def admin_fine_amount(message: Message, state: FSMContext, is_admin: bool, db_user: dict) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    try:
        amount = float(message.text.replace(",", ".").strip())
    except Exception:
        await message.answer(INVALID_AMOUNT)
        return

    data = await state.get_data()
    user_ids = _selected_user_ids(data)
    reason = data["fine_reason"]
    names = []

    for user_id in user_ids:
        await create_fine(user_id, amount, reason, db_user["id"])
        user = await get_user_by_id(user_id)
        if user:
            name = user.get("full_name") or user.get("username") or str(user["tg_id"])
            names.append(name)
            try:
                await message.bot.send_message(
                    user["tg_id"],
                    texts.FINE_ASSIGNED_NOTIFICATION.format(reason=reason, amount=amount),
                )
            except Exception:
                pass

    await state.clear()
    await state.update_data(selected_user_ids=user_ids)

    await message.answer(
        texts.FINE_APPLIED.format(
            name="\n".join(texts.ADMIN_LIST_ITEM.format(name=name) for name in names),
            reason=reason,
            amount=amount,
        ),
        reply_markup=back_to_main_menu(True)
    )


@router.callback_query(F.data.startswith("payroll_confirm:"))
async def payroll_confirm(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(callback, is_admin):
        return
    answer = callback.data.split(":")[-1]
    if answer == "no":
        await callback.answer(texts.CANCELLED)
        return

    data = await state.get_data()
    user_ids = _selected_user_ids(data)
    await bulk_close_periods(user_ids)

    names = []
    for user_id in user_ids:
        user = await get_user_by_id(user_id)
        if user:
            names.append(user.get("full_name") or user.get("username") or str(user["tg_id"]))

    await edit_or_send(
        callback,
        texts.PAYROLL_DONE_INLINE.format(names="\n".join(texts.ADMIN_LIST_ITEM.format(name=name) for name in names)),
        reply_markup=back_to_main_menu(True),
    )
    await callback.answer()


# =========================
# ОПОВЕЩЕНИЯ
# =========================

# =========================
# НАСТРОЙКИ
# =========================

@router.message(F.text == texts.MENU_SETTINGS)
async def settings_open(message: Message, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    await open_settings_menu(message, is_admin)


@router.message(F.text == "/settings")
async def settings_open_command(message: Message, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
        return
    await open_settings_menu(message, is_admin)


@router.callback_query(F.data == "settings:reports_days")
async def settings_reports_days(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(callback, is_admin):
        return
    await state.set_state(AdminSettingsState.waiting_reports_days)
    await edit_or_send(callback, texts.REPORT_DAYS_PROMPT)
    await callback.answer()


@router.message(AdminSettingsState.waiting_reports_days)
async def settings_reports_days_save(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
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
    await _send_admin_main_menu(message)

@router.callback_query(F.data == "settings:new_report_recipients")
async def settings_new_report_recipients(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(callback, is_admin):
        return

    users = [user for user in await list_all_users() if user.get("role") in {"employee", "manager"}]
    available_ids = {user["id"] for user in users}
    selected_ids = set(await get_new_report_recipient_ids()) & available_ids

    await state.set_state(AdminReportRecipientsState.selecting_users)
    await state.update_data(
        selection_mode="report_recipients",
        selected_user_ids=list(selected_ids),
    )

    await edit_or_send(
        callback,
        texts.NEW_REPORT_RECIPIENTS_HINT,
        reply_markup=employees_selection_keyboard(users, selected_ids),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:shift_event_recipients")
async def settings_shift_event_recipients(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(callback, is_admin):
        return

    users = [user for user in await list_all_users() if user.get("role") in {"employee", "manager"}]
    available_ids = {user["id"] for user in users}
    selected_ids = set(await get_shift_event_recipient_ids()) & available_ids

    await state.set_state(AdminReportRecipientsState.selecting_users)
    await state.update_data(
        selection_mode="shift_event_recipients",
        selected_user_ids=list(selected_ids),
    )

    await edit_or_send(
        callback,
        texts.SHIFT_EVENT_RECIPIENTS_HINT,
        reply_markup=employees_selection_keyboard(users, selected_ids),
    )
    await callback.answer()


def _format_admin_shift_card(shift: dict) -> str:
    name = shift.get("full_name") or shift.get("username") or str(shift.get("tg_id") or shift.get("user_id"))
    opened_at_raw = shift.get("opened_at")
    closed_at_raw = shift.get("closed_at")
    opened_at = opened_at_raw.strftime("%d.%m.%Y %H:%M") if opened_at_raw else texts.UNKNOWN
    closed_at = closed_at_raw.strftime("%d.%m.%Y %H:%M") if closed_at_raw else texts.DASH
    duration = seconds_to_human(int(shift.get("duration_seconds", 0) or 0))
    late = seconds_to_human(int(shift.get("late_seconds", 0) or 0))
    return texts.ADMIN_SHIFT_CARD.format(
        name=html.escape(name),
        opened_at=opened_at,
        closed_at=closed_at,
        duration=duration,
        late=late,
    )


@router.message(F.text.regexp(r"^/admin_shift_(\d+)$"))
async def open_admin_shift(message: Message, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
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
    if not await _ensure_admin(callback, is_admin):
        return

    parts = callback.data.split(":")
    action = parts[1]

    if action == "cancel_edit":
        await state.clear()
        await edit_or_send(callback, texts.CANCELLED, reply_markup=back_to_main_menu(True))
        await callback.answer(texts.CANCELLED)
        return

    shift_id = int(parts[2])
    shift = await get_shift_by_id(shift_id)
    if not shift:
        await edit_or_send(callback, texts.SHIFT_NOT_FOUND_ADMIN, reply_markup=back_to_main_menu(True))
        await callback.answer()
        return

    if action == "delete":
        await delete_shift(shift_id)
        await edit_or_send(callback, texts.SHIFT_DELETED, reply_markup=back_to_main_menu(True))
        await callback.answer(texts.SAVED)
        return

    if action == "edit":
        await state.set_state(AdminShiftEditState.waiting_minutes)
        await state.update_data(edit_shift_id=shift_id)
        await edit_or_send(callback, texts.ENTER_SHIFT_MINUTES, reply_markup=cancel_shift_edit_keyboard())
        await callback.answer()
        return


@router.message(AdminShiftEditState.waiting_minutes)
async def admin_shift_set_minutes(message: Message, state: FSMContext, is_admin: bool) -> None:
    if not await _ensure_admin(message, is_admin):
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
