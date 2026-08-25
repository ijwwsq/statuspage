"""Admin-роуты. Авторизация — независимый токен (STATUS_ADMIN_TOKEN), ноль связей с порталом."""
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from . import notify, schemas, service
from .config import settings
from .db import SessionLocal

router = APIRouter(prefix="/api/admin")


def get_db():
    with SessionLocal() as db:
        yield db


def require_admin(request: Request) -> bool:
    token = request.headers.get("X-Status-Token") or request.cookies.get("status_admin")
    if not token or not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(401, "unauthorized")
    return True


@router.post("/login")
def login(body: schemas.Login, response: Response):
    if not hmac.compare_digest(body.token, settings.admin_token):
        raise HTTPException(401, "bad token")
    response.set_cookie(
        "status_admin", body.token, httponly=True, samesite="lax",
        secure=settings.cookie_secure, max_age=60 * 60 * 24 * 7,
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("status_admin")
    return {"ok": True}


@router.get("/session", dependencies=[Depends(require_admin)])
def session_ok():
    return {"ok": True}


@router.get("/components", dependencies=[Depends(require_admin)])
def components(db=Depends(get_db)):
    return service.list_components(db)


@router.post("/components/{key}/status", dependencies=[Depends(require_admin)])
def set_component_status(key: str, body: schemas.ComponentStatus, db=Depends(get_db)):
    return service.set_component_status(db, key, body.status)


@router.get("/incidents", dependencies=[Depends(require_admin)])
def incidents(db=Depends(get_db)):
    return service.list_incidents(db)


@router.post("/incidents", dependencies=[Depends(require_admin)])
async def create_incident(body: schemas.IncidentCreate, db=Depends(get_db)):
    inc = service.create_incident(db, body)
    await notify.notify_incident(db, inc)
    return service.incident_dict(inc)


@router.post("/incidents/{incident_id}/updates", dependencies=[Depends(require_admin)])
async def add_update(incident_id: int, body: schemas.IncidentUpdateCreate, db=Depends(get_db)):
    inc = service.add_update(db, incident_id, body)
    await notify.notify_incident(db, inc)
    return service.incident_dict(inc)
