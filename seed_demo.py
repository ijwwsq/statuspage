"""Демо-наполнение: история проверок (для аптайм-полосок) + инциденты + плановые работы.

Идемпотентно: чистит status_checks / status_incident* и заливает заново.
Запуск (из services/statuspage):
    STATUS_DATABASE_URL=sqlite:///./data/demo.db STATUS_CONFIG_FILE=./config.demo.json \
        python seed_demo.py
"""
import datetime as dt
import math

from app.db import Base, SessionLocal, engine
from app.models import (
    Check,
    Component,
    Incident,
    IncidentComponent,
    IncidentUpdate,
)
from app.service import sync_components

DAYS = 90
SAMPLES_PER_DAY = 24  # почасово

# провалы доступности: (ключ компонента, дней назад) -> сколько часов было "down"
DIPS = {
    ("portal-api", 10): 8,
    ("tableau", 32): 10,
    ("redis", 20): 3,
    ("frontend", 0): 3,
    ("frontend", 55): 4,
    ("gateway", 70): 1,
}

# итоговые текущие статусы компонентов (остальные — operational по умолчанию)
CURRENT = {
    "frontend": "degraded",
}

# базовое время ответа компонента, мс (для графиков метрик)
BASE_LATENCY = {
    "gateway": 16, "frontend": 40, "portal-api": 60, "auth": 26,
    "postgres": 5, "pgbouncer": 6, "redis": 3, "tableau": 180,
}


def _latency(key: str, days_ago: int, hour: int, elevated: bool) -> float:
    base = BASE_LATENCY.get(key, 30)
    wave = 1 + 0.12 * math.sin(days_ago / 6.0) + 0.05 * math.sin(hour / 3.0)
    val = base * wave
    if elevated:
        val *= 1.9  # в дни инцидента время ответа выше
    return round(val, 1)


def _midnight_utc(days_ago: int) -> dt.datetime:
    d = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days_ago)
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def seed_checks(db) -> int:
    comps = db.query(Component).all()
    rows = 0
    for comp in comps:
        for days_ago in range(DAYS):
            down = DIPS.get((comp.key, days_ago), 0)
            base = _midnight_utc(days_ago)
            for hour in range(SAMPLES_PER_DAY):
                ok = hour >= down  # первые `down` часов дня — сбой
                db.add(
                    Check(
                        component_id=comp.id,
                        ts=base + dt.timedelta(hours=hour, minutes=1),
                        ok=ok,
                        latency_ms=_latency(comp.key, days_ago, hour, down > 0) if ok else None,
                        error=None if ok else "HTTP 502",
                    )
                )
                rows += 1
        comp.monitored_status = CURRENT.get(comp.key, "operational")
    return rows


def _incident(db, *, title, type_, impact, days_ago, comp_keys, updates, resolved,
              scheduled_for=None, scheduled_until=None):
    start = _midnight_utc(days_ago) + dt.timedelta(hours=9)
    inc = Incident(
        title=title,
        type=type_,
        impact=impact,
        status=updates[-1][0],
        scheduled_for=scheduled_for,
        scheduled_until=scheduled_until,
    )
    inc.created_at = start
    if resolved:
        inc.resolved_at = start + dt.timedelta(hours=len(updates))
    db.add(inc)
    db.flush()
    for i, (status, body) in enumerate(updates):
        db.add(
            IncidentUpdate(
                incident_id=inc.id,
                status=status,
                body=body,
                created_at=start + dt.timedelta(hours=i),
            )
        )
    for key in comp_keys:
        comp = db.query(Component).filter_by(key=key).first()
        if comp:
            db.add(IncidentComponent(incident_id=inc.id, component_id=comp.id))
    return inc


def seed_incidents(db) -> None:
    # 1. крупный, разрешён 32 дня назад — Tableau
    _incident(
        db,
        title="Недоступность встраивания дашбордов Tableau",
        type_="incident",
        impact="major",
        days_ago=32,
        comp_keys=["tableau"],
        resolved=True,
        updates=[
            ("investigating", "Пользователи сообщают об ошибке загрузки дашбордов. Разбираемся."),
            ("identified", "Причина — истёк сертификат Connected App на стороне BI. Готовим замену."),
            ("monitoring", "Сертификат обновлён, встраивание восстановлено. Наблюдаем."),
            ("resolved", "Инцидент устранён. Встраивание работает штатно."),
        ],
    )
    # 2. небольшой, разрешён 10 дней назад — API
    _incident(
        db,
        title="Замедленные ответы API каталога",
        type_="incident",
        impact="minor",
        days_ago=10,
        comp_keys=["portal-api"],
        resolved=True,
        updates=[
            ("investigating", "Наблюдаем повышенное время ответа каталога."),
            ("identified", "Всплеск нагрузки на пул соединений БД. Увеличиваем пул."),
            ("resolved", "Пул расширен, время ответа в норме."),
        ],
    )
    # 3. небольшой, разрешён 20 дней назад — Redis
    _incident(
        db,
        title="Кратковременная недоступность кэша",
        type_="incident",
        impact="minor",
        days_ago=20,
        comp_keys=["redis"],
        resolved=True,
        updates=[
            ("investigating", "Redis не отвечает на часть запросов, растёт время ответа портала."),
            ("identified", "Достигнут лимит памяти, сработала политика вытеснения. Поднимаем лимит."),
            ("resolved", "Лимит памяти увеличен, кэш работает штатно."),
        ],
    )
    # 4. активный сейчас — фронтенд
    _incident(
        db,
        title="Периодические ошибки загрузки интерфейса",
        type_="incident",
        impact="minor",
        days_ago=0,
        comp_keys=["frontend"],
        resolved=False,
        updates=[
            ("investigating", "Часть пользователей видит ошибку при открытии портала. Разбираемся."),
            ("monitoring", "Выкатили исправление, следим за метриками ошибок."),
        ],
    )
    # 4. плановые работы (в будущем)
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)
    _incident(
        db,
        title="Плановое обновление базы данных",
        type_="maintenance",
        impact="minor",
        days_ago=0,
        comp_keys=["postgres", "portal-api"],
        resolved=False,
        scheduled_for=future,
        scheduled_until=future + dt.timedelta(hours=2),
        updates=[
            ("investigating", "Запланировано обновление PostgreSQL. Возможна недоступность до 2 часов."),
        ],
    )


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_components(db)
        db.commit()
        # чистим прошлые демо-данные
        db.query(IncidentComponent).delete()
        db.query(IncidentUpdate).delete()
        db.query(Incident).delete()
        db.query(Check).delete()
        db.commit()

        rows = seed_checks(db)
        seed_incidents(db)
        db.commit()
        print(f"seeded: {rows} проб, инциденты и плановые работы")


if __name__ == "__main__":
    main()
