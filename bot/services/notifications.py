from __future__ import annotations

import logging
from datetime import date
from typing import Any

from aiogram import Bot

from bot import texts
from bot.database import execute, fetch_all, fetch_one
from bot.services.shifts import get_open_shift
from bot.services.settings_service import get_shift_event_recipient_ids
from bot.services.users import get_admin_users, get_user_by_id, list_all_users
from bot.utils.dates import now_local, seconds_to_human

logger = logging.getLogger(__name__)

__all__ = [
    "notify_admins_about_late",
    "notify_employee_rate_changed",
    "notify_employee_schedule_changed",
    "notify_new_report_recipients",
    "notify_shift_event_recipients",
    "dispatch_schedule_shift_notifications",
]


async def notify_admins_about_late(bot: Bot, user: dict, late_seconds: int) -> None:
    if late_seconds <= 0:
        return

    admins = await get_admin_users()
    late_minutes = late_seconds // 60
    text = (
        texts.LATE_NOTIFICATION.format(employee_name=user.get("full_name") or user.get("username"), late_minutes=late_minutes)
    )

    for admin in admins:
        try:
            await bot.send_message(admin["tg_id"], text)
        except Exception:
            pass


async def notify_employee_rate_changed(bot: Bot, user_id: int, rate: float) -> None:
    user = await get_user_by_id(user_id)
    if not user or not user.get("tg_id"):
        return

    text = texts.RATE_CHANGED_NOTIFICATION.format(rate=rate)

    try:
        await bot.send_message(user["tg_id"], text)
    except Exception as exc:
        logger.warning(
            "Failed to send rate change notification to %s: %s", user["tg_id"], exc
        )


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

    day_names = {
        **texts.WEEKDAYS_SHORT_TITLE,
    }
    days = ", ".join(day_names.get(x, str(x)) for x in sorted(weekdays)) or texts.DASH
    text = (
texts.SCHEDULE_CHANGED_NOTIFICATION.format(days=days, start_time=start_time, end_time=end_time)
    )

    try:
        await bot.send_message(user["tg_id"], text)
    except Exception as exc:
        logger.warning(
            "Failed to send schedule change notification to %s: %s", user["tg_id"], exc
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

    if not recipient_ids:
        return 0

    placeholders = ",".join(["%s"] * len(recipient_ids))
    recipients = await fetch_all(
        f"SELECT tg_id FROM users WHERE is_active=1 AND id IN ({placeholders})",
        tuple(recipient_ids),
    )
    if not recipients:
        return 0

    now = now_local()

    weekday_names = {
        0: "Mon",
        1: "Tue",
        2: "Wed",
        3: "Thu",
        4: "Fri",
        5: "Sat",
        6: "Sun",
    }
    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December",
    }

    report_date = (
        f"{now.strftime('%H:%M')} | "
        f"{weekday_names[now.weekday()]} "
        f"{now.strftime('%d')} "
        f"{month_names[now.month]} "
        f"{now.strftime('%Y')}"
    )

    text = (
        texts.NEW_REPORT_NOTIFICATION.format(author_name=author_name, report_date=report_date, description=description or texts.NO_DESCRIPTION)
    )

    sent = 0
    for user in recipients:
        try:
            await bot.send_message(
                user["tg_id"],
                text,
                parse_mode="HTML",
            )
            sent += 1
        except Exception as exc:
            logger.warning(
                "Failed to send new report notification to %s: %s", user["tg_id"], exc
            )
    return sent


