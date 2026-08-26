"""Тесты сервисных операций на in-memory SQLite (без сети)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, service
from app.db import Base
from app.schemas import IncidentCreate, IncidentUpdateCreate


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        s.add(models.Component(key="api", name="API", group="G"))
        s.commit()
        yield s


def _comp(db):
    return db.query(models.Component).first()


def test_maintenance_suppresses(db):
    comp = _comp(db)
    assert service.is_under_maintenance(db, comp.id) is False
    service.create_incident(db, IncidentCreate(
        title="Работы", body="x", type="maintenance", impact="minor", status="investigating"))
    # глобальные работы (без компонентов) гасят всё
    assert service.is_under_maintenance(db, comp.id) is True


def test_auto_open_resolve(db):
    comp = _comp(db)
    inc = service.auto_open_incident(db, comp)
    assert inc is not None and inc.status == "investigating" and inc.auto is True
    assert service.auto_open_incident(db, comp) is None            # повторно не заводит
    res = service.auto_resolve_incident(db, comp)
    assert res is not None and res.status == "resolved"
    assert service.auto_resolve_incident(db, comp) is None         # закрывать нечего


def test_add_update_resolves(db):
    inc = service.create_incident(db, IncidentCreate(
        title="Сбой", body="init", impact="major", status="investigating", component_keys=["api"]))
    assert service.latest_open_incident(db).id == inc.id
    service.add_update(db, inc.id, IncidentUpdateCreate(body="готово", status="resolved"))
    assert service.latest_open_incident(db) is None


def test_manual_status_override(db):
    service.set_component_status(db, "api", "major_outage")
    assert _comp(db).status == "major_outage"
    service.set_component_status(db, "api", None)                  # снять оверрайд
    assert _comp(db).status == "unknown"
