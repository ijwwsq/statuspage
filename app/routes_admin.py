"""Admin-роуты. Авторизация — независимый токен (STATUS_ADMIN_TOKEN), ноль связей с приложением-хостом."""
import hmac
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from . import cache, notify, schemas, service
from .config import settings
from .db import SessionLocal

router = APIRouter(prefix="/api/admin")

# рейт-лимит логина: попытки по IP
_login_attempts: dict[str, list[float]] = {}
_LOGIN_MAX = 5
_LOGIN_WINDOW = 60.0


def get_db():
    with SessionLocal() as db:
        yield db


def require_admin(request: Request) -> bool:
    token = request.headers.get("X-Status-Token") or request.cookies.get("status_admin")
    if not token or not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(401, "unauthorized")
    return True


def require_csrf(request: Request) -> bool:
    """Double-submit: заголовок X-CSRF должен совпадать с cookie status_csrf."""
    header = request.headers.get("X-CSRF") or ""
    cookie = request.cookies.get("status_csrf") or ""
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(403, "csrf")
    return True


# зависимость для мутаций: авторизация + CSRF (только для cookie-аутентификации) + сброс кэша
def guard(request: Request):
    require_admin(request)
    # заголовок-токен уже CSRF-safe (кросс-сайт его не поставит); CSRF нужен только для cookie
    if not request.headers.get("X-Status-Token"):
        require_csrf(request)
    cache.invalidate()
    return True


@router.post("/login")
def login(body: schemas.Login, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    now = time.time()
    hits = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW]
    if len(hits) >= _LOGIN_MAX:
        raise HTTPException(429, "too many attempts")
    if not hmac.compare_digest(body.token, settings.admin_token):
        hits.append(now)
        _login_attempts[ip] = hits
        raise HTTPException(401, "bad token")
    _login_attempts.pop(ip, None)
    kw = dict(samesite="lax", secure=settings.cookie_secure, max_age=60 * 60 * 24 * 7)
    response.set_cookie("status_admin", body.token, httponly=True, **kw)
    response.set_cookie("status_csrf", secrets.token_urlsafe(24), httponly=False, **kw)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("status_admin")
    response.delete_cookie("status_csrf")
    return {"ok": True}


@router.get("/session", dependencies=[Depends(require_admin)])
def session_ok():
    return {"ok": True}


@router.get("/components", dependencies=[Depends(require_admin)])
def components(db=Depends(get_db)):
    return service.list_components(db)


@router.post("/components/{key}/status", dependencies=[Depends(guard)])
def set_component_status(key: str, body: schemas.ComponentStatus, db=Depends(get_db)):
    return service.set_component_status(db, key, body.status)


@router.get("/incidents", dependencies=[Depends(require_admin)])
def incidents(db=Depends(get_db)):
    return service.list_incidents(db)


@router.post("/incidents", dependencies=[Depends(guard)])
async def create_incident(body: schemas.IncidentCreate, db=Depends(get_db)):
    inc = service.create_incident(db, body)
    cache.invalidate()
    await notify.notify_incident(db, inc)
    return service.incident_dict(inc)


@router.post("/incidents/{incident_id}/updates", dependencies=[Depends(guard)])
async def add_update(incident_id: int, body: schemas.IncidentUpdateCreate, db=Depends(get_db)):
    inc = service.add_update(db, incident_id, body)
    cache.invalidate()
    await notify.notify_incident(db, inc)
    return service.incident_dict(inc)
