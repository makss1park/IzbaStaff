from __future__ import annotations

from fastapi import APIRouter, Form, Request
from starlette.responses import RedirectResponse

from bot.database import execute, fetch_one
from web.auth import hash_password, is_password_hash, verify_password
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

    if not row or not row['is_active']:
        return render(request, 'login.html', {'error': 'Неверный логин или пароль'})

    stored_password = row.get('password_hash')

    password_ok = verify_password(password, stored_password)

    # Совместимость со старой/неправильной базой:
    # если в password_hash лежит обычный текстовый пароль, не падаем,
    # а даём войти и сразу заменяем его на нормальный hash.
    if not password_ok and stored_password == password:
        new_hash = hash_password(password)
        await execute(
            'UPDATE admin_users SET password_hash=%s, updated_at=NOW() WHERE id=%s',
            (new_hash, row['id']),
        )
        password_ok = True

    if not password_ok:
        return render(request, 'login.html', {'error': 'Неверный логин или пароль'})

    # Если hash старый/неправильного формата, но пароль прошёл проверку,
    # обновляем hash на актуальный формат.
    if not is_password_hash(stored_password):
        await execute(
            'UPDATE admin_users SET password_hash=%s, updated_at=NOW() WHERE id=%s',
            (hash_password(password), row['id']),
        )

    request.session['admin'] = {'id': row['id'], 'username': row['username'], 'role': row['role']}
    return RedirectResponse('/web', status_code=303)


@router.get('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/web/login', status_code=303)
