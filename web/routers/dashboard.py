from __future__ import annotations

import json

from fastapi import APIRouter, Request

from web.dependencies import require_login
from web.routers.common import render
from web.services.metrics import dashboard_metrics

router = APIRouter(prefix='/web', tags=['dashboard'])


@router.get('')
@require_login
async def dashboard(request: Request):
    metrics = await dashboard_metrics()
    return render(
        request,
        'dashboard.html',
        {
            'summary': metrics['summary'],
            'salary_chart_json': json.dumps(metrics['salary_chart'], default=float, ensure_ascii=False),
            'top_staff': metrics['top_staff'],
            'lateness_json': json.dumps(metrics['lateness'], default=float, ensure_ascii=False),
        },
    )
