from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def edit_or_send(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    message = callback.message
    if message is None:
        await callback.answer()
        return

    try:
        if getattr(message, "text", None) is not None:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif getattr(message, "caption", None) is not None:
            await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
