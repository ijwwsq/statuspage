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


_STATUS_EMOJI = {
    "investigating": "🔍", "identified": "📌", "monitoring": "👀", "resolved": "✅",
}


def _format(inc: Incident) -> str:
    if inc.status == "resolved":
        head = "✅ <b>Восстановлено</b>"
    elif inc.type == "maintenance":
        head = "🛠 <b>Плановые работы</b>"
    else:
        head = f"{_IMPACT_EMOJI.get(inc.impact, '🟠')} <b>Инцидент</b>"

    lines = [head, f"<b>{html.escape(inc.title)}</b>", ""]

    if inc.updates:
        lines.append(html.escape(inc.updates[-1].body))
        lines.append("")

    meta = [f"{_STATUS_EMOJI.get(inc.status, '•')} {_STATUS_LABELS.get(inc.status, inc.status)}"]
    if inc.type != "maintenance":
        meta.append(f"влияние — {_IMPACT_LABELS.get(inc.impact, inc.impact)}")
    lines.append(" · ".join(meta))

    if inc.components:
        lines.append("Затронуто: " + ", ".join(html.escape(c.component.name) for c in inc.components))

    if inc.status == "resolved" and inc.created_at and inc.resolved_at:
        downtime = (inc.resolved_at - inc.created_at).total_seconds()
        if downtime > 0:
            lines.append(f"🕒 Время простоя: {_fmt_duration(downtime)}")

    if settings.public_base_url:
        lines.append("")
        lines.append(f'<a href="{settings.public_base_url}">Открыть статус-страницу →</a>')

    return "\n".join(lines)


async def notify_incident(db: Session, inc: Incident) -> None:
    targets = db.scalars(
        select(Subscriber.target).where(Subscriber.channel == "telegram")
    ).all()
    if not targets:
        return
    text = _format(inc)
    for chat_id in targets:
        await _send(chat_id, text)


_COMP_CMD = {
    "/up": "operational",
    "/down": "major_outage",
    "/degraded": "degraded",
    "/partial": "partial_outage",
    "/maint": "maintenance",
}
_COMP_LABELS = {
    "operational": "работает", "degraded": "замедление", "partial_outage": "частичный сбой",
    "major_outage": "сбой", "maintenance": "работы", "unknown": "нет данных",
}
_HELP = (
    "Админ-команды:\n"
    "/components — список и статусы\n"
    "/up /down /degraded /partial /maint /auto <ключ> — статус компонента\n"
    "/incident [minor|major|critical] <заголовок> — завести инцидент\n"
    "/maintenance <заголовок> — плановые работы (гасят авто-алерты)\n"
    "/update <текст> — обновление к последнему инциденту\n"
    "/resolve — закрыть последний инцидент\n"
    "/start /stop — подписка на уведомления"
)


def _st(status: str) -> str:
    return _COMP_LABELS.get(status, status)


async def handle_update(db: Session, update: dict) -> None:
    """Обработчик апдейтов бота: подписка (/start /stop) и админ-команды из доверенных чатов."""
    from . import schemas, service

    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    cmd = text.split()[0].lower()

    if cmd == "/start":
        exists = db.scalar(
            select(Subscriber).where(
                Subscriber.channel == "telegram", Subscriber.target == chat_id
            )
        )
        if not exists:
            db.add(Subscriber(channel="telegram", target=chat_id))
            db.commit()
        extra = "\n\nВы админ — /help для управления." if chat_id in settings.telegram_admin_chat_ids else ""
        await _send(chat_id, "Вы подписаны на уведомления о статусе. /stop — отписаться." + extra)
        return
    if cmd == "/stop":
        db.query(Subscriber).filter(
            Subscriber.channel == "telegram", Subscriber.target == chat_id
        ).delete()
        db.commit()
        await _send(chat_id, "Вы отписались от уведомлений.")
        return

    if chat_id in settings.telegram_admin_chat_ids:
        await _admin_command(db, chat_id, text, service, schemas)


async def _admin_command(db: Session, chat_id: str, text: str, service, schemas) -> None:
    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]
    reply = "Неизвестная команда. /help"
    try:
        if cmd == "/help":
            reply = _HELP
        elif cmd == "/components":
            rows = service.list_components(db)
            reply = "Компоненты:\n" + "\n".join(f"• {c['key']} — {_st(c['status'])}" for c in rows)
        elif cmd in _COMP_CMD or cmd == "/auto":
            if not args:
                reply = "Укажи ключ: напр. /down portal-api"
            else:
                status = None if cmd == "/auto" else _COMP_CMD[cmd]
                res = service.set_component_status(db, args[0], status)
                reply = f"{args[0]} → {_st(res['status'])}"
        elif cmd in ("/incident", "/maintenance"):
            if not args:
                reply = f"Заголовок: напр. {cmd} major База данных недоступна"
            else:
                impact = "major"
                title_parts = args
                if args[0].lower() in ("none", "minor", "major", "critical"):
                    impact, title_parts = args[0].lower(), args[1:]
                title = " ".join(title_parts).strip() or "Инцидент"
                typ = "maintenance" if cmd == "/maintenance" else "incident"
                body = "Плановые работы." if typ == "maintenance" else "Инцидент заведён вручную."
                inc = service.create_incident(db, schemas.IncidentCreate(
                    title=title, body=body, impact=impact, type=typ, status="investigating"))
                await notify_incident(db, inc)
                reply = ("🛠 Работы: " if typ == "maintenance" else "Инцидент: ") + title
        elif cmd == "/update":
            body = " ".join(args).strip()
            inc = service.latest_open_incident(db)
            if not inc:
                reply = "Нет открытых инцидентов."
            elif not body:
                reply = "Текст: /update расследуем причину"
            else:
                inc = service.add_update(db, inc.id, schemas.IncidentUpdateCreate(body=body, status=inc.status))
                await notify_incident(db, inc)
                reply = "Обновление добавлено."
        elif cmd == "/resolve":
            inc = service.latest_open_incident(db)
            if not inc:
                reply = "Нет открытых инцидентов."
            else:
                inc = service.add_update(db, inc.id, schemas.IncidentUpdateCreate(
                    body="Устранено.", status="resolved"))
                await notify_incident(db, inc)
                reply = f"Закрыто: {inc.title}"
    except Exception as exc:  # noqa: BLE001
        reply = f"Ошибка: {str(exc)[:150]}"
    await _send(chat_id, reply)


async def run_poll() -> None:
    """Long-poll getUpdates — подписка через бота (/start) без публичного вебхука."""
    if not settings.telegram_bot_token:
        return
    base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    offset = 0
    timeout = httpx.Timeout(35.0, connect=10.0)
    while True:
        try:
            # свежий клиент на каждый long-poll — иначе протухшее соединение рвётся
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(base + "/getUpdates", params={"offset": offset, "timeout": 25})
            for upd in r.json().get("result", []):
                offset = upd["update_id"] + 1
                with SessionLocal() as db:
                    try:
                        await handle_update(db, upd)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[notify] handle error: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[notify] poll error: {exc}")
            await asyncio.sleep(2)
