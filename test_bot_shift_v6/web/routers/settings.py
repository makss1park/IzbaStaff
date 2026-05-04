from __future__ import annotations

from fastapi import APIRouter, Form, Request
from starlette.responses import RedirectResponse

from bot.database import execute, fetch_all
from web.dependencies import require_login, require_role
from web.routers.common import render

router = APIRouter(prefix='/web/settings', tags=['settings'])


@router.get('')
@require_login
async def settings_page(request: Request):
    rows = await fetch_all('SELECT * FROM bot_settings ORDER BY `key` ASC')
    latest = next((row['value'] for row in rows if row['key'] == 'latest_reports_days'), '10')
    recipient_value = next((row['value'] for row in rows if row['key'] == 'new_report_recipient_ids'), '')

    selected_recipient_ids: list[int] = []
    for item in str(recipient_value or '').split(','):
        item = item.strip()
        if not item:
            continue
        try:
            selected_recipient_ids.append(int(item))
        except Exception:
            continue
    selected_recipient_ids = sorted(set(selected_recipient_ids))

    employees = await fetch_all(
        """
        SELECT id, full_name, username, phone, is_active
        FROM users
        WHERE role='employee'
        ORDER BY is_active DESC, COALESCE(full_name, '') ASC, id DESC
        """
    )

    return render(
        request,
        'settings.html',
        {
            'settings_rows': rows,
            'latest_reports_days': latest,
            'employees': employees,
            'selected_recipient_ids': selected_recipient_ids,
        },
    )


@router.post('/save')
@require_role('superadmin', 'manager')
async def settings_save(
    request: Request,
    latest_reports_days: str = Form('10'),
    new_report_recipient_ids: list[str] | None = Form(None),
):
    await execute(
        'INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)',
        ('latest_reports_days', latest_reports_days.strip()),
    )

    normalized_ids: list[int] = []
    for item in new_report_recipient_ids or []:
        try:
            normalized_ids.append(int(str(item).strip()))
        except Exception:
            continue
    normalized_value = ','.join(str(item) for item in sorted(set(normalized_ids)))

    await execute(
        'INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)',
        ('new_report_recipient_ids', normalized_value),
    )
    return RedirectResponse('/web/settings', status_code=303)
