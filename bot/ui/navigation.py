from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts


def main_menu_callback_data(is_admin: bool) -> str:
    return "menu:main_admin" if is_admin else "menu:main_employee"


def back_to_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data=main_menu_callback_data(is_admin))]]
    )


def with_back_button(keyboard: InlineKeyboardMarkup, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [row[:] for row in keyboard.inline_keyboard]
    rows.append([InlineKeyboardButton(text=texts.BTN_MAIN_MENU, callback_data=main_menu_callback_data(is_admin))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
