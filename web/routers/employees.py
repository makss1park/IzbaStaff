from __future__ import annotations

import json

from aiogram import Bot
from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse, Response

from bot.keyboards.inline import back_to_main_menu, graph_menu, profile_menu

from bot.config import settings
from bot.database import execute, fetch_all, fetch_one
from bot.services.notifications import (
    notify_employee_rate_changed,
    notify_employee_schedule_changed,
)
from web.dependencies import require_login, require_role
from web.routers.common import render
from web.services.excel import build_workbook
from web.services.query import paginate_query, parse_page

router = APIRouter(prefix='/web/employees', tags=['employees'])
PAGE_SIZE = 15


@router.get('')
@require_login
async def employees_list(
    request: Request,
    page: int = Query(1),
    q: str = Query(''),
    status: str = Query('all'),
    export: str | None = Query(None),
):
    clauses = ['1=1']
    args: list = []
    if q.strip():
        clauses.append('(u.full_name LIKE %s OR u.username LIKE %s OR u.phone LIKE %s)')
        like = f"%{q.strip()}%"
        args.extend([like, like, like])
    if status == 'active':
        clauses.append('u.is_active=1')
    elif status == 'inactive':
        clauses.append('u.is_active=0')

    where_sql = ' AND '.join(clauses)
    base_query = f'''
        SELECT u.*, s.weekdays_json, s.start_time, s.end_time,
               (SELECT COUNT(*) FROM shifts sh WHERE sh.user_id = u.id AND sh.closed_at IS NULL) AS active_shift_count
        FROM users u
        LEFT JOIN user_schedules s ON s.user_id = u.id AND s.is_active=1
        WHERE {where_sql}
        ORDER BY u.is_active DESC, COALESCE(u.full_name, '') ASC, u.id DESC
    '''
    count_query = f'SELECT COUNT(*) AS cnt FROM users u WHERE {where_sql}'
    data = await paginate_query(base_query, count_query, tuple(args), parse_page(page), PAGE_SIZE)

    if export == 'xlsx':
        rows = [[i['id'], i['full_name'], i['username'], i['phone'], i['role'], int(round(float(i['hourly_rate'] or 0))), 'Да' if i['is_active'] else 'Нет', i.get('weekdays_json') or '', i.get('start_time') or '', i.get('end_time') or ''] for i in data['items']]
        content = build_workbook('Employees', ['ID', 'ФИО', 'Username', 'Телефон', 'Роль', 'Ставка', 'Активен', 'Дни', 'Начало', 'Конец'], rows)
        return Response(content=content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=employees.xlsx'})

    return render(request, 'employees.html', {'data': data, 'filters': {'q': q, 'status': status}})


@router.get('/{user_id}')
@require_login
async def employee_detail(request: Request, user_id: int):
    employee = await fetch_one('SELECT *, CAST(ROUND(hourly_rate, 0) AS SIGNED) AS hourly_rate_int FROM users WHERE id=%s LIMIT 1', (user_id,))
    if not employee:
        return RedirectResponse('/web/employees', status_code=303)
    schedule = await fetch_one('SELECT * FROM user_schedules WHERE user_id=%s AND is_active=1 LIMIT 1', (user_id,))
    periods = await fetch_all(
        '''
        SELECT p.*, 
               ROUND(COALESCE((SELECT SUM(duration_seconds) FROM shifts WHERE payroll_period_id=p.id AND closed_at IS NOT NULL), 0)/3600, 2) AS hours_worked,
               CAST(ROUND(COALESCE((SELECT SUM(duration_seconds) FROM shifts WHERE payroll_period_id=p.id AND closed_at IS NOT NULL), 0)/3600 * %s, 0) AS SIGNED) AS salary_amount,
               CAST(ROUND(COALESCE((SELECT SUM(amount) FROM fines WHERE payroll_period_id=p.id), 0), 0) AS SIGNED) AS fines_amount
        FROM payroll_periods p
        WHERE p.user_id=%s
        ORDER BY p.start_at DESC
        LIMIT 20
        ''',
        (employee['hourly_rate'], user_id),
    )
    return render(request, 'employee_detail.html', {'employee': employee, 'schedule': schedule, 'periods': periods})


@router.post('/{user_id}/edit')
@require_role('superadmin', 'manager')
async def employee_edit(request: Request, user_id: int, full_name: str = Form(''), phone: str = Form(''), hourly_rate: float = Form(0), is_active: str | None = Form(None)):
    existing = await fetch_one('SELECT * FROM users WHERE id=%s LIMIT 1', (user_id,))
    await execute(
        'UPDATE users SET full_name=%s, phone=%s, hourly_rate=%s, is_active=%s, updated_at=NOW() WHERE id=%s',
        (full_name.strip(), phone.strip(), hourly_rate, 1 if is_active == '1' else 0, user_id),
    )

    if existing and float(existing.get('hourly_rate') or 0) != float(hourly_rate):
        bot = Bot(token=settings.bot_token)
        try:
            await notify_employee_rate_changed(bot, user_id, float(hourly_rate))
        finally:
            await bot.session.close()

    return RedirectResponse(f'/web/employees/{user_id}', status_code=303)


@router.post('/{user_id}/schedule')
@require_role('superadmin', 'manager')
async def employee_schedule(request: Request, user_id: int, weekdays_json: str = Form('1,2,3,4,5'), start_time: str = Form('09:00'), end_time: str = Form('18:00')):
    existing = await fetch_one(
        'SELECT * FROM user_schedules WHERE user_id=%s AND is_active=1 LIMIT 1',
        (user_id,),
    )

    weekdays_clean = weekdays_json.strip()
    start_clean = start_time.strip()
    end_clean = end_time.strip()

    if existing:
        await execute(
            'UPDATE user_schedules SET weekdays_json=%s, start_time=%s, end_time=%s, updated_at=NOW() WHERE id=%s',
            (weekdays_clean, start_clean, end_clean, existing['id']),
        )
    else:
        await execute(
            'INSERT INTO user_schedules (user_id, weekdays_json, start_time, end_time, is_active, created_at, updated_at) VALUES (%s, %s, %s, %s, 1, NOW(), NOW())',
            (user_id, weekdays_clean, start_clean, end_clean),
        )

    old_weekdays = (existing.get('weekdays_json') if existing else None) or ''
    old_start = (existing.get('start_time') if existing else None) or ''
    old_end = (existing.get('end_time') if existing else None) or ''

    if old_weekdays != weekdays_clean or old_start != start_clean or old_end != end_clean:
        try:
            weekdays_list = [int(x.strip()) for x in weekdays_clean.split(',') if x.strip()]
        except Exception:
            weekdays_list = []

        bot = Bot(token=settings.bot_token)
        try:
            await notify_employee_schedule_changed(
                bot,
                user_id,
                weekdays_list,
                start_clean,
                end_clean,
            )
        finally:
            await bot.session.close()

    return RedirectResponse(f'/web/employees/{user_id}', status_code=303)
