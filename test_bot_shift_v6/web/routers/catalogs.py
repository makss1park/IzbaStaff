from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Request
from starlette.responses import Response

from web.config import web_settings
from web.dependencies import require_login
from web.routers.common import render
from web.services.excel import build_workbook
from web.services.query import paginate_query, parse_page

router = APIRouter(prefix='/web/catalogs', tags=['catalogs'])
PAGE_SIZE = 12


def _resolve_catalog_image_url(item: dict) -> str | None:
    if item.get('preview_public_url'):
        return item['preview_public_url']
    local_path = item.get('preview_local_path')
    if not local_path:
        return None
    file_name = Path(local_path).name
    return f"{web_settings.catalogs_url_prefix.rstrip('/')}/{file_name}"


@router.get('')
@require_login
async def catalogs_list(
    request: Request,
    page: int = Query(1),
    query: str = Query(''),
    date_from: str = Query(''),
    date_to: str = Query(''),
    export: str | None = Query(None),
):
    clauses = ['1=1']
    args: list = []
    if query.strip():
        like = f"%{query.strip()}%"
        clauses.append('(c.title LIKE %s OR c.tags_text LIKE %s OR u.full_name LIKE %s OR u.username LIKE %s)')
        args.extend([like, like, like, like])
    if date_from.strip():
        clauses.append('DATE(c.created_at) >= %s')
        args.append(date_from.strip())
    if date_to.strip():
        clauses.append('DATE(c.created_at) <= %s')
        args.append(date_to.strip())
    where_sql = ' AND '.join(clauses)
    base_query = f'''
        SELECT c.*, u.full_name, u.username,
               (SELECT cp.photo_public_url FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_public_url,
               (SELECT cp.photo_local_path FROM catalog_photos cp WHERE cp.catalog_id = c.id ORDER BY cp.id ASC LIMIT 1) AS preview_local_path,
               (SELECT COUNT(*) FROM catalog_photos cp WHERE cp.catalog_id = c.id) AS photos_count
        FROM catalogs c
        JOIN users u ON u.id = c.user_id
        WHERE {where_sql}
        ORDER BY c.created_at DESC
    '''
    count_query = f'''SELECT COUNT(*) AS cnt FROM catalogs c JOIN users u ON u.id=c.user_id WHERE {where_sql}'''
    data = await paginate_query(base_query, count_query, tuple(args), parse_page(page), PAGE_SIZE)
    for item in data['items']:
        item['preview_image_url'] = _resolve_catalog_image_url(item)
    if export == 'xlsx':
        rows = [[i['id'], i.get('title') or '', i.get('tags_text') or '', i.get('full_name') or i.get('username') or '', i['created_at'], i.get('photos_count') or 0] for i in data['items']]
        content = build_workbook('Catalogs', ['ID', 'Название', 'Теги', 'Создатель', 'Дата', 'Фото'], rows)
        return Response(content=content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename=catalogs.xlsx'})
    return render(request, 'catalogs.html', {
        'data': data,
        'filters': {'query': query, 'date_from': date_from, 'date_to': date_to},
    })
