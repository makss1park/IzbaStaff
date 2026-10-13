from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot import texts
from bot.keyboards.inline import main_menu_for_role
from bot.services.notifications import notify_new_report_recipients, with_active_admin_ids
from bot.services.permissions import can_assign_fines
from bot.services.reports import create_report
from bot.services.settings_service import get_new_report_recipient_ids
from bot.states import QuickReportState
from bot.texts import ASK_REPORT_PHOTO, ASK_REPORT_TEXT
from bot.utils.media import send_photo_screen
from bot.utils.report_storage import save_telegram_report_photo
from bot.utils.telegram import edit_or_send

router = Router()


@router.message(F.text == texts.MENU_QUICK_REPORT)
async def quick_report(message: Message, state: FSMContext) -> None:
    await state.set_state(QuickReportState.waiting_text)
    await message.answer(ASK_REPORT_TEXT, reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data == "menu:quick_report")
async def quick_report_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(QuickReportState.waiting_text)
    await edit_or_send(callback, ASK_REPORT_TEXT, reply_markup=None)
    await callback.answer()


@router.message(QuickReportState.waiting_text)
async def report_text(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(QuickReportState.waiting_photo)
    await message.answer(ASK_REPORT_PHOTO)


@router.message(QuickReportState.waiting_photo, F.photo)
async def report_photo(message: Message, state: FSMContext, db_user: dict) -> None:
    data = await state.get_data()
    description = data["description"]
    photo = message.photo[-1]

    photo_local_path, photo_public_url = await save_telegram_report_photo(message.bot, photo.file_id)

    report_id = await create_report(
        db_user["id"],
        description,
        photo.file_id,
        photo_public_url=photo_public_url,
        photo_local_path=photo_local_path,
    )

    recipient_ids = await with_active_admin_ids(await get_new_report_recipient_ids())

    author_name = db_user.get("full_name") or db_user.get("username") or str(db_user.get("tg_id"))
    await notify_new_report_recipients(
        message.bot,
        recipient_ids=recipient_ids,
        author_name=author_name,
        description=description,
        photo_file_id=photo.file_id,
        report_id=report_id,
    )

    await state.clear()

    # Больше не показываем картинку отчета обратно в чат
    await message.answer(
        texts.REPORT_SAVED.format(description=description),
        reply_markup=ReplyKeyboardRemove(),
    )

    await send_photo_screen(
        message,
        asset_name="main_menu",
        caption="",
        reply_markup=main_menu_for_role(db_user.get("role"), await can_assign_fines(db_user)),
    )


@router.message(QuickReportState.waiting_photo)
async def report_photo_invalid(message: Message) -> None:
    await message.answer(texts.REPORT_PHOTO_REQUIRED)