from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse, Response

from bot.database import execute, fetch_one
from web.dependencies import require_login
from web.routers.common import render
from web.services.employees import get_employee_options, get_selected_employee, parse_employee_id
from web.services.excel import build_workbook
from web.services.query import paginate_query, parse_page

router = APIRouter(prefix='/web/shifts', tags=['shifts'])
PAGE_SIZE = 20


def _parse_dt_local(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


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
    clauses = ['1=1']
    args: list = []
    if normalized_employee_id:
        clauses.append('s.user_id = %s')
        args.append(normalized_employee_id)
    elif employee.strip():
        clauses.append('(u.full_name LIKE %s OR u.username LIKE %s)')
        like = f"%{employee.strip()}%"
        args.extend([like, like])
    if status == 'open':
        clauses.append('s.closed_at IS NULL')
    elif status == 'closed':
        clauses.append('s.closed_at IS NOT NULL')
    if date_from.strip():
        clauses.append('DATE(s.opened_at) >= %s')
        args.append(date_from.strip())
    if date_to.strip():
        clauses.append('DATE(s.opened_at) <= %s')
        args.append(date_to.strip())
    where_sql = ' AND '.join(clauses)
    base_query = f'''SELECT s.*, u.full_name, u.username, u.hourly_rate, ROUND(s.duration_seconds / 3600, 2) AS duration_hours, ROUND(s.late_seconds / 60, 0) AS late_minutes, CAST(ROUND((s.duration_seconds / 3600) * u.hourly_rate, 0) AS SIGNED) AS salary_amount FROM shifts s JOIN users u ON u.id=s.user_id WHERE {where_sql} ORDER BY s.opened_at DESC'''
    count_query = f'''SELECT COUNT(*) AS cnt FROM shifts s JOIN users u ON u.id=s.user_id WHERE {where_sql}'''
    data = await paginate_query(base_query, count_query, tuple(args), parse_page(page), PAGE_SIZE)
    if export == 'xlsx':
        rows = [[i['id'], i.get('full_name') or i.get('username') or '', i['opened_at'], i['closed_at'], i['duration_hours'], i['late_minutes'], i['salary_amount']] for i in data['items']]
        content = build_workbook('Shifts', ['ID', 'Сотрудник', 'Открыта', 'Закрыта', 'Часы', 'Опоздание, мин', 'Сумма'], rows)
        return Response(content=content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=shifts.xlsx'})

    employee_options = await get_employee_options()
    selected_employee = await get_selected_employee(normalized_employee_id)
    return render(request, 'shifts.html', {
        'data': data,
        'filters': {'employee': employee, 'employee_id': normalized_employee_id or '', 'employee_label': employee_label, 'status': status, 'date_from': date_from, 'date_to': date_to},
        'employee_options': employee_options,
        'selected_employee': selected_employee,
    })


@router.get('/{shift_id}')
@require_login
async def shift_detail(request: Request, shift_id: int, updated: int = Query(0)):
    shift = await fetch_one(
        '''
        SELECT s.*, u.full_name, u.username, u.hourly_rate,
               ROUND(s.duration_seconds / 3600, 2) AS duration_hours,
               ROUND(s.late_seconds / 60, 0) AS late_minutes,
               CAST(ROUND((s.duration_seconds / 3600) * u.hourly_rate, 0) AS SIGNED) AS salary_amount,
               p.start_at AS period_start_at,
               p.end_at AS period_end_at,
               p.is_closed AS period_is_closed
        FROM shifts s
        JOIN users u ON u.id = s.user_id
        JOIN payroll_periods p ON p.id = s.payroll_period_id
        WHERE s.id = %s
        LIMIT 1
        ''',
        (shift_id,),
    )
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
    opened_dt = _parse_dt_local(opened_at)
    closed_dt = _parse_dt_local(closed_at)
    if opened_dt is None:
        return RedirectResponse(url=f'/web/shifts/{shift_id}', status_code=303)
    if closed_dt is not None and closed_dt < opened_dt:
        closed_dt = opened_dt
    duration_seconds = int((closed_dt - opened_dt).total_seconds()) if closed_dt else 0
    late_seconds = max(int(late_seconds or 0), 0)
    await execute(
        '''
        UPDATE shifts
        SET opened_at=%s,
            closed_at=%s,
            duration_seconds=%s,
            late_seconds=%s,
            payroll_period_id=%s,
            is_scheduled=%s,
            updated_at=NOW()
        WHERE id=%s
        ''',
        (opened_dt, closed_dt, duration_seconds, late_seconds, payroll_period_id, 1 if int(is_scheduled or 0) else 0, shift_id),
    )
    return RedirectResponse(url=f'/web/shifts/{shift_id}?updated=1', status_code=303)
