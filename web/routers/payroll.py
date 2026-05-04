from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse, Response

from bot.database import execute, fetch_all, fetch_one
from web.dependencies import require_login
from web.routers.common import render
from web.services.employees import get_employee_options, get_selected_employee, parse_employee_id
from web.services.excel import build_workbook
from web.services.query import paginate_query, parse_page

router = APIRouter(prefix='/web/payroll', tags=['payroll'])
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
    clauses = ['1=1']
    args: list = []
    if normalized_employee_id:
        clauses.append('p.user_id = %s')
        args.append(normalized_employee_id)
    elif employee.strip():
        clauses.append('(u.full_name LIKE %s OR u.username LIKE %s)')
        like = f"%{employee.strip()}%"
        args.extend([like, like])
    if date_from.strip():
        clauses.append('DATE(p.start_at) >= %s')
        args.append(date_from.strip())
    if date_to.strip():
        clauses.append('DATE(COALESCE(p.end_at, p.start_at)) <= %s')
        args.append(date_to.strip())
    if status == 'open':
        clauses.append('p.is_closed=0')
    elif status == 'closed':
        clauses.append('p.is_closed=1')
    elif status == 'previous_closed':
        clauses.append(
            '''
            p.is_closed = 1
            AND p.start_at = (
                SELECT MAX(pc.start_at)
                FROM payroll_periods pc
                WHERE pc.user_id = p.user_id
                  AND pc.is_closed = 1
                  AND pc.start_at < COALESCE(
                      (
                          SELECT MIN(po.start_at)
                          FROM payroll_periods po
                          WHERE po.user_id = p.user_id AND po.is_closed = 0
                      ),
                      '2999-12-31 23:59:59'
                  )
            )
            '''
        )
    where_sql = ' AND '.join(clauses)

    base_query = f'''
        SELECT p.*, u.full_name, u.username, u.hourly_rate,
               ROUND(COALESCE(sh.hours_worked, 0), 2) AS hours_worked,
               CAST(ROUND(COALESCE(sh.salary_amount, 0), 0) AS SIGNED) AS salary_amount,
               CAST(ROUND(COALESCE(fi.fines_amount, 0), 0) AS SIGNED) AS fines_amount,
               CAST(ROUND(COALESCE(sh.salary_amount, 0) - COALESCE(fi.fines_amount, 0), 0) AS SIGNED) AS net_amount,
               COALESCE(sh.shift_count, 0) AS shift_count,
               COALESCE(sh.late_count, 0) AS late_count,
               COALESCE(sh.late_minutes, 0) AS late_minutes
        FROM payroll_periods p
        JOIN users u ON u.id = p.user_id
        LEFT JOIN (
            SELECT s.payroll_period_id,
                   COUNT(*) AS shift_count,
                   SUM(CASE WHEN s.closed_at IS NOT NULL THEN s.duration_seconds ELSE 0 END) / 3600 AS hours_worked,
                   SUM(CASE WHEN s.closed_at IS NOT NULL THEN s.duration_seconds ELSE 0 END) / 3600 * MAX(u.hourly_rate) AS salary_amount,
                   SUM(CASE WHEN s.late_seconds > 0 THEN 1 ELSE 0 END) AS late_count,
                   SUM(s.late_seconds) / 60 AS late_minutes
            FROM shifts s
            JOIN users u ON u.id = s.user_id
            GROUP BY s.payroll_period_id
        ) sh ON sh.payroll_period_id = p.id
        LEFT JOIN (
            SELECT payroll_period_id, SUM(amount) AS fines_amount
            FROM fines GROUP BY payroll_period_id
        ) fi ON fi.payroll_period_id = p.id
        WHERE {where_sql}
        ORDER BY p.start_at DESC, p.id DESC
    '''
    count_query = f'''SELECT COUNT(*) AS cnt FROM payroll_periods p JOIN users u ON u.id=p.user_id WHERE {where_sql}'''

    summary_query = f'''
        SELECT
            COALESCE(SUM(periods.shift_count), 0) AS total_shifts,
            ROUND(COALESCE(SUM(periods.hours_worked), 0), 2) AS total_hours,
            CAST(ROUND(COALESCE(SUM(periods.salary_amount), 0), 0) AS SIGNED) AS total_salary_amount,
            CAST(ROUND(COALESCE(SUM(periods.fines_amount), 0), 0) AS SIGNED) AS total_fines_amount,
            CAST(ROUND(COALESCE(SUM(periods.salary_amount) - SUM(periods.fines_amount), 0), 0) AS SIGNED) AS total_net_amount
        FROM (
            SELECT p.id,
                   COALESCE(sh.shift_count, 0) AS shift_count,
                   COALESCE(sh.hours_worked, 0) AS hours_worked,
                   COALESCE(sh.salary_amount, 0) AS salary_amount,
                   COALESCE(fi.fines_amount, 0) AS fines_amount
            FROM payroll_periods p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN (
                SELECT s.payroll_period_id,
                       COUNT(*) AS shift_count,
                       SUM(CASE WHEN s.closed_at IS NOT NULL THEN s.duration_seconds ELSE 0 END) / 3600 AS hours_worked,
                       SUM(CASE WHEN s.closed_at IS NOT NULL THEN s.duration_seconds ELSE 0 END) / 3600 * MAX(u.hourly_rate) AS salary_amount
                FROM shifts s
                JOIN users u ON u.id = s.user_id
                GROUP BY s.payroll_period_id
            ) sh ON sh.payroll_period_id = p.id
            LEFT JOIN (
                SELECT payroll_period_id, SUM(amount) AS fines_amount
                FROM fines GROUP BY payroll_period_id
            ) fi ON fi.payroll_period_id = p.id
            WHERE {where_sql}
        ) periods
    '''

    data = await paginate_query(base_query, count_query, tuple(args), parse_page(page), PAGE_SIZE)
    summary = await fetch_one(summary_query, tuple(args)) or {}

    if export == 'xlsx':
        rows = [[i['id'], i.get('full_name') or i.get('username') or '', i['start_at'], i['end_at'], i['shift_count'], i['hours_worked'], i['salary_amount'], i['fines_amount'], i['net_amount'], 'Закрыт' if i['is_closed'] else 'Открыт'] for i in data['items']]
        content = build_workbook('Payroll', ['ID', 'Сотрудник', 'Начало', 'Конец', 'Смен', 'Часы', 'Начислено', 'Штрафы', 'К выплате', 'Статус'], rows)
        return Response(content=content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=payroll_periods.xlsx'})

    employee_options = await get_employee_options()
    selected_employee = await get_selected_employee(normalized_employee_id)
    return render(request, 'payroll.html', {
        'data': data,
        'summary': summary,
        'filters': {'employee': employee, 'employee_id': normalized_employee_id or '', 'employee_label': employee_label, 'date_from': date_from, 'date_to': date_to, 'status': status},
        'employee_options': employee_options,
        'selected_employee': selected_employee,
    })


@router.get('/{period_id}')
@require_login
async def payroll_detail(request: Request, period_id: int, export: str | None = Query(None), updated: int = Query(0)):
    period = await fetch_one('SELECT p.*, u.full_name, u.username, u.hourly_rate FROM payroll_periods p JOIN users u ON u.id=p.user_id WHERE p.id=%s LIMIT 1', (period_id,))
    if not period:
        return render(request, 'payroll_detail.html', {'period': None, 'shifts': [], 'fines': [], 'chart_json': '[]', 'updated': False})
    shifts = await fetch_all(
        'SELECT id, opened_at, closed_at, ROUND(duration_seconds/3600, 2) AS duration_hours, ROUND(late_seconds/60, 0) AS late_minutes, CAST(ROUND(duration_seconds/3600 * %s, 0) AS SIGNED) AS salary_amount FROM shifts WHERE payroll_period_id=%s ORDER BY opened_at ASC',
        (period['hourly_rate'], period_id),
    )
    fines = await fetch_all('SELECT *, CAST(ROUND(amount, 0) AS SIGNED) AS amount_int FROM fines WHERE payroll_period_id=%s ORDER BY created_at DESC', (period_id,))
    if export == 'xlsx':
        rows = [[s['id'], s['opened_at'], s['closed_at'], s['duration_hours'], s['late_minutes'], s['salary_amount']] for s in shifts]
        total_salary = round(sum(float(s.get('salary_amount') or 0) for s in shifts), 2)
        total_fines = round(sum(float(f.get('amount') or 0) for f in fines), 2)
        rows.append([])
        rows.append(['Итого', '', '', round(sum(float(s.get('duration_hours') or 0) for s in shifts), 2), '', total_salary])
        rows.append(['Штрафы', '', '', '', '', total_fines])
        rows.append(['К выплате', '', '', '', '', round(total_salary - total_fines, 2)])
        content = build_workbook(
            'Payroll Detail',
            ['ID смены', 'Открыта', 'Закрыта', 'Часы', 'Опоздание, мин', 'Сумма'],
            rows,
        )
        filename = f"payroll_period_{period_id}.xlsx"
        return Response(content=content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename={filename}'})
    chart = [{'label': s['opened_at'].strftime('%d.%m') if hasattr(s['opened_at'], 'strftime') else str(s['opened_at']), 'value': float(s['salary_amount'] or 0)} for s in shifts]
    return render(request, 'payroll_detail.html', {'period': period, 'shifts': shifts, 'fines': fines, 'chart_json': json.dumps(chart, ensure_ascii=False), 'updated': bool(updated)})


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
    start_dt = _parse_dt_local(start_at)
    end_dt = _parse_dt_local(end_at)
    if start_dt is None:
        return RedirectResponse(url=f'/web/payroll/{period_id}', status_code=303)
    if end_dt is not None and end_dt < start_dt:
        end_dt = start_dt
    is_closed_value = 1 if int(is_closed or 0) else 0
    if is_closed_value == 0:
        end_dt = None
    await execute(
        '''
        UPDATE payroll_periods
        SET start_at=%s,
            end_at=%s,
            is_closed=%s,
            updated_at=NOW()
        WHERE id=%s
        ''',
        (start_dt, end_dt, is_closed_value, period_id),
    )
    return RedirectResponse(url=f'/web/payroll/{period_id}?updated=1', status_code=303)
