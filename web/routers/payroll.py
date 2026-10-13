from __future__ import annotations

import json

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse

from core.repositories import fines as fines_repo
from core.repositories import payroll as payroll_repo
from core.repositories import shifts as shifts_repo
from web.dependencies import require_login
from web.routers.common import render
from web.services.employees import employee_filter_context, parse_employee_id
from web.services.excel import xlsx_response
from web.services.forms import parse_dt_local
from web.services.query import parse_page

router = APIRouter(prefix='/web/payroll', tags=['payroll'])
PAGE_SIZE = 20


@router.get('')
@require_login
async def payroll_list(
    request: Request,
    page: int = Query(1),
    employee: str = Query(''),
    employee_id: str | None = Query(None),
    employee_label: str = Query(''),
    date_from: str = Query(''),
    date_to: str = Query(''),
    status: str = Query('all'),
    export: str | None = Query(None),
):
    normalized_employee_id = parse_employee_id(employee_id)
    data, summary = await payroll_repo.search_page_with_summary(
        employee_id=normalized_employee_id,
        employee_query=employee,
        date_from=date_from,
        date_to=date_to,
        status=status,
        page=parse_page(page),
        page_size=PAGE_SIZE,
    )

    if export == 'xlsx':
        rows = [
            [i['id'], i.get('full_name') or i.get('username') or '', i['start_at'], i['end_at'], i['shift_count'], i['hours_worked'], i['salary_amount'], i['fines_amount'], i['net_amount'], 'Закрыт' if i['is_closed'] else 'Открыт']
            for i in data['items']
        ]
        return xlsx_response('payroll_periods.xlsx', 'Payroll', ['ID', 'Сотрудник', 'Начало', 'Конец', 'Смен', 'Часы', 'Начислено', 'Штрафы', 'К выплате', 'Статус'], rows)

    return render(request, 'payroll.html', {
        'data': data,
        'summary': summary,
        'filters': {
            'employee': employee,
            'employee_id': normalized_employee_id or '',
            'employee_label': employee_label,
            'date_from': date_from,
            'date_to': date_to,
            'status': status,
        },
        **await employee_filter_context(normalized_employee_id),
    })


def _period_export_rows(shifts: list[dict], fines: list[dict]) -> list[list]:
    rows = [[s['id'], s['opened_at'], s['closed_at'], s['duration_hours'], s['late_minutes'], s['salary_amount']] for s in shifts]
    total_hours = round(sum(float(s.get('duration_hours') or 0) for s in shifts), 2)
    total_salary = round(sum(float(s.get('salary_amount') or 0) for s in shifts), 2)
    total_fines = round(sum(float(f.get('amount') or 0) for f in fines), 2)
    rows.append([])
    rows.append(['Итого', '', '', total_hours, '', total_salary])
    rows.append(['Штрафы', '', '', '', '', total_fines])
    rows.append(['К выплате', '', '', '', '', round(total_salary - total_fines, 2)])
    return rows


@router.get('/{period_id}')
@require_login
async def payroll_detail(request: Request, period_id: int, export: str | None = Query(None), updated: int = Query(0)):
    period = await payroll_repo.get_with_user(period_id)
    if not period:
        return render(request, 'payroll_detail.html', {'period': None, 'shifts': [], 'fines': [], 'chart_json': '[]', 'updated': False})

    shifts = await shifts_repo.list_for_period_with_salary(period_id, period['hourly_rate'])
    fines = await fines_repo.list_for_period(period_id)

    if export == 'xlsx':
        return xlsx_response(
            f'payroll_period_{period_id}.xlsx',
            'Payroll Detail',
            ['ID смены', 'Открыта', 'Закрыта', 'Часы', 'Опоздание, мин', 'Сумма'],
            _period_export_rows(shifts, fines),
        )

    chart = [
        {
            'label': s['opened_at'].strftime('%d.%m') if hasattr(s['opened_at'], 'strftime') else str(s['opened_at']),
            'value': float(s['salary_amount'] or 0),
        }
        for s in shifts
    ]
    return render(request, 'payroll_detail.html', {
        'period': period,
        'shifts': shifts,
        'fines': fines,
        'chart_json': json.dumps(chart, ensure_ascii=False),
        'updated': bool(updated),
    })


@router.post('/{period_id}/update')
@require_login
async def payroll_update(
    request: Request,
    period_id: int,
    start_at: str = Form(...),
    end_at: str = Form(''),
    is_closed: int = Form(0),
):
    del request
    start_dt = parse_dt_local(start_at)
    end_dt = parse_dt_local(end_at)
    if start_dt is None:
        return RedirectResponse(url=f'/web/payroll/{period_id}', status_code=303)
    if end_dt is not None and end_dt < start_dt:
        end_dt = start_dt
    closed = bool(int(is_closed or 0))
    if not closed:
        end_dt = None
    await payroll_repo.update_from_web(period_id, start_at=start_dt, end_at=end_dt, is_closed=closed)
    return RedirectResponse(url=f'/web/payroll/{period_id}?updated=1', status_code=303)
