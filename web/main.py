from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from bot.database import close_pool, init_pool
from web.config import web_settings
from web.routers import auth, dashboard, employees, reports, shifts, payroll, settings, admins, catalogs

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title='Shift Bot Web Admin')


@app.get('/', include_in_schema=False)
async def root_redirect():
    return RedirectResponse('/web', status_code=303)


app.add_middleware(
    SessionMiddleware,
    secret_key=web_settings.secret_key,
    session_cookie=web_settings.web_session_cookie,
    same_site='lax',
    https_only=False,
)
app.mount('/web/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')

reports_dir = Path(web_settings.reports_storage_dir)
if not reports_dir.is_absolute():
    reports_dir = Path(__file__).resolve().parent.parent / reports_dir
reports_dir.mkdir(parents=True, exist_ok=True)
app.mount(web_settings.reports_url_prefix, StaticFiles(directory=reports_dir), name='report_files')

catalogs_dir = Path(web_settings.catalogs_storage_dir)
if not catalogs_dir.is_absolute():
    catalogs_dir = Path(__file__).resolve().parent.parent / catalogs_dir
catalogs_dir.mkdir(parents=True, exist_ok=True)
app.mount(web_settings.catalogs_url_prefix, StaticFiles(directory=catalogs_dir), name='catalog_files')

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(employees.router)
app.include_router(reports.router)
app.include_router(shifts.router)
app.include_router(payroll.router)
app.include_router(settings.router)
app.include_router(catalogs.router)
app.include_router(admins.router)


@app.on_event('startup')
async def on_startup() -> None:
    await init_pool()


@app.on_event('shutdown')
async def on_shutdown() -> None:
    await close_pool()
