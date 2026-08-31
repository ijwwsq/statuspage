"""Telegram-уведомления об инцидентах + обработка /start /stop от бота."""
import asyncio
import html

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import cache
from .config import settings
from .db import SessionLocal
from .models import Incident, Subscriber

_STATUS_LABELS = {
    "investigating": "Investigating",
    "identified": "Identified",
    "monitoring": "Monitoring",
    "resolved": "Resolved",
}
_IMPACT_LABELS = {
    "none": "none",
    "minor": "minor",
    "major": "major",
    "critical": "critical",
}
_IMPACT_EMOJI = {
    "none": "⚪",
    "minor": "🟡",
    "major": "🟠",
    "critical": "🔴",
}


async def _api(method: str, payload: dict) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] telegram {method} failed: {exc}")


async def _send(chat_id: str, text: str, markup: dict | None = None) -> None:
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup:
        p["reply_markup"] = markup
    await _api("sendMessage", p)


async def _edit(chat_id: str, message_id, text: str, markup: dict | None = None) -> None:
    p = {"chat_id": chat_id, "message_id": message_id, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup:
        p["reply_markup"] = markup
    await _api("editMessageText", p)


async def _answer(cq_id: str, text: str | None = None) -> None:
    p = {"callback_query_id": cq_id}
    if text:
        p["text"] = text
    await _api("answerCallbackQuery", p)


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s" if sec else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


_STATUS_EMOJI = {
    "investigating": "🔍", "identified": "📌", "monitoring": "👀", "resolved": "✅",
}


def _format(inc: Incident) -> str:
    if inc.status == "resolved":
        head = "✅ <b>Recovered</b>"
    elif inc.type == "maintenance":
        head = "🛠 <b>Scheduled maintenance</b>"
    else:
        head = f"{_IMPACT_EMOJI.get(inc.impact, '🟠')} <b>Incident</b>"

    lines = [head, f"<b>{html.escape(inc.title)}</b>", ""]

    if inc.updates:
        lines.append(html.escape(inc.updates[-1].body))
        lines.append("")

    meta = [f"{_STATUS_EMOJI.get(inc.status, '•')} {_STATUS_LABELS.get(inc.status, inc.status)}"]
    if inc.type != "maintenance":
        meta.append(f"impact — {_IMPACT_LABELS.get(inc.impact, inc.impact)}")
    lines.append(" · ".join(meta))

    if inc.components:
        lines.append("Affected: " + ", ".join(html.escape(c.component.name) for c in inc.components))

    if inc.status == "resolved" and inc.created_at and inc.resolved_at:
        downtime = (inc.resolved_at - inc.created_at).total_seconds()
        if downtime > 0:
            lines.append(f"🕒 Downtime: {_fmt_duration(downtime)}")

    if settings.public_base_url:
        lines.append("")
        lines.append(f'<a href="{settings.public_base_url}">Open the status page →</a>')

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
    "operational": "operational", "degraded": "degraded", "partial_outage": "partial outage",
    "major_outage": "major outage", "maintenance": "maintenance", "unknown": "no data",
}
_HELP = (
    "Commands:\n"
    "/status — summary + inline control panel\n"
    "/components — list and statuses\n"
    "/up /down /degraded /partial /maint /auto <key> — component status\n"
    "/incident [minor|major|critical] <title> — open an incident\n"
    "/maintenance <title> — scheduled maintenance (suppresses auto-alerts)\n"
    "/update <text> — add an update to the latest incident\n"
    "/resolve — close the latest incident\n"
    "/start /stop — subscribe to notifications"
)


def _st(status: str) -> str:
    return _COMP_LABELS.get(status, status)


_COMP_EMOJI = {"operational": "🟢", "degraded": "🟡", "partial_outage": "🟠",
               "major_outage": "🔴", "maintenance": "🔵", "unknown": "⚪"}
_OVERALL_EMOJI = {"operational": "🟢", "minor": "🟡", "major": "🔴", "maintenance": "🔵"}
_SET_CODE = {"op": "operational", "dg": "degraded", "pt": "partial_outage",
             "mj": "major_outage", "mn": "maintenance", "au": None}


def _status_text(summary: dict) -> str:
    o = summary["overall"]
    lines = [f'{_OVERALL_EMOJI.get(o["level"], "⚪")} <b>{html.escape(o["label"])}</b>', ""]
    for g in summary["groups"]:
        lines.append(f'<b>{html.escape(g["name"])}</b>')
        for c in g["components"]:
            up = "" if c["uptime"] is None else f'  <i>{c["uptime"]:.2f}%</i>'
            lines.append(f'{_COMP_EMOJI.get(c["status"], "⚪")} {html.escape(c["name"])}{up}')
        lines.append("")
    inc = summary.get("incidents", [])
    if inc:
        lines.append(f"⚠️ Active incidents — {len(inc)}:")
        lines += [f'• {html.escape(i["title"])}' for i in inc[:5]]
    else:
        lines.append("No active incidents.")
    return "\n".join(lines).strip()


def _main_kb(is_admin: bool) -> dict:
    rows = [[{"text": "🔄 Refresh", "callback_data": "rf"}]]
    if is_admin:
        rows.append([{"text": "🧩 Components", "callback_data": "cp"},
                     {"text": "✅ Resolve incident", "callback_data": "rs"}])
    return {"inline_keyboard": rows}


def _comps_kb(components: list[dict]) -> dict:
    rows = [[{"text": f'{_COMP_EMOJI.get(c["status"], "⚪")} {c["name"]}',
              "callback_data": f'c:{c["key"]}'}] for c in components]
    rows.append([{"text": "‹ Back", "callback_data": "rf"}])
    return {"inline_keyboard": rows}


