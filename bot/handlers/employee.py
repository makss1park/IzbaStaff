from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from bot import texts
from bot.keyboards.inline import graph_menu, profile_menu
from bot.ui.navigation import back_to_main_menu, with_back_button
from bot.services.notifications import notify_admins_about_late, notify_shift_event_recipients
from bot.services.payroll import get_current_period_fines, get_current_period_shift_list, get_current_period_stats
from bot.services.schedules import get_schedules_map
from bot.services.shifts import close_shift, open_shift
from bot.services.users import decorate_users_with_schedule, get_user_by_id
from bot.utils.formatters import (
    format_period_stats,
    format_profile,
    format_shift_closed,
    format_shift_opened,
)
from bot.utils.media import send_photo_screen
from bot.utils.telegram import edit_or_send
from bot.handlers.start import bind_profile_photo, clear_profile_photo

router = Router()


async def _notify_admins_about_late(message: Message | None, db_user: dict, late_seconds: int) -> None:
    if message is None:
        return
    await notify_admins_about_late(message.bot, db_user, late_seconds)


async def _perform_shift_open(message: Message, db_user: dict, **kwargs) -> None:
    shift = await open_shift(db_user["id"], **kwargs)
    dt = shift["opened_at"].strftime("%d.%m.%Y %H:%M")
    late_seconds = int(shift["late_seconds"])

    await message.answer(
        format_shift_opened(dt, late_seconds),
        reply_markup=back_to_main_menu(db_user.get("role") == "admin"),
    )

    await notify_shift_event_recipients(
        message.bot,
        user=db_user,
        event_type="open",
        event_at=shift["opened_at"],
    )
    await _notify_admins_about_late(message, db_user, late_seconds)


async def _perform_shift_close(message: Message, db_user: dict, **kwargs) -> None:
    shift = await close_shift(db_user["id"], **kwargs)
    dt = shift["closed_at"].strftime("%d.%m.%Y %H:%M")

    await message.answer(
        format_shift_closed(dt, int(shift["duration_seconds"])),
        reply_markup=back_to_main_menu(db_user.get("role") == "admin"),
    )

    await notify_shift_event_recipients(
        message.bot,
        user=db_user,
        event_type="close",
        event_at=shift["closed_at"],
        duration_seconds=int(shift["duration_seconds"]),
    )


@router.message(F.text == texts.MENU_GRAPH)
async def graph(message: Message, db_user: dict) -> None:
    if db_user.get("role") == "manager":
        await message.answer(texts.NO_ACCESS, reply_markup=back_to_main_menu(False))
        return
    await send_photo_screen(
        message,
        asset_name="graphic",
        caption="",
        reply_markup=with_back_button(graph_menu(), db_user.get("role") == "admin"),
    )


@router.callback_query(F.data == "shift:open")
async def shift_open(callback: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    if db_user.get("role") == "manager":
        await edit_or_send(callback, texts.NO_ACCESS, reply_markup=back_to_main_menu(False))
        await callback.answer()
        return
    try:
        shift = await open_shift(db_user["id"])
        dt = shift["opened_at"].strftime("%d.%m.%Y %H:%M")
        late_seconds = int(shift["late_seconds"])
        is_admin = db_user.get("role") == "admin"
        await edit_or_send(
            callback,
            format_shift_opened(dt, late_seconds),
            reply_markup=back_to_main_menu(is_admin),
        )
        await notify_shift_event_recipients(
            callback.bot,
            user=db_user,
            event_type="open",
            event_at=shift["opened_at"],
        )
        await _notify_admins_about_late(callback.message, db_user, late_seconds)
    except ValueError as exc:
        is_admin = db_user.get("role") == "admin"
        await edit_or_send(
            callback,
            texts.WARNING_PREFIX.format(message=exc),
            reply_markup=back_to_main_menu(is_admin),
        )
    await callback.answer()


@router.callback_query(F.data == "shift:close")
async def shift_close_request(callback: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    if db_user.get("role") == "manager":
        await edit_or_send(callback, texts.NO_ACCESS, reply_markup=back_to_main_menu(False))
        await callback.answer()
        return
    try:
        shift = await close_shift(db_user["id"])
        dt = shift["closed_at"].strftime("%d.%m.%Y %H:%M")
        is_admin = db_user.get("role") == "admin"
        await edit_or_send(
            callback,
            format_shift_closed(dt, int(shift["duration_seconds"])),
            reply_markup=back_to_main_menu(is_admin),
        )
        await notify_shift_event_recipients(
            callback.bot,
            user=db_user,
            event_type="close",
            event_at=shift["closed_at"],
            duration_seconds=int(shift["duration_seconds"]),
        )
    except ValueError as exc:
        is_admin = db_user.get("role") == "admin"
        await edit_or_send(
            callback,
            texts.WARNING_PREFIX.format(message=exc),
            reply_markup=back_to_main_menu(is_admin),
        )
    await callback.answer()


@router.callback_query(F.data == "shift:my")
async def my_shifts(callback: CallbackQuery, db_user: dict) -> None:
    if db_user.get("role") == "manager":
        await edit_or_send(callback, texts.NO_ACCESS, reply_markup=back_to_main_menu(False))
        await callback.answer()
        return
    stats = await get_current_period_stats(db_user["id"])
    shifts = await get_current_period_shift_list(db_user["id"])
    fines = await get_current_period_fines(db_user["id"])
    text = texts.MY_SHIFTS_TITLE + "\n\n" + format_period_stats(stats, shifts=shifts, fines=fines)
    message = callback.message

    if message is not None and getattr(message, "photo", None):
        try:
            await message.delete()
        except Exception:
            pass
        await callback.message.answer(
            text,
            reply_markup=back_to_main_menu(db_user.get("role") == "admin"),
            parse_mode="HTML",
        )
    else:
        await edit_or_send(
            callback,
            text,
            reply_markup=back_to_main_menu(db_user.get("role") == "admin"),
            parse_mode="HTML",
        )
    await callback.answer()


async def _build_profile_text(db_user: dict) -> str:
    user = await get_user_by_id(db_user["id"])
    stats = await get_current_period_stats(db_user["id"])
    assert user is not None

    schedules = await get_schedules_map([db_user["id"]])
    await decorate_users_with_schedule([user], schedules)
    return format_profile(user, stats)


async def _send_profile(message: Message, db_user: dict, state: FSMContext) -> None:
    await clear_profile_photo(state, message.bot, message.chat.id)
    photo_message = await send_photo_screen(
        message,
        asset_name="personal_account",
        caption="",
    )
    await bind_profile_photo(state, photo_message.message_id if photo_message else None)
    await message.answer(
        await _build_profile_text(db_user),
        reply_markup=with_back_button(profile_menu(), db_user.get("role") == "admin"),
        parse_mode="HTML",
    )


@router.message(F.text == texts.MENU_PROFILE)
async def profile(message: Message, db_user: dict, state: FSMContext) -> None:
    await _send_profile(message, db_user, state)


@router.message(F.text == "/profile")
async def profile_command(message: Message, db_user: dict, state: FSMContext) -> None:
    await _send_profile(message, db_user, state)


@router.message(F.text == "/grafic")
async def graph_command(message: Message, db_user: dict) -> None:
    await send_photo_screen(
        message,
        asset_name="graphic",
        caption="",
        reply_markup=with_back_button(graph_menu(), db_user.get("role") == "admin"),
    )
