from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from fastapi import Request
from starlette.responses import RedirectResponse


def current_admin(request: Request) -> dict | None:
    admin = request.session.get('admin')
    return admin if isinstance(admin, dict) else None


def require_login(handler: Callable):
    @wraps(handler)
    async def wrapper(*args, **kwargs):
        request: Request | None = kwargs.get('request')
        if request is None:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if request is None or current_admin(request) is None:
            return RedirectResponse('/web/login', status_code=303)
        return await handler(*args, **kwargs)
    return wrapper


def require_role(*roles: str):
    def decorator(handler: Callable):
        @wraps(handler)
        async def wrapper(*args, **kwargs):
            request: Request | None = kwargs.get('request')
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request is None:
                return RedirectResponse('/web/login', status_code=303)
            admin = current_admin(request)
            if not admin:
                return RedirectResponse('/web/login', status_code=303)
            if admin.get('role') not in roles:
                return RedirectResponse('/web', status_code=303)
            return await handler(*args, **kwargs)
        return wrapper
    return decorator
