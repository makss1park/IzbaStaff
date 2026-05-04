from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates

from web.dependencies import current_admin

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / 'templates'))


def render(request, template_name: str, context: dict[str, Any]):
    base_context = {'request': request, 'current_admin': current_admin(request)}
    base_context.update(context)
    return TEMPLATES.TemplateResponse(template_name, base_context)
