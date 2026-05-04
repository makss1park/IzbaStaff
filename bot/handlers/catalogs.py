from __future__ import annotations

import asyncio
import html
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.keyboards.inline import catalog_menu_keyboard, main_menu_admin, main_menu_employee
from bot.services.catalogs import add_catalog_photo, create_catalog, get_catalog_by_id, search_catalogs
from bot.states import CatalogCreateState
from bot.ui.navigation import back_to_main_menu
from bot.utils.catalog_storage import build_public_catalog_url, save_telegram_catalog_photo
from bot.utils.media import open_photo_screen_from_callback, send_photo_screen
from bot.utils.telegram import edit_or_send


router = Router()

_album_tasks: dict[tuple[int, int, str], asyncio.Task] = {}


def _is_admin(db_user: dict | None) -> bool:
    return (db_user or {}).get('role') == 'admin'


def _catalog_info_text(item: dict) -> str:
    author = item.get('full_name') or item.get('username') or texts.EMPLOYEE_FALLBACK
    created_at = item.get('created_at')
    created_text = created_at.strftime('%d.%m.%Y %H:%M') if created_at else texts.NO_DATE
    tags = item.get('tags_text') or texts.DASH
    photos_count = item.get('photos_count') or 0
    return texts.CATALOG_INFO_TEMPLATE.format(
        title=html.escape(item.get('title') or texts.NO_DESCRIPTION),
        author=html.escape(author),
        created_at=created_text,
        tags=html.escape(tags),
        photos_count=photos_count,
    )




def _catalog_preview_url(item: dict) -> str:
    """Return an absolute thumbnail URL for Telegram inline results.

    New catalog photos store photo_public_url. Older rows may only have
    photo_local_path, so we rebuild the public URL from the first local file.
    Telegram thumbnails must be available by http/https URL.
    """
    public_url = str(item.get('preview_public_url') or '').strip()
    if public_url.startswith(('http://', 'https://')):
        return public_url

    local_path = str(item.get('preview_local_path') or '').strip()
    if local_path:
        rebuilt_url = build_public_catalog_url(local_path.rsplit('/', 1)[-1])
        if rebuilt_url.startswith(('http://', 'https://')):
            return rebuilt_url

    return 'https://placehold.co/200x200?text=Catalog'

def _catalog_inline_description(item: dict) -> str:
    author = item.get('full_name') or item.get('username') or texts.EMPLOYEE_FALLBACK
    created_at = item.get('created_at')
    created_text = created_at.strftime('%d.%m.%Y') if created_at else texts.NO_DATE
    tags = item.get('tags_text') or texts.DASH
    return texts.CATALOG_INLINE_DESCRIPTION.format(author=author, created_at=created_text, tags=tags)


async def _open_catalog_screen(message: Message, catalog_id: int, is_admin: bool) -> None:
    catalog = await get_catalog_by_id(catalog_id)
    if not catalog:
        await message.answer(texts.CATALOG_NOT_FOUND, reply_markup=back_to_main_menu(is_admin))
        return

    photos = catalog.get('photos') or []
    media = []
    for photo in photos[:10]:
        file_id = photo.get('photo_file_id')
        if file_id:
            media.append(InputMediaPhoto(media=file_id))

    if media:
        if len(media) == 1:
            await message.answer_photo(media[0].media)
        else:
            await message.answer_media_group(media)

    await message.answer(
        _catalog_info_text(catalog),
        reply_markup=back_to_main_menu(is_admin),
        parse_mode='HTML',
    )


@router.message(F.text == texts.MENU_CATALOG)
async def catalog_menu_entry(message: Message, db_user: dict, state: FSMContext) -> None:
    await state.clear()
    await send_photo_screen(
        message,
        asset_name='catalog',
        caption=texts.CATALOG_SCREEN_TITLE,
        reply_markup=catalog_menu_keyboard(_is_admin(db_user)),
    )


@router.callback_query(F.data == 'menu:catalog')
async def catalog_menu_callback(callback: CallbackQuery, db_user: dict, state: FSMContext) -> None:
    await state.clear()
    await open_photo_screen_from_callback(
        callback,
        asset_name='catalog',
        caption=texts.CATALOG_SCREEN_TITLE,
        reply_markup=catalog_menu_keyboard(_is_admin(db_user)),
    )
    await callback.answer()


@router.callback_query(F.data == 'catalog:create')
async def catalog_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CatalogCreateState.waiting_title)
    await edit_or_send(callback, texts.CATALOG_ENTER_TITLE, reply_markup=None)
    await callback.answer()


@router.message(CatalogCreateState.waiting_title)
async def catalog_receive_title(message: Message, state: FSMContext) -> None:
    title = (message.text or '').strip()
    if not title:
        await message.answer(texts.CATALOG_ENTER_TITLE)
        return
    await state.update_data(catalog_title=title)
    await state.set_state(CatalogCreateState.waiting_tags)
    await message.answer(texts.CATALOG_ENTER_TAGS)


