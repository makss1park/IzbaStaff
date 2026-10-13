from __future__ import annotations

from fastapi import APIRouter, Form, Request
from starlette.responses import RedirectResponse

from core.repositories import admin_users as admin_users_repo
from web.auth import hash_password, is_password_hash, verify_password
from web.routers.common import render

router = APIRouter(prefix='/web', tags=['auth'])

LOGIN_ERROR = 'Неверный логин или пароль'


@router.get('/login')
async def login_page(request: Request):
    if request.session.get('admin'):
        return RedirectResponse('/web', status_code=303)
    return render(request, 'login.html', {'error': None})


@router.post('/login')
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    row = await admin_users_repo.get_by_username(username.strip())
    if not row or not row['is_active']:
        return render(request, 'login.html', {'error': LOGIN_ERROR})

    stored_password = row.get('password_hash')
    password_ok = verify_password(password, stored_password)

    # Совместимость со старой базой: если в password_hash лежит обычный текстовый
    # пароль, пускаем и ниже сразу заменяем его нормальным хэшем.
    if not password_ok and stored_password == password:
        password_ok = True

    if not password_ok:
        return render(request, 'login.html', {'error': LOGIN_ERROR})

    # Хэш устаревшего формата (или открытый пароль) — перехэшируем.
    if not is_password_hash(stored_password):
        await admin_users_repo.set_password_hash(row['id'], hash_password(password))

    request.session['admin'] = {'id': row['id'], 'username': row['username'], 'role': row['role']}
    return RedirectResponse('/web', status_code=303)


@router.get('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/web/login', status_code=303)
