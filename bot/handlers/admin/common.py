"""Общие помощники админских хендлеров."""
from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.keyboards.inline import main_menu_admin
from bot.services.users import display_name
from bot.utils.media import send_photo_screen


def format_days(days: list[int]) -> str:
    return ", ".join(texts.WEEKDAYS_SHORT_TITLE.get(day, str(day)) for day in sorted(days))


def format_names_list(names: list[str]) -> str:
    return "\n".join(texts.ADMIN_LIST_ITEM.format(name=name) for name in names)


def format_selected_users(users: list[dict], selected_ids: list[int]) -> str:
    """Список выбранных сотрудников в порядке selected_ids."""
    by_id = {user["id"]: user for user in users}
    return format_names_list([display_name(by_id[user_id]) for user_id in selected_ids if user_id in by_id])


def selected_user_ids(data: dict) -> list[int]:
    return sorted(set(data.get("selected_user_ids", [])))


async def keep_selection_only(state: FSMContext, user_ids: list[int]) -> None:
    """Сбрасывает сценарий, но оставляет выбранных сотрудников для следующего действия."""
    await state.clear()
    await state.update_data(selected_user_ids=user_ids)


async def ensure_admin(event: Message | CallbackQuery, is_admin: bool) -> bool:
    if is_admin:
        return True
    if isinstance(event, CallbackQuery):
        await event.answer(texts.NOT_ADMIN, show_alert=True)
    else:
        await event.answer(texts.NOT_ADMIN)
    return False


def skip_button(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_SKIP, callback_data=callback_data)]]
    )


def active_workers_open_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=texts.BTN_OPEN_ACTIVE_SHIFTS_LIST,
                switch_inline_query_current_chat="#active_shifts",
            )
        ]]
    )


async def send_admin_main_menu(message: Message) -> None:
    await send_photo_screen(message, asset_name="main_menu", caption="", reply_markup=main_menu_admin())
