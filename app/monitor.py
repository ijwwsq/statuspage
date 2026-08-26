"""Активный монитор: пингует health-URL компонентов, пишет пробы, чистит старьё."""
import asyncio
import datetime as dt
import time

import httpx
from sqlalchemy import select

from . import cache, notify, service
from .config import settings
from .db import SessionLocal
from .models import Check, Component, Incident, now

# состояние по компоненту (в памяти процесса)
_fails: dict[int, int] = {}          # неудач подряд
_oks: dict[int, int] = {}            # успехов подряд (для закрытия)
_down_since: dict[int, object] = {}  # момент начала падения
_resolved_at: dict[int, float] = {}  # когда закрыли авто-инцидент (кулдаун от флапа)


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
            cid = c["id"]
            db.add(Check(component_id=cid, ok=ok, latency_ms=latency, error=error))
            comp = db.get(Component, cid)
            if not comp:
                continue

            if ok:
                # медленно, но 2xx → «Замедление» (жёлтый), не сбой
                slow = latency is not None and latency > settings.degraded_ms
                comp.monitored_status = "degraded" if slow else "operational"
                _fails[cid] = 0
                _down_since.pop(cid, None)
                _oks[cid] = _oks.get(cid, 0) + 1
                # закрываем авто-инцидент только после N успехов подряд (защита от флапа)
                if _oks[cid] >= settings.recover_after:
                    inc = service.auto_resolve_incident(db, comp)
                    if inc:
                        to_notify.append(inc.id)
                        _resolved_at[cid] = time.time()
            else:
                comp.monitored_status = "major_outage"
                _oks[cid] = 0
                if _fails.get(cid, 0) == 0:
                    _down_since[cid] = now()
                _fails[cid] = _fails.get(cid, 0) + 1
                in_cooldown = time.time() - _resolved_at.get(cid, 0.0) < settings.flap_cooldown
                # не заводим инцидент: при работах, в кулдауне после недавнего закрытия
                if (_fails[cid] >= settings.alert_after
                        and not in_cooldown
                        and not service.is_under_maintenance(db, comp.id)):
                    inc = service.auto_open_incident(db, comp, _down_since.get(cid))
                    if inc:
                        to_notify.append(inc.id)
        db.commit()

    if to_notify:
        cache.invalidate()  # инциденты изменились — показать сразу
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
