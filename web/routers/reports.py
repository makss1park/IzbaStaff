from __future__ import annotations

from aiogram import Bot
from fastapi import APIRouter, Query, Request
from starlette.responses import RedirectResponse

from bot.config import settings
from core.repositories import reports as reports_repo
from web.dependencies import require_login
from web.routers.common import render
from web.services.employees import employee_filter_context, parse_employee_id
from web.services.excel import xlsx_response
from web.services.files import report_image_url
from web.services.query import parse_page
from web.services.report_migration import backfill_report_public_urls, normalize_report_urls

router = APIRouter(prefix='/web/reports', tags=['reports'])
PAGE_SIZE = 12


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
    data = await reports_repo.search_page(
        employee_id=normalized_employee_id,
        employee_query=employee,
        date_from=date_from,
        date_to=date_to,
        page=parse_page(page),
        page_size=PAGE_SIZE,
    )
    for item in data['items']:
        item['photo_web_url'] = report_image_url(item)

    if export == 'xlsx':
        rows = [[i['id'], i.get('full_name') or i.get('username') or '', i['description'], i['created_at']] for i in data['items']]
        return xlsx_response('reports.xlsx', 'Reports', ['ID', 'Сотрудник', 'Описание', 'Дата'], rows)

    flash = None
    if migrated is not None:
        flash = f'Сгенерировано ссылок и локальных файлов: {migrated}'
    elif normalized is not None:
        flash = f'Обновлено URL у существующих файлов: {normalized}'

    return render(request, 'reports.html', {
        'data': data,
        'filters': {
            'employee': employee,
            'employee_id': normalized_employee_id or '',
            'employee_label': employee_label,
            'date_from': date_from,
            'date_to': date_to,
        },
        'flash': flash,
        **await employee_filter_context(normalized_employee_id),
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
