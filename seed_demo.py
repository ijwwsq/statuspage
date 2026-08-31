"""Демо-данные: 90 дней аптайма (100%) + исторические инциденты/сбои + плановые работы.

Идемпотентно: чистит проверки и инциденты, заливает заново (подписчики сохраняются).
Запуск:  python seed_demo.py
         docker exec <контейнер> python seed_demo.py
"""
import datetime as dt
import math

from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.models import Check, Component, Incident, IncidentComponent, IncidentUpdate
from app.service import sync_components

DAYS = 90
PER_DAY = [0, 4, 8, 12, 16, 20]                     # 6 проверок в день
BASE = {'website': 20, 'api': 45, 'auth': 30, 'database': 6,
        'cache': 4, 'queue': 12, 'cdn': 25, 'email': 60}

# (days ago, key, impact, title, detail, full day down?, downtime hours)
INCIDENTS = [
    (58, 'api', 'major', 'API outage', 'A share of requests returned 5xx', True, 3),
    (41, 'cdn', 'major', 'CDN unavailable', 'Static assets and media failed to load for users', True, 2),
    (27, 'cache', 'minor', 'Cache slowdown', 'Elevated response times due to memory eviction', False, 1),
    (14, 'website', 'major', 'Website unavailable', 'The site failed to open — 502 from the load balancer', True, 4),
    (6, 'auth', 'minor', 'Sign-in errors', 'Some users could not authenticate', False, 1),
]


def _updates(impact, detail):
    if impact == 'minor':
        return [('investigating', detail + '. Looking into it.'),
                ('resolved', 'Resolved, the service is back to normal.')]
    return [('investigating', detail + '. Investigating.'),
            ('identified', 'Root cause identified, applying a fix.'),
            ('monitoring', 'Fix applied, monitoring the metrics.'),
            ('resolved', 'Incident resolved, the service is operating normally.')]


def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_components(db)
        db.commit()
        for t in (IncidentUpdate, IncidentComponent, Incident, Check):
            db.query(t).delete()
        db.commit()

        comps = [(c.id, c.key) for c in db.scalars(
            select(Component).where(Component.enabled.is_(True))).all()]
        cid = {k: i for i, k in comps}
        now = dt.datetime.now(dt.timezone.utc)

        # аптайм 100% за 90 дней
        for c_id, key in comps:
            b = BASE.get(key, 20)
            for da in range(0, DAYS):
                day = now - dt.timedelta(days=da)
                for h in PER_DAY:
                    ts = day.replace(hour=h, minute=2, second=0, microsecond=0)
                    db.add(Check(component_id=c_id, ts=ts, ok=True,
                                 latency_ms=round(b * (1 + 0.08 * math.sin(da / 7.0)) + (h % 5) * 0.3, 1)))
        db.commit()

        # исторические инциденты + провалы аптайма на те дни
        for da, key, impact, title, detail, fullday, dur in INCIDENTS:
            day = now - dt.timedelta(days=da)
            ds = day.date().isoformat()
            checks = db.scalars(select(Check).where(
                Check.component_id == cid[key], func.date(Check.ts) == ds).order_by(Check.ts)).all()
            for ch in (checks if fullday else checks[:1]):
                ch.ok = False
                ch.latency_ms = None
                ch.error = 'HTTP 503'
            start = day.replace(hour=9, minute=0, second=0, microsecond=0)
            inc = Incident(title=title, type='incident', impact=impact, status='resolved', auto=False)
            inc.created_at = start
            inc.resolved_at = start + dt.timedelta(hours=dur)
            db.add(inc)
            db.flush()
            ups = _updates(impact, detail)
            for i, (st, body) in enumerate(ups):
                db.add(IncidentUpdate(incident_id=inc.id, status=st, body=body,
                                      created_at=start + dt.timedelta(hours=dur * i / max(len(ups) - 1, 1))))
            db.add(IncidentComponent(incident_id=inc.id, component_id=cid[key]))

        # плановые работы (без простоя)
        m_day = (now - dt.timedelta(days=20)).replace(hour=2, minute=0, second=0, microsecond=0)
        m = Incident(title='Scheduled database upgrade', type='maintenance',
                     impact='minor', status='resolved', auto=False)
        m.created_at = m_day
        m.resolved_at = m_day + dt.timedelta(hours=1, minutes=30)
        db.add(m)
        db.flush()
        db.add(IncidentUpdate(incident_id=m.id, status='investigating',
                              body='PostgreSQL upgrade. Brief unavailability is possible.', created_at=m_day))
        db.add(IncidentUpdate(incident_id=m.id, status='resolved',
                              body='Maintenance complete, the database is operating normally.', created_at=m.resolved_at))
        db.add(IncidentComponent(incident_id=m.id, component_id=cid['database']))

        # живой статус: без внешних сервисов монитор молчит — проставляем «работает» вручную,
        # чтобы демо было зелёным и самодостаточным (иначе все компоненты «нет данных»)
        for c_id, _ in comps:
            db.get(Component, c_id).monitored_status = 'operational'
        db.commit()

        print(f'seeded: проверок {db.query(Check).count()}, инцидентов {db.query(Incident).count()}')


if __name__ == '__main__':
    main()
