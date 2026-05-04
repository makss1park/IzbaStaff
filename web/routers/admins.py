from __future__ import annotations

from fastapi import APIRouter, Form, Query, Request
from starlette.responses import RedirectResponse

from bot.database import execute
from web.auth import hash_password
from web.dependencies import require_role
from web.routers.common import render
from web.services.query import paginate_query, parse_page

router = APIRouter(prefix='/web/admins', tags=['admins'])
PAGE_SIZE = 20


@router.get('')
@require_role('superadmin')
async def admins_list(request: Request, page: int = Query(1)):
    data = await paginate_query('SELECT id, username, role, is_active, created_at, updated_at FROM admin_users ORDER BY username ASC', 'SELECT COUNT(*) AS cnt FROM admin_users', (), parse_page(page), PAGE_SIZE)
    return render(request, 'admins.html', {'data': data, 'filters': {}})


@router.post('/create')
@require_role('superadmin')
async def admins_create(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form('manager')):
    await execute('INSERT INTO admin_users (username, password_hash, role, is_active, created_at, updated_at) VALUES (%s, %s, %s, 1, NOW(), NOW())', (username.strip(), hash_password(password), role))
    return RedirectResponse('/web/admins', status_code=303)


@router.post('/{admin_id}/toggle')
@require_role('superadmin')
async def admins_toggle(request: Request, admin_id: int):
    await execute('UPDATE admin_users SET is_active = IF(is_active=1,0,1), updated_at=NOW() WHERE id=%s', (admin_id,))
    return RedirectResponse('/web/admins', status_code=303)
