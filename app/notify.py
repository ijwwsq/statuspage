"""Telegram-уведомления об инцидентах + обработка /start /stop от бота."""
import asyncio
import html

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Incident, Subscriber

_STATUS_LABELS = {
    "investigating": "Расследуем",
    "identified": "Причина найдена",
    "monitoring": "Наблюдаем",
    "resolved": "Устранено",
}
_IMPACT_LABELS = {
    "none": "нет",
    "minor": "незначительное",
    "major": "серьёзное",
    "critical": "критическое",
}
_IMPACT_EMOJI = {
    "none": "⚪",
    "minor": "🟡",
    "major": "🟠",
    "critical": "🔴",
}


async def _send(chat_id: str, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] telegram send failed: {exc}")


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} с"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {sec} с" if sec else f"{minutes} мин"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин"


def _format(inc: Incident) -> str:
    if inc.status == "resolved":
        head = "✅ Восстановлено"
    elif inc.type == "maintenance":
        head = "🛠 Плановые работы"
    else:
        head = f"{_IMPACT_EMOJI.get(inc.impact, '🟠')} Инцидент"
    last = inc.updates[-1].body if inc.updates else ""
    lines = [
        f"<b>{head}: {html.escape(inc.title)}</b>",
        f"Статус: {_STATUS_LABELS.get(inc.status, inc.status)}"
        f" · Влияние: {_IMPACT_LABELS.get(inc.impact, inc.impact)}",
        html.escape(last),
    ]
    if inc.status == "resolved" and inc.created_at and inc.resolved_at:
        downtime = (inc.resolved_at - inc.created_at).total_seconds()
        if downtime > 0:
            lines.append(f"🕒 Время простоя: {_fmt_duration(downtime)}")
    if inc.components:
        lines.append("Затронуто: " + ", ".join(html.escape(c.component.name) for c in inc.components))
    if settings.public_base_url:
        lines.append(settings.public_base_url)
    return "\n".join(x for x in lines if x)


async def notify_incident(db: Session, inc: Incident) -> None:
    targets = db.scalars(
        select(Subscriber.target).where(Subscriber.channel == "telegram")
    ).all()
    if not targets:
        return
    text = _format(inc)
    for chat_id in targets:
        await _send(chat_id, text)


async def handle_update(db: Session, update: dict) -> None:
    """Мини-обработчик вебхука бота: /start подписывает, /stop отписывает."""
    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    text = (msg.get("text") or "").strip()
    if not chat_id:
        return
    if text.startswith("/start"):
        exists = db.scalar(
            select(Subscriber).where(
                Subscriber.channel == "telegram", Subscriber.target == chat_id
            )
        )
        if not exists:
            db.add(Subscriber(channel="telegram", target=chat_id))
            db.commit()
        await _send(chat_id, "Вы подписаны на уведомления о статусе. /stop — отписаться.")
    elif text.startswith("/stop"):
        db.query(Subscriber).filter(
            Subscriber.channel == "telegram", Subscriber.target == chat_id
        ).delete()
        db.commit()
        await _send(chat_id, "Вы отписались от уведомлений.")


async def run_poll() -> None:
    """Long-poll getUpdates — подписка через бота (/start) без публичного вебхука."""
    if not settings.telegram_bot_token:
        return
    base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    offset = 0
    async with httpx.AsyncClient(timeout=40) as client:
        while True:
            try:
                r = await client.get(
                    base + "/getUpdates", params={"offset": offset, "timeout": 30}
                )
                for upd in r.json().get("result", []):
                    offset = upd["update_id"] + 1
                    with SessionLocal() as db:
                        await handle_update(db, upd)
            except Exception as exc:  # noqa: BLE001
                print(f"[notify] poll error: {exc}")
                await asyncio.sleep(3)
