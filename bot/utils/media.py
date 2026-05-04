from __future__ import annotations

from pathlib import Path

from bot import texts

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
_ASSET_SUFFIXES = ("", ".jpg", ".jpeg", ".png", ".webp")

_ASSET_FILE_ID_CACHE: dict[str, str] = {}


def resolve_asset_path(asset_name: str) -> Path | None:
    for suffix in _ASSET_SUFFIXES:
        candidate = ASSETS_DIR / f"{asset_name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _cache_key(asset_path: Path) -> str:
    return str(asset_path.resolve())


def _get_cached_file_id(asset_path: Path) -> str | None:
    return _ASSET_FILE_ID_CACHE.get(_cache_key(asset_path))


def _save_cached_file_id(asset_path: Path, file_id: str) -> None:
    _ASSET_FILE_ID_CACHE[_cache_key(asset_path)] = file_id


async def send_photo_screen(
    message: Message,
    asset_name: str,
    caption: str = "",
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message:
    asset_path = resolve_asset_path(asset_name)
    fallback_text = caption if caption else texts.ZERO_WIDTH_PLACEHOLDER

    if asset_path is None:
        return await message.answer(fallback_text, reply_markup=reply_markup, parse_mode=parse_mode)

    kwargs = {
        "reply_markup": reply_markup,
    }

    if caption:
        kwargs["caption"] = caption
    if parse_mode and caption:
        kwargs["parse_mode"] = parse_mode

    cached_file_id = _get_cached_file_id(asset_path)
    if cached_file_id:
        sent_message = await message.answer_photo(photo=cached_file_id, **kwargs)
        return sent_message

    sent_message = await message.answer_photo(photo=FSInputFile(asset_path), **kwargs)

    if sent_message.photo:
        largest_photo = sent_message.photo[-1]
        if getattr(largest_photo, "file_id", None):
            _save_cached_file_id(asset_path, largest_photo.file_id)

    return sent_message


async def open_photo_screen_from_callback(
    callback: CallbackQuery,
    asset_name: str,
    caption: str = "",
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message | None:
    message = callback.message
    if message is None:
        await callback.answer()
        return None

    try:
        await message.delete()
    except Exception:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    return await send_photo_screen(
        message=message,
        asset_name=asset_name,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )