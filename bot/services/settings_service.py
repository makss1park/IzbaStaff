from __future__ import annotations

from bot.config import settings
from core.clock import now_naive
from core.repositories import settings as settings_repo


def parse_id_list(raw: str | None) -> list[int]:
    """Разбирает «1, 2,3» в отсортированный список уникальных id, пропуская мусор."""
    if not raw:
        return []
    result: set[int] = set()
    for item in str(raw).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            continue
    return sorted(result)


def _format_id_list(user_ids: list[int]) -> str:
    return ",".join(str(int(user_id)) for user_id in sorted(set(user_ids)))


async def get_latest_reports_days() -> int:
    value = await settings_repo.get_value(settings_repo.LATEST_REPORTS_DAYS)
    if value is None:
        return settings.default_reports_days
    return int(value)


async def set_latest_reports_days(days: int) -> None:
    await settings_repo.set_value(settings_repo.LATEST_REPORTS_DAYS, str(days), now_naive())


async def get_new_report_recipient_ids() -> list[int]:
    return parse_id_list(await settings_repo.get_value(settings_repo.NEW_REPORT_RECIPIENT_IDS))


async def set_new_report_recipient_ids(user_ids: list[int]) -> None:
    await settings_repo.set_value(settings_repo.NEW_REPORT_RECIPIENT_IDS, _format_id_list(user_ids), now_naive())


async def get_shift_event_recipient_ids() -> list[int]:
    return parse_id_list(await settings_repo.get_value(settings_repo.SHIFT_EVENT_RECIPIENT_IDS))


async def set_shift_event_recipient_ids(user_ids: list[int]) -> None:
    await settings_repo.set_value(settings_repo.SHIFT_EVENT_RECIPIENT_IDS, _format_id_list(user_ids), now_naive())


async def get_fine_grantee_ids() -> list[int]:
    """Сотрудники (не админы), которым выдан доступ к назначению штрафов."""
    return parse_id_list(await settings_repo.get_value(settings_repo.FINE_GRANTEE_IDS))


async def set_fine_grantee_ids(user_ids: list[int]) -> None:
    await settings_repo.set_value(settings_repo.FINE_GRANTEE_IDS, _format_id_list(user_ids), now_naive())