@router.message(CatalogCreateState.waiting_tags)
async def catalog_receive_tags(message: Message, state: FSMContext) -> None:
    tags_text = (message.text or '').strip()
    await state.update_data(catalog_tags=tags_text, catalog_photo_ids=[])
    await state.set_state(CatalogCreateState.waiting_photos)
    await message.answer(texts.CATALOG_UPLOAD_PHOTOS, reply_markup=_save_catalog_keyboard())


async def _send_album_added_message(message: Message, state: FSMContext, key: tuple[int, int, str]) -> None:
    try:
        await asyncio.sleep(0.8)
        data = await state.get_data()
        photo_ids = list(data.get('catalog_photo_ids') or [])
        await message.answer(
            texts.CATALOG_PHOTO_ADDED.format(count=len(photo_ids)),
            reply_markup=_save_catalog_keyboard(),
        )
    finally:
        _album_tasks.pop(key, None)


@router.message(CatalogCreateState.waiting_photos, F.photo)
async def catalog_receive_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photo_ids = list(data.get('catalog_photo_ids') or [])
    photo = message.photo[-1]
    photo_ids.append(photo.file_id)
    await state.update_data(catalog_photo_ids=photo_ids)

    media_group_id = message.media_group_id
    if media_group_id:
        key = (message.chat.id, message.from_user.id if message.from_user else 0, media_group_id)
        existing = _album_tasks.get(key)
        if existing and not existing.done():
            existing.cancel()
        _album_tasks[key] = asyncio.create_task(_send_album_added_message(message, state, key))
        return

    await message.answer(
        texts.CATALOG_PHOTO_ADDED.format(count=len(photo_ids)),
        reply_markup=_save_catalog_keyboard(),
    )


@router.message(CatalogCreateState.waiting_photos)
async def catalog_receive_photo_invalid(message: Message) -> None:
    await message.answer(texts.CATALOG_PHOTO_REQUIRED, reply_markup=_save_catalog_keyboard())


@router.callback_query(F.data == 'catalog:save')
async def catalog_save(callback: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    data = await state.get_data()
    title = (data.get('catalog_title') or '').strip()
    tags = (data.get('catalog_tags') or '').strip()
    photo_ids = list(data.get('catalog_photo_ids') or [])

    if not title:
        await callback.answer(texts.CATALOG_ENTER_TITLE, show_alert=True)
        return
    if not photo_ids:
        await callback.answer(texts.CATALOG_SAVE_NEEDS_PHOTOS, show_alert=True)
        return

    catalog_id = await create_catalog(db_user['id'], title, tags)
    for file_id in photo_ids:
        local_path, public_url = await save_telegram_catalog_photo(callback.bot, file_id)
        await add_catalog_photo(catalog_id, file_id, photo_public_url=public_url, photo_local_path=local_path)

    await state.clear()
    await edit_or_send(
        callback,
        texts.CATALOG_SAVED.format(title=title, count=len(photo_ids)),
        reply_markup=back_to_main_menu(_is_admin(db_user)),
    )
    await callback.answer()


@router.callback_query(F.data == 'catalog:list')
async def catalog_list_prompt(callback: CallbackQuery) -> None:
    await callback.answer()


@router.inline_query(F.query.regexp(r'^(#catalogs|catalogs)'))
async def catalogs_inline_dispatcher(query: InlineQuery) -> None:
    raw_q = (query.query or '').strip()
    lower_q = raw_q.lower()

    if lower_q.startswith('#catalogs') or lower_q.startswith('catalogs'):
        search_q = raw_q.split(' ', 1)[1].strip() if ' ' in raw_q else ''
        items = await search_catalogs(text_query=search_q, limit=50)
        results = []
        for item in items:
            title = (item.get('title') or texts.NO_DESCRIPTION).strip()
            if len(title) > 60:
                title = title[:57] + '...'
            preview_url = _catalog_preview_url(item)
            results.append(
                InlineQueryResultArticle(
                    id=f"catalog_{item['id']}",
                    title=title,
                    description=_catalog_inline_description(item),
                    input_message_content=InputTextMessageContent(message_text=f"/catalog_{item['id']}"),
                    thumbnail_url=preview_url,
                )
            )
        await query.answer(results, cache_time=1, is_personal=True, switch_pm_text=texts.INLINE_OPEN_BOT, switch_pm_parameter='start')
        return



@router.message(F.text.regexp(r'^/catalog_(\d+)$'))
async def open_catalog(message: Message, db_user: dict) -> None:
    catalog_id = int(message.text.split('_')[-1])
    await _open_catalog_screen(message, catalog_id, _is_admin(db_user))



def _save_catalog_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_SAVE_CATALOG, callback_data='catalog:save')]]
    )
