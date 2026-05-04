from __future__ import annotations

from fastapi import APIRouter, Form, Request
from starlette.responses import RedirectResponse

from bot.database import fetch_one
from web.auth import verify_password
from web.routers.common import render

router = APIRouter(prefix='/web', tags=['auth'])


@router.get('/login')
async def login_page(request: Request):
    if request.session.get('admin'):
        return RedirectResponse('/web', status_code=303)
    return render(request, 'login.html', {'error': None})


@router.post('/login')
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    row = await fetch_one(
        'SELECT id, username, role, is_active, password_hash FROM admin_users WHERE username=%s LIMIT 1',
        (username.strip(),),
    )
    if not row or not row['is_active'] or not verify_password(password, row['password_hash']):
        return render(request, 'login.html', {'error': 'Неверный логин или пароль'})
    request.session['admin'] = {'id': row['id'], 'username': row['username'], 'role': row['role']}
    return RedirectResponse('/web', status_code=303)


@router.get('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/web/login', status_code=303)
