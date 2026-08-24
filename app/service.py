"""Бизнес-логика: синхронизация компонентов, сборка публичной сводки, операции с инцидентами.

Чистые хелперы day_status/overall вынесены отдельно и покрыты тестом.
"""
import datetime as dt

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    Check,
    Component,
    Incident,
    IncidentComponent,
    IncidentUpdate,
    Subscriber,
    now,
)
from .schemas import (
    COMPONENT_STATUSES,
    IMPACTS,
    INCIDENT_STATUSES,
    IncidentCreate,
    IncidentUpdateCreate,
)

# ранг тяжести статуса компонента (для вычисления общего статуса)
_RANK = {
    "operational": 0,
    "unknown": 0,
    "maintenance": 1,
    "degraded": 2,
    "partial_outage": 3,
    "major_outage": 4,
}


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


# ---- чистые хелперы (тестируются без БД) --------------------------------------

def day_status(up: int, total: int) -> tuple[str, float | None]:
    """Статус одного дня по числу успешных/всех проверок."""
    if not total:
        return "unknown", None
    ratio = up / total
    if ratio >= 1:
        return "up", 1.0
    if ratio <= 0:
        return "down", 0.0
    return "partial", ratio


def overall(components: list[dict], has_active_incident: bool) -> dict:
    """Общий статус витрины из статусов компонентов и наличия активных инцидентов."""
    worst = max((_RANK.get(c["status"], 0) for c in components), default=0)
    if worst >= _RANK["major_outage"]:
        return {"level": "major", "label": "Серьёзные сбои в работе"}
    if worst >= _RANK["degraded"]:
        return {"level": "minor", "label": "Частичные проблемы в работе"}
    if has_active_incident:
        return {"level": "minor", "label": "Есть активный инцидент"}
    if worst >= _RANK["maintenance"]:
        return {"level": "maintenance", "label": "Плановые работы"}
    return {"level": "operational", "label": "Все системы работают"}


# ---- синхронизация из конфига -------------------------------------------------

def sync_components(db: Session) -> None:
    """Upsert компонентов из config.json; отсутствующие в конфиге — выключаются."""
    keys = {c.key for c in settings.components}
    for cd in settings.components:
        row = db.scalar(select(Component).where(Component.key == cd.key))
        if row is None:
            row = Component(key=cd.key)
            db.add(row)
        row.name = cd.name
        row.group = cd.group
        row.description = cd.description
        row.check_url = cd.check_url
        row.method = cd.method
        row.expected_status = cd.expected_status
        row.order = cd.order
        row.enabled = True
    for row in db.scalars(select(Component)).all():
        if row.key not in keys:
            row.enabled = False


def seed_subscribers(db: Session) -> None:
    for chat_id in settings.telegram_seed_chat_ids:
        exists = db.scalar(
            select(Subscriber).where(
                Subscriber.channel == "telegram", Subscriber.target == chat_id
            )
        )
        if not exists:
            db.add(Subscriber(channel="telegram", target=chat_id))


# ---- сводка для публичной страницы -------------------------------------------

def _uptime_map(db: Session, component_id: int, days: int) -> dict[str, tuple[int, int]]:
    since = now() - dt.timedelta(days=days)
    day = func.date(Check.ts)
    rows = db.execute(
        select(
            day,
            func.count(),
            func.sum(case((Check.ok, 1), else_=0)),
        )
        .where(Check.component_id == component_id, Check.ts >= since)
        .group_by(day)
    ).all()
    result: dict[str, tuple[int, int]] = {}
    for d, total, up in rows:
        key = d if isinstance(d, str) else d.isoformat()
        result[key] = (int(up or 0), int(total or 0))
    return result


