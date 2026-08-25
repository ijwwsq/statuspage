"""Точка входа statuspage. Автономный FastAPI-сервис."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (регистрация моделей в Base.metadata)
from . import notify
from .config import settings
from .db import Base, SessionLocal, engine
from .monitor import run_monitor
from .routes_admin import router as admin_router
from .routes_public import router as public_router
from .service import seed_subscribers, sync_components

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.split("///", 1)[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_components(db)
        seed_subscribers(db)
        db.commit()
    tasks = [asyncio.create_task(run_monitor())]
    if settings.telegram_bot_token and settings.telegram_poll:
        tasks.append(asyncio.create_task(notify.run_poll()))
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()


app = FastAPI(title=settings.brand.title, docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def _revalidate_static(request, call_next):
    # статика ревалидируется каждый раз (304 если не менялась) — правки видны без ручной чистки кэша
    resp = await call_next(request)
    if request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(public_router)
app.include_router(admin_router)
