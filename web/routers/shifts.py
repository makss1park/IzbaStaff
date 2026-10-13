from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse

from core.repositories import shifts as shifts_repo
from web.dependencies import require_login
from web.routers.common import render
from web.services.employees import employee_filter_context, parse_employee_id
from web.services.excel import xlsx_response
from web.services.forms import parse_dt_local
from web.services.query import parse_page

router = APIRouter(prefix='/web/shifts', tags=['shifts'])
PAGE_SIZE = 20


@router.get('')
@require_login
async def shifts_list(
    request: Request,
    page: int = Query(1),
    employee: str = Query(''),
    employee_id: str | None = Query(None),
    employee_label: str = Query(''),
    status: str = Query('all'),
    date_from: str = Query(''),
    date_to: str = Query(''),
    export: str | None = Query(None),
):
    normalized_employee_id = parse_employee_id(employee_id)
    data = await shifts_repo.search_page(
        employee_id=normalized_employee_id,
        employee_query=employee,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=parse_page(page),
        page_size=PAGE_SIZE,
    )

    if export == 'xlsx':
        rows = [
            [i['id'], i.get('full_name') or i.get('username') or '', i['opened_at'], i['closed_at'], i['duration_hours'], i['late_minutes'], i['salary_amount']]
            for i in data['items']
        ]
        return xlsx_response('shifts.xlsx', 'Shifts', ['ID', 'Сотрудник', 'Открыта', 'Закрыта', 'Часы', 'Опоздание, мин', 'Сумма'], rows)

    return render(request, 'shifts.html', {
        'data': data,
        'filters': {
            'employee': employee,
            'employee_id': normalized_employee_id or '',
            'employee_label': employee_label,
            'status': status,
            'date_from': date_from,
            'date_to': date_to,
        },
        **await employee_filter_context(normalized_employee_id),
    })


@router.get('/{shift_id}')
@require_login
async def shift_detail(request: Request, shift_id: int, updated: int = Query(0)):
    shift = await shifts_repo.get_detail(shift_id)
    return render(request, 'shift_detail.html', {'shift': shift, 'updated': bool(updated)})


@router.post('/{shift_id}/update')
@require_login
async def shift_update(
    request: Request,
    shift_id: int,
    opened_at: str = Form(...),
    closed_at: str = Form(''),
    late_seconds: int = Form(0),
    payroll_period_id: int = Form(...),
    is_scheduled: int = Form(0),
):
    del request
    opened_dt = parse_dt_local(opened_at)
    closed_dt = parse_dt_local(closed_at)
    if opened_dt is None:
        return RedirectResponse(url=f'/web/shifts/{shift_id}', status_code=303)
    if closed_dt is not None and closed_dt < opened_dt:
        closed_dt = opened_dt
    await shifts_repo.update_from_web(
        shift_id,
        opened_at=opened_dt,
        closed_at=closed_dt,
        duration_seconds=int((closed_dt - opened_dt).total_seconds()) if closed_dt else 0,
        late_seconds=max(int(late_seconds or 0), 0),
        payroll_period_id=payroll_period_id,
        is_scheduled=bool(int(is_scheduled or 0)),
    )
    return RedirectResponse(url=f'/web/shifts/{shift_id}?updated=1', status_code=303)
