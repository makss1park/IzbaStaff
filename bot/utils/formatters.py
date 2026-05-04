from __future__ import annotations

from bot import texts
from bot.utils.dates import seconds_to_human


def _format_money(value: float | int | None) -> str:
    amount = float(value or 0)
    return f"{amount:.2f}"


def _format_role(role: str | None) -> str:
    role_map = {
        "admin": texts.ROLE_ADMIN,
        "manager": texts.ROLE_MANAGER,
        "employee": texts.ROLE_EMPLOYEE,
    }
    return role_map.get(role or "employee", texts.ROLE_EMPLOYEE)


def _format_schedule(schedule: str | None) -> str:
    if not schedule or schedule == texts.SCHEDULE_NOT_SET:
        return texts.SCHEDULE_NOT_SET

    parts = [part.strip() for part in schedule.split(";") if part.strip()]
    if len(parts) >= 2:
        days_part = parts[0]
        time_part = parts[1].replace("-", " - ")
        return f"{days_part}, {time_part}."

    return schedule.replace("-", " - ")


def format_profile(user: dict, period_stats: dict | None = None) -> str:
    schedule = _format_schedule(user.get("schedule_display") or user.get("work_schedule") or user.get("schedule"))
    text = [
        texts.PROFILE_TITLE,
        texts.PROFILE_FULL_NAME.format(full_name=user.get('full_name') or texts.NOT_SPECIFIED_FEM),
        texts.PROFILE_PHONE.format(phone=user.get('phone') or texts.NOT_SPECIFIED_MASC),
        texts.PROFILE_ROLE.format(role=_format_role(user.get('role'))),
        texts.PROFILE_SCHEDULE.format(schedule=schedule),
        texts.PROFILE_RATE.format(rate=_format_money(user.get('hourly_rate', user.get('rate', 0)))),
    ]
    return "\n".join(text)


def format_period_stats(stats: dict, shifts: list[dict] | None = None, fines: list[dict] | None = None) -> str:
    lines = [
        texts.PERIOD_TITLE,
        texts.PERIOD_SHIFT_COUNT.format(count=stats.get('shift_count', 0)),
        texts.PERIOD_WORK_TIME.format(work_time=seconds_to_human(int(stats.get('work_seconds', 0) or 0))),
        texts.PERIOD_FINE_AMOUNT.format(amount=stats.get('fine_amount', 0)),
        texts.PERIOD_EARNED_AMOUNT.format(amount=stats.get('earned_amount', 0)),
    ]

    lines.append("")
    lines.append(texts.SHIFT_LIST_TITLE)
    if shifts:
        for shift in shifts:
            opened_at = shift.get('opened_at')
            closed_at = shift.get('closed_at')
            opened_text = opened_at.strftime('%d.%m.%Y %H:%M') if opened_at else texts.UNKNOWN
            closed_text = closed_at.strftime('%H:%M') if closed_at else texts.DASH
            duration = seconds_to_human(int(shift.get('duration_seconds', 0) or 0))
            lines.append(texts.SHIFT_ITEM.format(opened_text=opened_text, closed_text=closed_text, duration=duration))
    else:
        lines.append(texts.NO_SHIFTS_IN_PERIOD)

    lines.append("")
    lines.append(texts.FINES_TITLE)
    if fines:
        for fine in fines:
            amount = float(fine.get('amount', 0) or 0)
            reason = fine.get('reason') or texts.NO_DESCRIPTION
            created_at = fine.get('created_at')
            created_text = created_at.strftime('%d.%m.%Y') if created_at else texts.NO_DATE
            lines.append(texts.FINE_ITEM.format(created_text=created_text, amount=amount, reason=reason))
    else:
        lines.append(texts.NO_FINES_IN_PERIOD)

    return "\n".join(lines)


def format_shift_opened(opened_at: str, late_seconds: int = 0) -> str:
    msg = [texts.SHIFT_OPENED, texts.SHIFT_OPENED_AT.format(opened_at=opened_at)]
    if late_seconds > 0:
        msg.append(texts.SHIFT_LATE_LINE.format(late=seconds_to_human(late_seconds)))
    return "\n".join(msg)


def format_shift_closed(closed_at: str, duration_seconds: int) -> str:
    return "\n".join([
        texts.SHIFT_CLOSED,
        texts.SHIFT_CLOSED_AT.format(closed_at=closed_at),
        texts.SHIFT_DURATION.format(duration=seconds_to_human(duration_seconds)),
    ])
