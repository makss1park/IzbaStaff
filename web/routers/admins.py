from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse

from core.repositories import admin_users as admin_users_repo
from web.auth import hash_password
from web.dependencies import require_role
from web.routers.common import render
from web.services.query import parse_page

router = APIRouter(prefix='/web/admins', tags=['admins'])
PAGE_SIZE = 20


@router.get('')
@require_role('superadmin')
async def admins_list(request: Request, page: int = Query(1)):
    data = await admin_users_repo.list_page(parse_page(page), PAGE_SIZE)
    return render(request, 'admins.html', {'data': data, 'filters': {}})


@router.post('/create')
@require_role('superadmin')
async def admins_create(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form('manager')):
    await admin_users_repo.create(username.strip(), hash_password(password), role)
    return RedirectResponse('/web/admins', status_code=303)


@router.post('/{admin_id}/toggle')
@require_role('superadmin')
async def admins_toggle(request: Request, admin_id: int):
    await admin_users_repo.toggle_active(admin_id)
    return RedirectResponse('/web/admins', status_code=303)
