from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot
from fastapi import APIRouter, Query, Request
from starlette.responses import RedirectResponse, Response

from bot.config import settings, BASE_DIR
from web.config import web_settings
from web.dependencies import require_login
from web.routers.common import render
from web.services.employees import get_employee_options, get_selected_employee, parse_employee_id
from web.services.excel import build_workbook
from web.services.query import paginate_query, parse_page
from web.services.report_migration import backfill_report_public_urls, normalize_report_urls

router = APIRouter(prefix='/web/reports', tags=['reports'])
PAGE_SIZE = 12


def _build_report_public_url(filename: str) -> str:
    prefix = web_settings.reports_url_prefix.rstrip('/') or '/reports'
    base = (web_settings.reports_public_base_url or '').rstrip('/')
    relative = f"{prefix}/{filename}"
    if not base:
        return relative

    parsed = urlparse(base)
    if parsed.path.rstrip('/') == prefix:
        return f"{base}/{filename}"
    return f"{base}{relative}"


def _resolve_report_image_url(item: dict) -> str | None:
    local_path = item.get('photo_local_path')
    if local_path:
        file_name = Path(local_path).name
        # Use a /web/* path for the admin preview. This path is served by the
        # same FastAPI app as the admin panel, so it works even if nginx does
        # not separately proxy /reports.
        return f"/web/report-files/{file_name}"

    public_url = item.get('photo_public_url')
    if public_url:
        return public_url

    return None


@router.get('')
@require_login
async def reports_list(
    request: Request,
    page: int = Query(1),
    employee: str = Query(''),
    employee_id: str | None = Query(None),
    employee_label: str = Query(''),
    date_from: str = Query(''),
    date_to: str = Query(''),
    export: str | None = Query(None),
    migrated: int | None = Query(None),
    normalized: int | None = Query(None),
):
    normalized_employee_id = parse_employee_id(employee_id)
    clauses = ['1=1']
    args: list = []
    if normalized_employee_id:
        clauses.append('r.user_id = %s')
        args.append(normalized_employee_id)
    elif employee.strip():
        clauses.append('(u.full_name LIKE %s OR u.username LIKE %s)')
        like = f"%{employee.strip()}%"
        args.extend([like, like])
    if date_from.strip():
        clauses.append('DATE(r.created_at) >= %s')
        args.append(date_from.strip())
    if date_to.strip():
        clauses.append('DATE(r.created_at) <= %s')
        args.append(date_to.strip())
    where_sql = ' AND '.join(clauses)
    base_query = f'''SELECT r.*, u.full_name, u.username FROM reports r JOIN users u ON u.id=r.user_id WHERE {where_sql} ORDER BY r.created_at DESC'''
    count_query = f'''SELECT COUNT(*) AS cnt FROM reports r JOIN users u ON u.id=r.user_id WHERE {where_sql}'''
    data = await paginate_query(base_query, count_query, tuple(args), parse_page(page), PAGE_SIZE)
    for item in data['items']:
        item['photo_web_url'] = _resolve_report_image_url(item)
    if export == 'xlsx':
        rows = [[i['id'], i.get('full_name') or i.get('username') or '', i['description'], i['created_at']] for i in data['items']]
        content = build_workbook('Reports', ['ID', 'Сотрудник', 'Описание', 'Дата'], rows)
        return Response(content=content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=reports.xlsx'})
    flash = None
    if migrated is not None:
        flash = f'Сгенерировано ссылок и локальных файлов: {migrated}'
    elif normalized is not None:
        flash = f'Обновлено URL у существующих файлов: {normalized}'

    employee_options = await get_employee_options()
    selected_employee = await get_selected_employee(normalized_employee_id)
    return render(request, 'reports.html', {
        'data': data,
        'filters': {'employee': employee, 'employee_id': normalized_employee_id or '', 'employee_label': employee_label, 'date_from': date_from, 'date_to': date_to},
        'flash': flash,
        'employee_options': employee_options,
        'selected_employee': selected_employee,
    })


@router.post('/generate-photo-urls')
@require_login
async def generate_photo_urls(request: Request):
    bot = Bot(token=settings.bot_token)
    try:
        migrated = await backfill_report_public_urls(bot)
        normalized = await normalize_report_urls()
    finally:
        await bot.session.close()
    return RedirectResponse(f'/web/reports?migrated={migrated}&normalized={normalized}', status_code=303)