def _day_keys(days: int) -> list[str]:
    today = now().date()
    return [(today - dt.timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _component_payload(db: Session, comp: Component, days: int) -> dict:
    umap = _uptime_map(db, comp.id, days)
    total_up = total_all = 0
    day_bars = []
    for key in _day_keys(days):
        up, total = umap.get(key, (0, 0))
        st, frac = day_status(up, total)
        total_up += up
        total_all += total
        day_bars.append(
            {"date": key, "status": st, "uptime": None if frac is None else round(frac * 100, 3)}
        )
    uptime_pct = round(total_up / total_all * 100, 3) if total_all else None
    return {
        "key": comp.key,
        "name": comp.name,
        "description": comp.description,
        "status": comp.status,
        "monitored": comp.check_url is not None,
        "uptime": uptime_pct,
        "days": day_bars,
    }


def incident_dict(inc: Incident) -> dict:
    return {
        "id": inc.id,
        "title": inc.title,
        "type": inc.type,
        "status": inc.status,
        "impact": inc.impact,
        "created_at": _iso(inc.created_at),
        "resolved_at": _iso(inc.resolved_at),
        "scheduled_for": _iso(inc.scheduled_for),
        "scheduled_until": _iso(inc.scheduled_until),
        "components": [
            {"key": c.component.key, "name": c.component.name} for c in inc.components
        ],
        "updates": [
            {"body": u.body, "status": u.status, "created_at": _iso(u.created_at)}
            for u in inc.updates
        ],
    }


def _metrics(db: Session, days: int) -> list[dict]:
    since = now() - dt.timedelta(days=days)
    day = func.date(Check.ts)
    out: list[dict] = []
    for key in settings.metric_keys:  # компоненты графиков — из конфига
        comp = db.scalar(
            select(Component).where(Component.key == key, Component.enabled.is_(True))
        )
        if not comp:
            continue
        rows = db.execute(
            select(day, func.avg(Check.latency_ms))
            .where(
                Check.component_id == comp.id,
                Check.ok.is_(True),
                Check.latency_ms.is_not(None),
                Check.ts >= since,
            )
            .group_by(day)
            .order_by(day)
        ).all()
        points = [
            {"date": (d if isinstance(d, str) else d.isoformat()), "value": round(float(v), 1)}
            for d, v in rows
            if v is not None
        ]
        if points:
            out.append({"key": comp.key, "name": comp.name, "unit": "мс", "points": points})
    return out


def get_summary(db: Session) -> dict:
    days = settings.history_days
    comps = db.scalars(
        select(Component)
        .where(Component.enabled.is_(True))
        .order_by(Component.group, Component.order)
    ).all()

    groups: dict[str, list[dict]] = {}
    flat: list[dict] = []
    for comp in comps:
        payload = _component_payload(db, comp, days)
        flat.append(payload)
        groups.setdefault(comp.group, []).append(payload)

    active = db.scalars(
        select(Incident)
        .where(Incident.type == "incident", Incident.status != "resolved")
        .order_by(Incident.created_at.desc())
    ).all()
    maintenance = db.scalars(
        select(Incident)
        .where(Incident.type == "maintenance", Incident.status != "resolved")
        .order_by(Incident.scheduled_for)
    ).all()
    since = now() - dt.timedelta(days=days)
    history = db.scalars(
        select(Incident)
        .where(Incident.status == "resolved", Incident.resolved_at >= since)
        .order_by(Incident.resolved_at.desc())
    ).all()

    return {
        "generated_at": _iso(now()),
        "brand": {
            "name": settings.brand.name,
            "telegram_url": settings.brand.telegram_url,
            "accent": settings.brand.accent,
            "footer_note": settings.brand.footer_note,
        },
        "overall": overall(flat, bool(active)),
        "metrics": _metrics(db, days),
        "groups": [{"name": name, "components": items} for name, items in groups.items()],
        "incidents": [incident_dict(i) for i in active],
        "maintenance": [incident_dict(i) for i in maintenance],
        "history": [incident_dict(i) for i in history],
        "history_days": days,
    }


# ---- операции admin -----------------------------------------------------------

def create_incident(db: Session, body: IncidentCreate) -> Incident:
    if body.status not in INCIDENT_STATUSES:
        raise HTTPException(422, "bad status")
    if body.impact not in IMPACTS:
        raise HTTPException(422, "bad impact")
    inc = Incident(
        title=body.title,
        type="maintenance" if body.type == "maintenance" else "incident",
        status=body.status,
        impact=body.impact,
        scheduled_for=body.scheduled_for,
        scheduled_until=body.scheduled_until,
    )
    db.add(inc)
    db.flush()
    db.add(IncidentUpdate(incident_id=inc.id, body=body.body, status=body.status))
    for key in body.component_keys:
        comp = db.scalar(select(Component).where(Component.key == key))
        if comp:
            db.add(IncidentComponent(incident_id=inc.id, component_id=comp.id))
    db.commit()
    db.refresh(inc)
    return inc


def add_update(db: Session, incident_id: int, body: IncidentUpdateCreate) -> Incident:
    if body.status not in INCIDENT_STATUSES:
        raise HTTPException(422, "bad status")
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "incident not found")
    db.add(IncidentUpdate(incident_id=inc.id, body=body.body, status=body.status))
    inc.status = body.status
    if body.status == "resolved":
        inc.resolved_at = now()
        for link in inc.components:  # снять ручные override с затронутых компонентов
            comp = db.get(Component, link.component_id)
            if comp:
                comp.manual_status = None
    db.commit()
    db.refresh(inc)
    return inc


def set_component_status(db: Session, key: str, status: str | None) -> dict:
    if status and status not in COMPONENT_STATUSES:
        raise HTTPException(422, "bad status")
    comp = db.scalar(select(Component).where(Component.key == key))
    if not comp:
        raise HTTPException(404, "component not found")
    comp.manual_status = status or None
    db.commit()
    return {"key": comp.key, "status": comp.status}


def _open_auto_incident(db: Session, component_id) -> Incident | None:
    return db.scalar(
        select(Incident)
        .join(IncidentComponent, IncidentComponent.incident_id == Incident.id)
        .where(
            Incident.auto.is_(True),
            Incident.status != "resolved",
            IncidentComponent.component_id == component_id,
        )
    )


def auto_open_incident(db: Session, comp: Component, started_at=None) -> Incident | None:
    """Монитор: завести инцидент по падению компонента (если ещё не заведён).

    started_at — момент первого упавшего пинга (для корректного времени простоя).
    """
    if _open_auto_incident(db, comp.id):
        return None
    inc = Incident(
        title=f"Недоступен: {comp.name}",
        type="incident", impact="major", status="investigating", auto=True,
    )
    if started_at:
        inc.created_at = started_at
    db.add(inc)
    db.flush()
    db.add(IncidentUpdate(
        incident_id=inc.id, status="investigating",
        body=f"Автоматически обнаружено: «{comp.name}» не отвечает на проверки доступности.",
    ))
    db.add(IncidentComponent(incident_id=inc.id, component_id=comp.id))
    db.commit()
    db.refresh(inc)
    return inc


def auto_resolve_incident(db: Session, comp: Component) -> Incident | None:
    """Монитор: закрыть авто-инцидент при восстановлении компонента."""
    inc = _open_auto_incident(db, comp.id)
    if not inc:
        return None
    db.add(IncidentUpdate(
        incident_id=inc.id, status="resolved",
        body=f"Автоматически: «{comp.name}» снова отвечает. Инцидент закрыт.",
    ))
    inc.status = "resolved"
    inc.resolved_at = now()
    db.commit()
    db.refresh(inc)
    return inc


def list_incidents(db: Session) -> list[dict]:
    rows = db.scalars(select(Incident).order_by(Incident.created_at.desc())).all()
    return [incident_dict(i) for i in rows]


def list_components(db: Session) -> list[dict]:
    rows = db.scalars(select(Component).order_by(Component.group, Component.order)).all()
    return [
        {
            "key": c.key,
            "name": c.name,
            "group": c.group,
            "status": c.status,
            "monitored_status": c.monitored_status,
            "manual_status": c.manual_status,
            "enabled": c.enabled,
        }
        for c in rows
    ]
