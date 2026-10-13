from __future__ import annotations

import json
import logging
from datetime import datetime

from aiogram import Bot

from bot import texts
from bot.services.settings_service import get_shift_event_recipient_ids
from bot.services.shifts import get_open_shift
from bot.services.users import display_name, get_user_by_id
from bot.utils.dates import now_local, seconds_to_human
from core.clock import now_naive
from core.repositories import reminders as reminders_repo
from core.repositories import schedules as schedules_repo
from core.repositories import users as users_repo

logger = logging.getLogger(__name__)

__all__ = [
    "notify_admins_about_late",
    "notify_employee_rate_changed",
    "notify_employee_schedule_changed",
    "notify_new_report_recipients",
    "notify_shift_event_recipients",
    "dispatch_schedule_shift_notifications",
    "with_active_admin_ids",
]

_WEEKDAY_NAMES_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_NAMES_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


async def _send(bot: Bot, chat_id: int, text: str, *, what: str, **kwargs) -> bool:
    """Отправляет сообщение; ошибку (бот заблокирован и т.п.) только логирует."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as exc:
        logger.warning("Failed to send %s notification to %s: %s", what, chat_id, exc)
        return False


async def notify_admins_about_late(bot: Bot, user: dict, late_seconds: int) -> None:
    if late_seconds <= 0:
        return

    text = texts.LATE_NOTIFICATION.format(
        employee_name=display_name(user),
        late_minutes=max(1, late_seconds // 60),
    )
    for admin in await users_repo.list_active_admins():
        await _send(bot, admin["tg_id"], text, what="late")


async def notify_employee_rate_changed(bot: Bot, user_id: int, rate: float) -> None:
    user = await get_user_by_id(user_id)
    if not user or not user.get("tg_id"):
        return
    await _send(bot, user["tg_id"], texts.RATE_CHANGED_NOTIFICATION.format(rate=rate), what="rate change")


async def notify_employee_schedule_changed(
    bot: Bot,
    user_id: int,
    weekdays: list[int],
    start_time: str,
    end_time: str,
) -> None:
    user = await get_user_by_id(user_id)
    if not user or not user.get("tg_id"):
        return

    days = ", ".join(texts.WEEKDAYS_SHORT_TITLE.get(x, str(x)) for x in sorted(weekdays)) or texts.DASH
    text = texts.SCHEDULE_CHANGED_NOTIFICATION.format(days=days, start_time=start_time, end_time=end_time)
    await _send(bot, user["tg_id"], text, what="schedule change")


def _format_report_date(now: datetime) -> str:
    return (
        f"{now.strftime('%H:%M')} | "
        f"{_WEEKDAY_NAMES_EN[now.weekday()]} "
        f"{now.strftime('%d')} "
        f"{_MONTH_NAMES_EN[now.month - 1]} "
        f"{now.strftime('%Y')}"
    )


async def notify_new_report_recipients(
    bot: Bot,
    *,
    recipient_ids: list[int],
    author_name: str,
    description: str,
    photo_file_id: str | None,
    report_id: int,
) -> int:
    del photo_file_id, report_id  # уведомление должно уходить только текстом

    recipients = await users_repo.list_active_tg_ids(recipient_ids)
    if not recipients:
        return 0

    text = texts.NEW_REPORT_NOTIFICATION.format(
        author_name=author_name,
        report_date=_format_report_date(now_local()),
        description=description or texts.NO_DESCRIPTION,
    )

    sent = 0
    for user in recipients:
        if await _send(bot, user["tg_id"], text, what="new report", parse_mode="HTML"):
            sent += 1
    return sent


async def with_active_admin_ids(configured_ids: list[int]) -> list[int]:
    """Получатели из настроек плюс все активные администраторы."""
    return sorted(set(configured_ids) | set(await users_repo.list_active_admin_ids()))


async def notify_shift_event_recipients(
    bot: Bot,
    *,
    user: dict,
    event_type: str,
    event_at,
    duration_seconds: int | None = None,
) -> int:
    recipient_ids = await with_active_admin_ids(await get_shift_event_recipient_ids())
    recipients = await users_repo.list_shift_event_tg_ids(recipient_ids)
    if not recipients:
        return 0

    employee_name = display_name(user)
    event_at_text = event_at.strftime("%d.%m.%Y %H:%M")

    if event_type == "open":
        text = texts.SHIFT_EVENT_OPEN.format(employee_name=employee_name, event_at_text=event_at_text)
    elif event_type == "close":
        text = texts.SHIFT_EVENT_CLOSE.format(employee_name=employee_name, event_at_text=event_at_text)
        if duration_seconds is not None:
            text += texts.SHIFT_EVENT_DURATION.format(duration=seconds_to_human(duration_seconds))
    else:
        raise ValueError(f"Unsupported shift event type: {event_type}")

    sent = 0
    for recipient in recipients:
        if await _send(bot, recipient["tg_id"], text, what="shift event"):
            sent += 1
    return sent


async def _send_schedule_reminder_once(bot: Bot, row: dict, reminder_type: str, today, text: str) -> None:
    if await reminders_repo.was_sent(row["user_id"], reminder_type, today):
        return
    await bot.send_message(row["tg_id"], text)
    await reminders_repo.mark_sent(row["user_id"], reminder_type, today, now_naive())


async def dispatch_schedule_shift_notifications(bot: Bot) -> None:
    """Раз в минуту: напоминает открыть смену в начале графика и закрыть — в конце."""
    now = now_local()
    current_time = now.strftime("%H:%M")
    today = now.date()
    iso_weekday = now.isoweekday()

    for row in await schedules_repo.list_active_employee_schedules():
        try:
            weekdays = row.get("weekdays_json") or "[]"
            if isinstance(weekdays, str):
                weekdays = json.loads(weekdays)
            if iso_weekday not in weekdays:
                continue

            full_name = row.get("full_name") or texts.EMPLOYEE_FALLBACK
            open_shift = await get_open_shift(row["user_id"])

            if row.get("start_time") == current_time and open_shift is None:
                await _send_schedule_reminder_once(
                    bot, row, "open", today, texts.SCHEDULE_OPEN_REMINDER.format(full_name=full_name)
                )

            if row.get("end_time") == current_time and open_shift is not None:
                await _send_schedule_reminder_once(
                    bot, row, "close", today, texts.SCHEDULE_CLOSE_REMINDER.format(full_name=full_name)
                )
        except Exception as exc:
            logger.warning("Failed to process schedule reminder for user %s: %s", row.get("user_id"), exc)
