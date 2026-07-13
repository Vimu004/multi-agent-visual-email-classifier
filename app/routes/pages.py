"""HTML page routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import UIStatus, get_settings

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _ui_status() -> UIStatus:
    settings = get_settings()
    if settings.use_fake_model:
        return UIStatus(provider_label="Local Demo Mode", is_demo_mode=True)
    return UIStatus(provider_label="Azure GPT-5.4 Nano", is_demo_mode=False)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html", {"request": request, "ui_status": _ui_status()}
    )


@router.get("/architecture", response_class=HTMLResponse)
async def architecture(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "architecture.html", {"request": request, "ui_status": _ui_status()}
    )


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "history.html", {"request": request, "ui_status": _ui_status()}
    )


@router.get("/workflows/{workflow_id}", response_class=HTMLResponse)
async def workflow_detail(request: Request, workflow_id: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "workflow.html",
        {"request": request, "workflow_id": workflow_id, "ui_status": _ui_status()},
    )
