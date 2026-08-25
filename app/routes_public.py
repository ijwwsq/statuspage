"""Публичные роуты: страница, JSON-сводка, Telegram-вебхук."""
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import notify, service
from .config import settings
from .db import SessionLocal

# короткий TTL-кэш сводки: дедуплицирует расчёт при поллинге и множестве зрителей
_SUMMARY_TTL = 5.0
_summary_cache: dict = {"ts": 0.0, "data": None}

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
    now = time.monotonic()
    if _summary_cache["data"] is None or now - _summary_cache["ts"] > _SUMMARY_TTL:
        _summary_cache["data"] = service.get_summary(db)
        _summary_cache["ts"] = now
    return JSONResponse(_summary_cache["data"])


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request, db=Depends(get_db)):
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise HTTPException(404)
    await notify.handle_update(db, await request.json())
    return {"ok": True}
