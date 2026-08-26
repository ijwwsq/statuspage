"""Конфигурация statuspage.

Всё гибко: секреты и параметры — из env, компоненты и брендинг — из config.json.
Перенос на другой проект = копипаст пакета + правка config.json (+ env).
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_COMPONENT_FIELDS = {
    "key", "name", "group", "description",
    "check_url", "method", "expected_status", "order",
}


def _env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


@dataclass
class Brand:
    name: str = "Status"
    title: str = "Статус сервисов"
    logo: str | None = None
    support_url: str | None = None
    telegram_url: str | None = None
    tagline: str | None = None
    accent: str | None = None          # акцентный цвет (CSS), напр. "#18794D"
    footer_note: str | None = None     # текст в подвале страницы


@dataclass
class ComponentDef:
    key: str
    name: str
    group: str = "Сервисы"
    description: str | None = None
    check_url: str | None = None
    method: str = "GET"
    expected_status: int = 200
    order: int = 0


@dataclass
class Settings:
    database_url: str
    admin_token: str
    check_interval: int
    check_timeout: int
    history_days: int
    alert_after: int
    recover_after: int
    flap_cooldown: int
    degraded_ms: int
    telegram_bot_token: str | None
    telegram_webhook_secret: str | None
    telegram_poll: bool
    telegram_seed_chat_ids: list[str]
    telegram_admin_chat_ids: list[str]
    public_base_url: str | None
    cookie_secure: bool
    metric_keys: list[str]
    brand: Brand
    components: list[ComponentDef] = field(default_factory=list)


def load_settings() -> Settings:
    cfg_path = Path(_env("STATUS_CONFIG_FILE", str(BASE_DIR / "config.json")))
    data: dict = {}
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))

    b = data.get("brand", {})
    brand = Brand(
        name=_env("STATUS_BRAND_NAME", b.get("name", "Status")),
        title=_env("STATUS_PAGE_TITLE", b.get("title", "Статус сервисов")),
        logo=_env("STATUS_BRAND_LOGO", b.get("logo")),
        support_url=_env("STATUS_SUPPORT_URL", b.get("support_url")),
        telegram_url=_env("STATUS_TELEGRAM_URL", b.get("telegram_url")),
        tagline=b.get("tagline"),
        accent=_env("STATUS_ACCENT", b.get("accent")),
        footer_note=b.get("footer_note"),
    )

    components: list[ComponentDef] = []
    for i, raw in enumerate(data.get("components", [])):
        clean = {k: v for k, v in raw.items() if k in _COMPONENT_FIELDS}
        cd = ComponentDef(**clean)
        if not cd.order:
            cd.order = i
        components.append(cd)

    seed = _env("STATUS_TELEGRAM_CHAT_IDS", "") or ""
    seed_ids = [x.strip() for x in seed.split(",") if x.strip()]
    admin_seed = _env("STATUS_TELEGRAM_ADMIN_CHAT_IDS", "") or ""
    admin_ids = [x.strip() for x in admin_seed.split(",") if x.strip()] or seed_ids
    return Settings(
        database_url=_env("STATUS_DATABASE_URL", "sqlite:///./data/statuspage.db"),
        admin_token=_env("STATUS_ADMIN_TOKEN", "change-me"),
        check_interval=int(_env("STATUS_CHECK_INTERVAL", "60")),
        check_timeout=int(_env("STATUS_CHECK_TIMEOUT", "10")),
        history_days=int(_env("STATUS_HISTORY_DAYS", "90")),
        alert_after=int(_env("STATUS_ALERT_AFTER", "3")),
        recover_after=int(_env("STATUS_RECOVER_AFTER", "2")),
        flap_cooldown=int(_env("STATUS_FLAP_COOLDOWN", "300")),
        degraded_ms=int(_env("STATUS_DEGRADED_MS", "1500")),
        telegram_bot_token=_env("STATUS_TELEGRAM_BOT_TOKEN") or None,
        telegram_webhook_secret=_env("STATUS_TELEGRAM_WEBHOOK_SECRET") or None,
        telegram_poll=(_env("STATUS_TELEGRAM_POLL", "false") or "").lower() in ("1", "true", "yes"),
        telegram_seed_chat_ids=seed_ids,
        telegram_admin_chat_ids=admin_ids,
        public_base_url=_env("STATUS_PUBLIC_BASE_URL") or None,
        cookie_secure=(_env("STATUS_COOKIE_SECURE", "false") or "").lower() in ("1", "true", "yes"),
        metric_keys=data.get("metrics") or ["gateway", "portal-api", "tableau"],
        brand=brand,
        components=components,
    )


settings = load_settings()
