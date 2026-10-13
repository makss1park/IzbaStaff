from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.ui.navigation import back_to_main_menu, with_back_button


def _with_fine_button(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    rows = [row[:] for row in keyboard.inline_keyboard]
    rows.append([InlineKeyboardButton(text=texts.BTN_ASSIGN_FINE, callback_data="menu:fine")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_employee() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_PROFILE, callback_data="menu:profile")],
            [InlineKeyboardButton(text=texts.BTN_GRAPH, callback_data="menu:graph")],
            [InlineKeyboardButton(text=texts.BTN_QUICK_REPORT, callback_data="menu:quick_report")],
            [InlineKeyboardButton(text=texts.BTN_LAST_REPORTS, switch_inline_query_current_chat="#reports")],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ACTIVE_SHIFTS,
                    switch_inline_query_current_chat="#active_shifts",
                )
            ]
        ]
    )


def main_menu_manager() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_PROFILE, callback_data="menu:profile")],
            [InlineKeyboardButton(text=texts.BTN_QUICK_REPORT, callback_data="menu:quick_report")],
            [InlineKeyboardButton(text=texts.BTN_LAST_REPORTS, switch_inline_query_current_chat="#reports")],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ACTIVE_SHIFTS,
                    switch_inline_query_current_chat="#active_shifts",
                )
            ],
            [InlineKeyboardButton(text=texts.BTN_CATALOG, callback_data="menu:catalog")]
        ]
    )


def main_menu_for_role(role: str | None, can_assign_fines: bool = False) -> InlineKeyboardMarkup:
    """Главное меню по роли. Админ штрафует через «Управление сотрудниками»; сотрудникам
    с выданным доступом добавляется отдельная кнопка «Назначить штраф»."""
    if role == "admin":
        return main_menu_admin()
    menu = main_menu_manager() if role == "manager" else main_menu_employee()
    return _with_fine_button(menu) if can_assign_fines else menu


def main_menu_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_PROFILE, callback_data="menu:profile")],
            [InlineKeyboardButton(text=texts.BTN_EMPLOYEE_MANAGE, callback_data="menu:employees_manage")],
            [
                InlineKeyboardButton(
                    text=texts.BTN_ACTIVE_SHIFTS,
                    switch_inline_query_current_chat="#active_shifts",
                )
            ],
            [InlineKeyboardButton(text=texts.BTN_SETTINGS, callback_data="menu:settings")],
            [
                InlineKeyboardButton(
                    text=texts.BTN_LAST_REPORTS,
                    switch_inline_query_current_chat="#reports",
                )
            ],
            [InlineKeyboardButton(text=texts.BTN_CATALOG, callback_data="menu:catalog")]
        ]
    )


def graph_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.BTN_SHIFT_OPEN, callback_data="shift:open"),
                InlineKeyboardButton(text=texts.BTN_SHIFT_CLOSE, callback_data="shift:close"),
            ],
            [
                InlineKeyboardButton(text=texts.BTN_MY_SHIFTS, callback_data="shift:my"),
            ],
        ]
    )


def profile_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[])


def confirm_payroll_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.BTN_CONFIRM, callback_data="payroll_confirm:yes"),
                InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="payroll_confirm:no"),
            ]
        ]
    )



def employee_actions_keyboard() -> InlineKeyboardMarkup:
    labels = [
        (texts.BTN_SHOW_ALL_INFO, "all_info"),
        (texts.BTN_SHOW_PERIOD_INFO, "period_info"),
        (texts.BTN_CHANGE_INFO, "change_employee_info"),
        (texts.BTN_DELETE_EMPLOYEE, "delete_employee"),
        (texts.BTN_FINE, "fine"),
        (texts.BTN_RESET_HOURS, "payroll_close")
    ]
    rows = [
        [InlineKeyboardButton(text=text, callback_data=f"emp_action:{code}")]
        for text, code in labels
    ]
    rows.append([InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data="menu:main_admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_change_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_SET_MANAGER_ROLE, callback_data="set_role:manager")],
            [InlineKeyboardButton(text=texts.BTN_SET_EMPLOYEE_ROLE, callback_data="set_role:employee")],
            [InlineKeyboardButton(text=texts.BTN_SKIP, callback_data="set_role:skip")],
        ]
    )


def employees_selection_keyboard(users: list[dict], selected_ids: set[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []

    for user in users:
        mark = "✅" if user["id"] in selected_ids else "⬜"
        title = user.get("full_name") or user.get("username") or str(user["tg_id"])
        current_row.append(
            InlineKeyboardButton(
                text=f"{mark} {title}",
                callback_data=f"emp_select:toggle:{user['id']}",
            )
        )
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.extend(
        [
            [
                InlineKeyboardButton(text=texts.BTN_SELECT_ALL, callback_data="emp_select:all"),
                InlineKeyboardButton(text=texts.BTN_CLEAR_SELECTION, callback_data="emp_select:none"),
            ],
            [InlineKeyboardButton(text=texts.BTN_NEXT, callback_data="emp_select:done")],
            [InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data="menu:main_admin")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grant_access_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_ACCESS_FINES, callback_data="settings:access:fines")],
            [InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data="menu:main_admin")],
        ]
    )


def latest_reports_open_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_OPEN_REPORTS_LIST, switch_inline_query_current_chat="#reports")],
        ]
    )



def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BTN_SET_REPORTS_DAYS,
                    callback_data="settings:reports_days",
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_SET_REPORT_RECIPIENTS,
                    callback_data="settings:new_report_recipients",
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BTN_SET_SHIFT_EVENT_RECIPIENTS,
                    callback_data="settings:shift_event_recipients",
                )
            ],
            [InlineKeyboardButton(text=texts.BTN_GRANT_ACCESS, callback_data="settings:access")]
        ]
    )




def catalog_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_CREATE_CATALOG, callback_data="catalog:create")],
            [InlineKeyboardButton(text=texts.BTN_CATALOG_LIST, switch_inline_query_current_chat="#catalogs")],
            [InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data="menu:main_admin" if is_admin else "menu:main_employee")],
        ]
    )


def period_info_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_EDIT_SHIFT, switch_inline_query_current_chat=f"#employee_shifts:{user_id}")],
            [InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data="menu:main_admin")],
        ]
    )


def shift_admin_actions_keyboard(shift_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_DELETE_SHIFT, callback_data=f"admin_shift:delete:{shift_id}")],
            [InlineKeyboardButton(text=texts.BTN_EDIT_SHIFT_HOURS, callback_data=f"admin_shift:edit:{shift_id}")],
            [InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data="menu:main_admin")],
        ]
    )


def cancel_shift_edit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="admin_shift:cancel_edit")],
        ]
    )