def _set_kb(key: str) -> dict:
    opts = [("🟢 Operational", "op"), ("🟡 Degraded", "dg"), ("🔴 Outage", "mj"),
            ("🔵 Maintenance", "mn"), ("↩︎ Auto", "au")]
    rows = [[{"text": t, "callback_data": f's:{key}:{code}'}] for t, code in opts]
    rows.append([{"text": "‹ To components", "callback_data": "cp"}])
    return {"inline_keyboard": rows}


async def handle_callback(db: Session, cq: dict) -> None:
    """Инлайн-кнопки: обновить сводку, менять статусы, закрыть инцидент."""
    from . import schemas, service
    data = cq.get("data", "")
    msg = cq.get("message") or {}
    chat = str((msg.get("chat") or {}).get("id") or "")
    mid = msg.get("message_id")
    is_admin = chat in settings.telegram_admin_chat_ids
    await _answer(cq.get("id"))
    if not chat or not mid:
        return

    def snap():
        return _status_text(cache.get(lambda: service.get_summary(db)))

    if data == "rf":
        await _edit(chat, mid, snap(), _main_kb(is_admin))
    elif not is_admin:
        return
    elif data == "cp":
        await _edit(chat, mid, "Pick a component:", _comps_kb(service.list_components(db)))
    elif data.startswith("c:"):
        await _edit(chat, mid, f"Status for “{html.escape(data[2:])}”:", _set_kb(data[2:]))
    elif data.startswith("s:"):
        _, key, code = data.split(":", 2)
        service.set_component_status(db, key, _SET_CODE.get(code))
        cache.invalidate()
        await _edit(chat, mid, snap(), _main_kb(is_admin))
    elif data == "rs":
        inc = service.latest_open_incident(db)
        if inc:
            inc = service.add_update(db, inc.id, schemas.IncidentUpdateCreate(body="Resolved.", status="resolved"))
            cache.invalidate()
            await notify_incident(db, inc)
        await _edit(chat, mid, snap(), _main_kb(is_admin))


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
        extra = "\n\nYou're an admin — /help for controls." if chat_id in settings.telegram_admin_chat_ids else ""
        await _send(chat_id, "You're subscribed to status notifications. /stop to unsubscribe." + extra)
        return
    if cmd == "/stop":
        db.query(Subscriber).filter(
            Subscriber.channel == "telegram", Subscriber.target == chat_id
        ).delete()
        db.commit()
        await _send(chat_id, "You've unsubscribed from notifications.")
        return
    if cmd in ("/status", "/menu"):
        summary = cache.get(lambda: service.get_summary(db))
        await _send(chat_id, _status_text(summary),
                    _main_kb(chat_id in settings.telegram_admin_chat_ids))
        return

    if chat_id in settings.telegram_admin_chat_ids:
        await _admin_command(db, chat_id, text, service, schemas)


async def _admin_command(db: Session, chat_id: str, text: str, service, schemas) -> None:
    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]
    reply = "Unknown command. /help"
    try:
        if cmd == "/help":
            reply = _HELP
        elif cmd == "/components":
            rows = service.list_components(db)
            reply = "Components:\n" + "\n".join(f"• {c['key']} — {_st(c['status'])}" for c in rows)
        elif cmd in _COMP_CMD or cmd == "/auto":
            if not args:
                reply = "Specify a key, e.g. /down api"
            else:
                status = None if cmd == "/auto" else _COMP_CMD[cmd]
                res = service.set_component_status(db, args[0], status)
                reply = f"{args[0]} → {_st(res['status'])}"
        elif cmd in ("/incident", "/maintenance"):
            if not args:
                reply = f"Title, e.g. {cmd} major Database is unavailable"
            else:
                impact = "major"
                title_parts = args
                if args[0].lower() in ("none", "minor", "major", "critical"):
                    impact, title_parts = args[0].lower(), args[1:]
                title = " ".join(title_parts).strip() or "Incident"
                typ = "maintenance" if cmd == "/maintenance" else "incident"
                body = "Scheduled maintenance." if typ == "maintenance" else "Incident opened manually."
                inc = service.create_incident(db, schemas.IncidentCreate(
                    title=title, body=body, impact=impact, type=typ, status="investigating"))
                await notify_incident(db, inc)
                reply = ("🛠 Maintenance: " if typ == "maintenance" else "Incident: ") + title
        elif cmd == "/update":
            body = " ".join(args).strip()
            inc = service.latest_open_incident(db)
            if not inc:
                reply = "No open incidents."
            elif not body:
                reply = "Text: /update investigating the root cause"
            else:
                inc = service.add_update(db, inc.id, schemas.IncidentUpdateCreate(body=body, status=inc.status))
                await notify_incident(db, inc)
                reply = "Update added."
        elif cmd == "/resolve":
            inc = service.latest_open_incident(db)
            if not inc:
                reply = "No open incidents."
            else:
                inc = service.add_update(db, inc.id, schemas.IncidentUpdateCreate(
                    body="Resolved.", status="resolved"))
                await notify_incident(db, inc)
                reply = f"Closed: {inc.title}"
    except Exception as exc:  # noqa: BLE001
        reply = f"Error: {str(exc)[:150]}"
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
                        if "callback_query" in upd:
                            await handle_callback(db, upd["callback_query"])
                        else:
                            await handle_update(db, upd)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[notify] handle error: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"[notify] poll error: {exc}")
            await asyncio.sleep(2)
