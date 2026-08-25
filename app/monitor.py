"""Активный монитор: пингует health-URL компонентов, пишет пробы, чистит старьё."""
import asyncio
import datetime as dt
import time

import httpx
from sqlalchemy import select

from . import notify, service
from .config import settings
from .db import SessionLocal
from .models import Check, Component, Incident, now

# подряд неудачных проверок и момент начала падения по компоненту (в памяти процесса)
_fails: dict[int, int] = {}
_down_since: dict[int, object] = {}


async def _probe_tcp(url: str):
    """tcp://host:port — проверка доступности порта (БД, кэш, пул)."""
    t0 = time.perf_counter()
    host, _, port = url[len("tcp://"):].partition(":")
    try:
        fut = asyncio.open_connection(host, int(port))
        _, writer = await asyncio.wait_for(fut, timeout=settings.check_timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True, (time.perf_counter() - t0) * 1000, None
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)[:290]


async def _probe(client: httpx.AsyncClient, method: str, url: str, expected: int):
    if url.startswith("tcp://"):
        return await _probe_tcp(url)
    t0 = time.perf_counter()
    try:
        r = await client.request(method, url, timeout=settings.check_timeout)
        latency = (time.perf_counter() - t0) * 1000
        ok = r.status_code == expected
        return ok, latency, None if ok else f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)[:290]


async def _tick() -> None:
    with SessionLocal() as db:
        comps = [
            {
                "id": c.id,
                "method": c.method,
                "url": c.check_url,
                "expected": c.expected_status,
            }
            for c in db.scalars(
                select(Component).where(Component.enabled.is_(True))
            ).all()
            if c.check_url
        ]
    if not comps:
        return

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_probe(client, c["method"], c["url"], c["expected"]) for c in comps]
        )

    to_notify: list[int] = []
    with SessionLocal() as db:
        for c, (ok, latency, error) in zip(comps, results):
            db.add(Check(component_id=c["id"], ok=ok, latency_ms=latency, error=error))
            comp = db.get(Component, c["id"])
            if not comp:
                continue
            comp.monitored_status = "operational" if ok else "major_outage"

            if ok:
                _fails[c["id"]] = 0
                _down_since.pop(c["id"], None)
                inc = service.auto_resolve_incident(db, comp)  # закрыть, если был авто-инцидент
                if inc:
                    to_notify.append(inc.id)
            else:
                if _fails.get(c["id"], 0) == 0:
                    _down_since[c["id"]] = now()  # первый упавший пинг
                _fails[c["id"]] = _fails.get(c["id"], 0) + 1
                if _fails[c["id"]] >= settings.alert_after:
                    inc = service.auto_open_incident(db, comp, _down_since.get(c["id"]))
                    if inc:
                        to_notify.append(inc.id)
        db.commit()

    for iid in to_notify:
        with SessionLocal() as db:
            inc = db.get(Incident, iid)
            if inc:
                await notify.notify_incident(db, inc)


def _prune() -> None:
    cutoff = now() - dt.timedelta(days=settings.history_days)
    with SessionLocal() as db:
        db.query(Check).filter(Check.ts < cutoff).delete()
        db.commit()


async def run_monitor() -> None:
    last_prune = 0.0
    while True:
        try:
            await _tick()
            if time.time() - last_prune > 3600:  # чистка старья раз в час, не каждый тик
                _prune()
                last_prune = time.time()
        except Exception as exc:  # noqa: BLE001
            print(f"[monitor] error: {exc}")
        await asyncio.sleep(settings.check_interval)
