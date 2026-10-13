from __future__ import annotations

from fastapi import APIRouter, Query, Request

from core.repositories import catalogs as catalogs_repo
from web.dependencies import require_login
from web.routers.common import render
from web.services.excel import xlsx_response
from web.services.files import catalog_photo_url, catalog_preview_url
from web.services.query import parse_page

router = APIRouter(prefix='/web/catalogs', tags=['catalogs'])
PAGE_SIZE = 12


async def _attach_catalog_photos(items: list[dict]) -> None:
    if not items:
        return
    catalog_ids = [int(item['id']) for item in items]
    grouped: dict[int, list[dict]] = {catalog_id: [] for catalog_id in catalog_ids}
    for photo in await catalogs_repo.list_photos_for_catalogs(catalog_ids):
        photo['image_url'] = catalog_photo_url(photo)
        grouped.setdefault(int(photo['catalog_id']), []).append(photo)
    for item in items:
        item['photos'] = grouped.get(int(item['id']), [])


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
    data = await catalogs_repo.search_page(
        query=query, date_from=date_from, date_to=date_to, page=parse_page(page), page_size=PAGE_SIZE
    )
    for item in data['items']:
        item['preview_image_url'] = catalog_preview_url(item)
    await _attach_catalog_photos(data['items'])

    if export == 'xlsx':
        rows = [
            [i['id'], i.get('title') or '', i.get('tags_text') or '', i.get('full_name') or i.get('username') or '', i['created_at'], i.get('photos_count') or 0]
            for i in data['items']
        ]
        return xlsx_response('catalogs.xlsx', 'Catalogs', ['ID', 'Название', 'Теги', 'Создатель', 'Дата', 'Фото'], rows)

    return render(request, 'catalogs.html', {
        'data': data,
        'filters': {'query': query, 'date_from': date_from, 'date_to': date_to},
    })
