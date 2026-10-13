from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from bot import texts

from bot.commands import apply_commands_for_chat
from bot.keyboards.inline import (
    employees_selection_keyboard,
    graph_menu,
    latest_reports_open_keyboard,
    main_menu_admin,
    main_menu_employee,
    main_menu_for_role,
    profile_menu,
    settings_menu,
    with_back_button,
)
from bot.services.payroll import get_current_period_stats
from bot.services.reports import get_recent_reports
from bot.services.schedules import get_schedules_map
from bot.services.settings_service import get_latest_reports_days
from bot.services.users import decorate_users_with_schedule, get_user_by_id, list_all_users
from bot.utils.formatters import format_profile
from bot.utils.media import open_photo_screen_from_callback, send_photo_screen

router = Router()
_PROFILE_PHOTO_KEY = "profile_photo_message_id"


async def _delete_profile_photo_by_id(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def clear_profile_photo(state: FSMContext, bot, chat_id: int) -> None:
    data = await state.get_data()
    photo_message_id = data.get(_PROFILE_PHOTO_KEY)
    await _delete_profile_photo_by_id(bot, chat_id, photo_message_id)
    if photo_message_id:
        await state.update_data(**{_PROFILE_PHOTO_KEY: None})


async def bind_profile_photo(state: FSMContext, photo_message_id: int | None) -> None:
    await state.update_data(**{_PROFILE_PHOTO_KEY: photo_message_id})


async def send_main_menu(message: Message, is_admin: bool, state: FSMContext | None = None, db_user: dict | None = None) -> None:
    role = (db_user or {}).get("role") or ("admin" if is_admin else "employee")
    await apply_commands_for_chat(message.bot, message.chat.id, is_admin, role=role)
    if state is not None:
        await clear_profile_photo(state, message.bot, message.chat.id)

    await message.answer(texts.ZERO_WIDTH_PLACEHOLDER, reply_markup=ReplyKeyboardRemove())
    await send_photo_screen(
        message,
        asset_name="main_menu",
        reply_markup=main_menu_for_role(role),
    )


async def send_main_menu_callback(callback: CallbackQuery, is_admin: bool, state: FSMContext, db_user: dict | None = None) -> None:
    role = (db_user or {}).get("role") or ("admin" if is_admin else "employee")
    message = callback.message
    if message is not None:
        await clear_profile_photo(state, callback.bot, message.chat.id)
        await send_photo_screen(
            message,
            asset_name="main_menu",
            caption="",
            reply_markup=main_menu_for_role(role),
        )
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, is_admin: bool, state: FSMContext, db_user: dict) -> None:
    await send_main_menu(message, is_admin, state, db_user)


@router.message(F.text == texts.MENU_TEXT)
async def menu(message: Message, is_admin: bool, state: FSMContext, db_user: dict) -> None:
    await send_main_menu(message, is_admin, state, db_user)


@router.callback_query(F.data == "menu:main_employee")
async def menu_main_employee(callback: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await send_main_menu_callback(callback, is_admin=False, state=state, db_user=db_user)


@router.callback_query(F.data == "menu:main_admin")
async def menu_main_admin(callback: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await send_main_menu_callback(callback, is_admin=True, state=state, db_user=db_user)


@router.callback_query(F.data == "menu:profile")
async def menu_profile(callback: CallbackQuery, db_user: dict, is_admin: bool, state: FSMContext) -> None:
    user = await get_user_by_id(db_user["id"])
    stats = await get_current_period_stats(db_user["id"])
    assert user is not None

    schedules = await get_schedules_map([db_user["id"]])
    await decorate_users_with_schedule([user], schedules)

    if callback.message is not None:
        await clear_profile_photo(state, callback.bot, callback.message.chat.id)
        photo_message = await send_photo_screen(
            callback.message,
            asset_name="personal_account",
            caption="",
        )
        await bind_profile_photo(state, photo_message.message_id if photo_message else None)
        await callback.message.answer(
            format_profile(user, stats),
            reply_markup=with_back_button(profile_menu(), is_admin),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "menu:graph")
async def menu_graph(callback: CallbackQuery, is_admin: bool, state: FSMContext) -> None:
    if callback.message is not None:
        await clear_profile_photo(state, callback.bot, callback.message.chat.id)
        await send_photo_screen(
            callback.message,
            asset_name="graphic",
            caption="",
            reply_markup=with_back_button(graph_menu(), is_admin),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:employees_manage")
async def menu_employees_manage(callback: CallbackQuery, state: FSMContext, is_admin: bool) -> None:
    if not is_admin:
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return

    users = await list_all_users()
    await state.clear()
    await state.update_data(selected_user_ids=[])

    if callback.message is not None:
        await send_photo_screen(
            callback.message,
            asset_name="employee_manage",
            caption=texts.SELECT_EMPLOYEES,
            reply_markup=employees_selection_keyboard(users, set()),
        )
    await callback.answer()




@router.callback_query(F.data == "menu:settings")
async def menu_settings(callback: CallbackQuery, is_admin: bool, state: FSMContext) -> None:
    if not is_admin:
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return

    if callback.message is not None:
        await clear_profile_photo(state, callback.bot, callback.message.chat.id)
        await send_photo_screen(
            callback.message,
            asset_name="settings",
            caption="",
            reply_markup=with_back_button(settings_menu(), True),
        )
    await callback.answer()




@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def _open_plain_text_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup,
) -> None:
    message = callback.message
    if message is None:
        await callback.answer()
        return

    try:
        if getattr(message, "photo", None):
            await message.delete()
            await message.answer(text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data == "menu:last_reports")
async def menu_last_reports(callback: CallbackQuery, is_admin: bool, state: FSMContext) -> None:
    if callback.message is not None:
        await clear_profile_photo(state, callback.bot, callback.message.chat.id)

    days = await get_latest_reports_days()
    reports = await get_recent_reports(days)

    if not reports:
        await _open_plain_text_screen(
            callback,
            texts.REPORTS_EMPTY.format(days=days),
            with_back_button(InlineKeyboardMarkup(inline_keyboard=[]), is_admin),
        )
        await callback.answer()
        return

    await open_photo_screen_from_callback(
        callback,
        asset_name="last_reports",
        caption=texts.REPORTS_SCREEN.format(days=days),
        reply_markup=with_back_button(latest_reports_open_keyboard(), is_admin),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:active_workers")
async def menu_active_workers(callback: CallbackQuery, is_admin: bool, state: FSMContext) -> None:
    if not is_admin:
        await callback.answer(texts.NO_ACCESS, show_alert=True)
        return

    from bot.handlers.admin import active_workers_open_keyboard
    from bot.services.shifts import get_active_shifts

    if callback.message is not None:
        await clear_profile_photo(state, callback.bot, callback.message.chat.id)

    items = await get_active_shifts()
    if not items:
        await _open_plain_text_screen(
            callback,
            texts.ACTIVE_SHIFTS_EMPTY,
            with_back_button(InlineKeyboardMarkup(inline_keyboard=[]), True),
        )
        await callback.answer()
        return

    await open_photo_screen_from_callback(
        callback,
        asset_name="active_employee",
        caption=texts.ACTIVE_SHIFTS_SCREEN,
        reply_markup=with_back_button(active_workers_open_keyboard(), True),
    )
    await callback.answer()