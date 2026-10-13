"""Inline-режим админа: поиск отчётов, активных смен и смен сотрудника.

Запросы вида ``#reports <поиск>``, ``#active_shifts <поиск>`` и
``#employee_shifts:<user_id> <поиск>`` (решётка необязательна).
"""
from __future__ import annotations

import html

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent

from bot import texts
from bot.services.payroll import get_current_period_shift_list
from bot.services.reports import get_recent_reports
from bot.services.settings_service import get_latest_reports_days
from bot.services.shifts import get_active_shifts
from bot.utils.dates import seconds_to_human

router = Router(name="admin.inline")

MAX_RESULTS = 50
_PLACEHOLDER_THUMB = "https://placehold.co/200x200"


def _strip_command(q: str, command: str) -> str | None:
    """Если запрос начинается с ``#command`` или ``command`` — вернуть остаток, иначе None."""
    for prefix in (f"#{command}", command):
        if q.startswith(prefix):
            return q.replace(prefix, "", 1).strip()
    return None


def _fmt_dt(value, fmt: str = "%d.%m.%Y %H:%M", default: str = texts.UNKNOWN) -> str:
    return value.strftime(fmt) if value else default


async def _answer(query: InlineQuery, results: list) -> None:
    await query.answer(
        results,
        cache_time=1,
        is_personal=True,
        switch_pm_text=texts.INLINE_OPEN_BOT,
        switch_pm_parameter="start",
    )


async def _reports_results(search_q: str) -> list[InlineQueryResultArticle]:
    reports = await get_recent_reports(await get_latest_reports_days())
    if search_q:
        reports = [
            report
            for report in reports
            if search_q in (report.get("description") or "").lower()
            or search_q in (report.get("full_name") or "").lower()
            or search_q in str(report["id"])
        ]

    results = []
    for report in reports[:MAX_RESULTS]:
        author = report.get("full_name") or report.get("username") or str(report["user_id"])
        title = (report.get("description") or texts.NO_DESCRIPTION).strip()
        if len(title) > 60:
            title = title[:57] + "..."
        results.append(
            InlineQueryResultArticle(
                id=str(report["id"]),
                title=title,
                description=texts.REPORT_INLINE_DESCRIPTION.format(
                    author=author, created_at=report["created_at"].strftime("%d.%m.%Y %H:%M")
                ),
                input_message_content=InputTextMessageContent(message_text=f"/report_{report['id']}"),
                thumbnail_url=report.get("photo_public_url") or _PLACEHOLDER_THUMB,
            )
        )
    return results


async def _active_shifts_results(search_q: str) -> list[InlineQueryResultArticle]:
    items = await get_active_shifts()
    if search_q:
        items = [
            item
            for item in items
            if search_q in (item.get("full_name") or "").lower()
            or search_q in (item.get("username") or "").lower()
        ]

    results = []
    for index, item in enumerate(items[:MAX_RESULTS], start=1):
        name = item.get("full_name") or item.get("username") or str(item.get("tg_id", "unknown"))
        description = texts.INLINE_ACTIVE_SHIFT_DESCRIPTION.format(opened_at=_fmt_dt(item.get("opened_at")))
        safe_id = item.get("id") or item.get("user_id") or item.get("tg_id") or index
        results.append(
            InlineQueryResultArticle(
                id=f"active_{safe_id}",
                title=name,
                description=description,
                input_message_content=InputTextMessageContent(
                    message_text=texts.ADMIN_HTML_USER_PREFIX.format(name=html.escape(name)) + description
                ),
            )
        )
    return results


async def _employee_shifts_results(user_id: int, search_q: str) -> list[InlineQueryResultArticle]:
    shifts = await get_current_period_shift_list(user_id)
    if search_q:
        shifts = [
            shift
            for shift in shifts
            if search_q in str(shift.get("id"))
            or search_q in _fmt_dt(shift.get("opened_at"), default="").lower()
        ]

    results = []
    for shift in shifts[:MAX_RESULTS]:
        opened_at = _fmt_dt(shift.get("opened_at"))
        duration = seconds_to_human(int(shift.get("duration_seconds", 0) or 0))
        results.append(
            InlineQueryResultArticle(
                id=f"employee_shift_{shift['id']}",
                title=f"Смена {opened_at}",
                description=texts.SHIFT_INLINE_DESCRIPTION.format(opened_at=opened_at, duration=duration),
                input_message_content=InputTextMessageContent(message_text=f"/admin_shift_{shift['id']}"),
            )
        )
    if not results:
        results.append(
            InlineQueryResultArticle(
                id="no_employee_shifts",
                title=texts.NO_SHIFTS_FOR_EDIT,
                description=texts.NO_SHIFTS_FOR_EDIT,
                input_message_content=InputTextMessageContent(message_text=texts.NO_SHIFTS_FOR_EDIT),
            )
        )
    return results


@router.inline_query()
async def inline_dispatcher(query: InlineQuery, is_admin: bool) -> None:
    raw_q = (query.query or "").strip()
    q = raw_q.lower()

    search_q = _strip_command(q, "reports")
    if search_q is not None:
        await _answer(query, await _reports_results(search_q))
        return

    search_q = _strip_command(q, "active_shifts")
    if search_q is not None:
        await _answer(query, await _active_shifts_results(search_q))
        return

    for prefix in ("#employee_shifts:", "employee_shifts:"):
        if q.startswith(prefix):
            parts = raw_q[len(prefix):].strip().split(maxsplit=1)
            try:
                user_id = int(parts[0])
            except (IndexError, ValueError):
                await query.answer([], cache_time=1, is_personal=True)
                return
            search_q = parts[1].lower().strip() if len(parts) > 1 else ""
            await _answer(query, await _employee_shifts_results(user_id, search_q))
            return

    await query.answer([], cache_time=1, is_personal=True)
