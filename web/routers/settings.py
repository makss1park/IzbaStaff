from __future__ import annotations

from fastapi import APIRouter, Form, Request
from starlette.responses import RedirectResponse

from core.repositories import settings as settings_repo
from web.dependencies import require_login, require_role
from web.routers.common import render

router = APIRouter(prefix='/web/settings', tags=['settings'])


@router.get('')
@require_login
async def settings_page(request: Request):
    rows = await settings_repo.list_all()
    latest = next((row['value'] for row in rows if row['key'] == settings_repo.LATEST_REPORTS_DAYS), '10')
    return render(request, 'settings.html', {'settings_rows': rows, 'latest_reports_days': latest})


@router.post('/save')
@require_role('superadmin', 'manager')
async def settings_save(request: Request, latest_reports_days: str = Form('10')):
    await settings_repo.set_value(settings_repo.LATEST_REPORTS_DAYS, latest_reports_days.strip())
    return RedirectResponse('/web/settings', status_code=303)
