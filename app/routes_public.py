"""Публичные роуты: страница, JSON-сводка, Telegram-вебхук."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import cache, notify, service
from .config import settings
from .db import SessionLocal

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter()


def get_db():
    with SessionLocal() as db:
        yield db


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"brand": settings.brand})


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html", {"brand": settings.brand})


@router.get("/api/summary")
def api_summary(db=Depends(get_db)):
    return JSONResponse(cache.get(lambda: service.get_summary(db)))


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request, db=Depends(get_db)):
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise HTTPException(404)
    await notify.handle_update(db, await request.json())
    return {"ok": True}
