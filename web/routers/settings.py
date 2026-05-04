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

    return render(
        request,
        'settings.html',
        {
            'settings_rows': rows,
            'latest_reports_days': latest,
        },
    )


@router.post('/save')
@require_role('superadmin', 'manager')
async def settings_save(
    request: Request,
    latest_reports_days: str = Form('10'),
):
    await execute(
        'INSERT INTO bot_settings (`key`, `value`, updated_at) VALUES (%s, %s, NOW()) ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)',
        ('latest_reports_days', latest_reports_days.strip()),
    )
    return RedirectResponse('/web/settings', status_code=303)