async def notify_shift_event_recipients(
    bot: Bot,
    *,
    user: dict,
    event_type: str,
    event_at,
    duration_seconds: int | None = None,
) -> int:
    recipient_ids = set(await get_shift_event_recipient_ids())
    admin_rows = await fetch_all(
        "SELECT id FROM users WHERE role='admin' AND is_active=1"
    )
    recipient_ids.update(int(row["id"]) for row in admin_rows if row.get("id") is not None)

    if not recipient_ids:
        return 0

    placeholders = ",".join(["%s"] * len(recipient_ids))
    recipients = await fetch_all(
        f"SELECT tg_id FROM users WHERE is_active=1 AND role IN ('admin','employee','manager') AND tg_id IS NOT NULL AND id IN ({placeholders})",
        tuple(sorted(recipient_ids)),
    )
    if not recipients:
        return 0

    employee_name = user.get("full_name") or user.get("username") or str(user.get("tg_id"))
    event_at_text = event_at.strftime("%d.%m.%Y %H:%M")

    if event_type == "open":
        text = (
texts.SHIFT_EVENT_OPEN.format(employee_name=employee_name, event_at_text=event_at_text)
        )
    elif event_type == "close":
        text = (
texts.SHIFT_EVENT_CLOSE.format(employee_name=employee_name, event_at_text=event_at_text)
        )
        if duration_seconds is not None:
            text += texts.SHIFT_EVENT_DURATION.format(duration=seconds_to_human(duration_seconds))
    else:
        raise ValueError(f"Unsupported shift event type: {event_type}")

    sent = 0
    for recipient in recipients:
        try:
            await bot.send_message(recipient["tg_id"], text)
            sent += 1
        except Exception as exc:
            logger.warning(
                "Failed to send shift event notification to %s: %s",
                recipient["tg_id"],
                exc,
            )
    return sent


async def _was_schedule_reminder_sent(user_id: int, reminder_type: str, reminder_date: date) -> bool:
    row = await fetch_one(
        "SELECT id FROM schedule_notification_logs WHERE user_id=%s AND reminder_type=%s AND reminder_date=%s LIMIT 1",
        (user_id, reminder_type, reminder_date),
    )
    return row is not None


async def _mark_schedule_reminder_sent(user_id: int, reminder_type: str, reminder_date: date) -> None:
    now_naive = now_local().replace(tzinfo=None)
    await execute(
        "INSERT INTO schedule_notification_logs (user_id, reminder_type, reminder_date, created_at) VALUES (%s, %s, %s, %s)",
        (user_id, reminder_type, reminder_date, now_naive),
    )


async def dispatch_schedule_shift_notifications(bot: Bot) -> None:
    now = now_local()
    current_time = now.strftime("%H:%M")
    today = now.date()
    iso_weekday = now.isoweekday()

    rows = await fetch_all(
        """
        SELECT
            u.id AS user_id,
            u.tg_id,
            u.full_name,
            s.weekdays_json,
            s.start_time,
            s.end_time
        FROM users u
        JOIN user_schedules s ON s.user_id = u.id AND s.is_active = 1
        WHERE u.is_active = 1 AND u.role = 'employee' AND u.tg_id IS NOT NULL
        """
    )
    if not rows:
        return

    for row in rows:
        try:
            weekdays = row.get("weekdays_json") or "[]"
            if isinstance(weekdays, str):
                import json
                weekdays = json.loads(weekdays)

            if iso_weekday not in weekdays:
                continue

            user_id = row["user_id"]
            tg_id = row["tg_id"]
            full_name = row.get("full_name") or texts.EMPLOYEE_FALLBACK
            open_shift = await get_open_shift(user_id)

            if row.get("start_time") == current_time:
                if open_shift is None and not await _was_schedule_reminder_sent(user_id, "open", today):
                    await bot.send_message(
                        tg_id,
                        (
                            texts.SCHEDULE_OPEN_REMINDER.format(full_name=full_name)
                        ),
                    )
                    await _mark_schedule_reminder_sent(user_id, "open", today)

            if row.get("end_time") == current_time:
                if open_shift is not None and not await _was_schedule_reminder_sent(user_id, "close", today):
                    await bot.send_message(
                        tg_id,
                        (
                            texts.SCHEDULE_CLOSE_REMINDER.format(full_name=full_name)
                        ),
                    )
                    await _mark_schedule_reminder_sent(user_id, "close", today)

        except Exception as exc:
            logger.warning(
                "Failed to process schedule reminder for user %s: %s",
                row.get("user_id"),
                exc,
            )
