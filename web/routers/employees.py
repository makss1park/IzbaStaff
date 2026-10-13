from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse

from core.repositories import payroll as payroll_repo
from core.repositories import schedules as schedules_repo
from core.repositories import users as users_repo
from web.dependencies import require_login, require_role
from web.routers.common import render
from web.services.excel import xlsx_response
from web.services.query import parse_page

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
    data = await users_repo.search_page(query=q, status=status, page=parse_page(page), page_size=PAGE_SIZE)

    if export == 'xlsx':
        rows = [
            [i['id'], i['full_name'], i['username'], i['phone'], i['role'], int(round(float(i['hourly_rate'] or 0))), 'Да' if i['is_active'] else 'Нет', i.get('weekdays_json') or '', i.get('start_time') or '', i.get('end_time') or '']
            for i in data['items']
        ]
        return xlsx_response('employees.xlsx', 'Employees', ['ID', 'ФИО', 'Username', 'Телефон', 'Роль', 'Ставка', 'Активен', 'Дни', 'Начало', 'Конец'], rows)

    return render(request, 'employees.html', {'data': data, 'filters': {'q': q, 'status': status}})


@router.get('/{user_id}')
@require_login
async def employee_detail(request: Request, user_id: int):
    employee = await users_repo.get_with_rate_int(user_id)
    if not employee:
        return RedirectResponse('/web/employees', status_code=303)
    schedule = await schedules_repo.get_active(user_id)
    periods = await payroll_repo.list_recent_for_user(user_id, employee['hourly_rate'])
    return render(request, 'employee_detail.html', {'employee': employee, 'schedule': schedule, 'periods': periods})


@router.post('/{user_id}/edit')
@require_role('superadmin', 'manager')
async def employee_edit(
    request: Request,
    user_id: int,
    full_name: str = Form(''),
    phone: str = Form(''),
    hourly_rate: float = Form(0),
    is_active: str | None = Form(None),
):
    await users_repo.update_profile_from_web(
        user_id,
        full_name=full_name.strip(),
        phone=phone.strip(),
        hourly_rate=hourly_rate,
        is_active=is_active == '1',
    )
    return RedirectResponse(f'/web/employees/{user_id}', status_code=303)


@router.post('/{user_id}/schedule')
@require_role('superadmin', 'manager')
async def employee_schedule(
    request: Request,
    user_id: int,
    weekdays_json: str = Form('1,2,3,4,5'),
    start_time: str = Form('09:00'),
    end_time: str = Form('18:00'),
):
    weekdays, start, end = weekdays_json.strip(), start_time.strip(), end_time.strip()
    existing = await schedules_repo.get_active(user_id)
    if existing:
        await schedules_repo.update_in_place(existing['id'], weekdays, start, end)
    else:
        await schedules_repo.create_now(user_id, weekdays, start, end)
    return RedirectResponse(f'/web/employees/{user_id}', status_code=303)
