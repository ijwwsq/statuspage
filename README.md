<div align="center">

# statuspage

**A self-hosted status page you can drop into any project.**
Active health-checks, 90-day uptime history, incidents & maintenance, response-time
charts, and Telegram notifications — one small FastAPI service, no SaaS, no external
dependencies beyond a database.

[![CI](https://github.com/ijwwsq/statuspage/actions/workflows/ci.yml/badge.svg)](https://github.com/ijwwsq/statuspage/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-18794D.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3d9a63.svg)](https://www.python.org/)
[![Docker ready](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)

[English](README.md) · [Русский](README.ru.md)

<img src="docs/screenshot-light.png" alt="statuspage — public status page" width="820">

</div>

---

## Why

Hosted status pages are a subscription for something that is fundamentally a small app:
ping a few URLs, store the results, draw some bars, post to a chat when something breaks.
**statuspage is that small app** — self-contained, drop-in, and yours.

- **One service.** FastAPI + SQLAlchemy + Jinja + httpx. No Redis, no Celery, no build step.
- **Drop-in.** Every table is `status_*`-prefixed; its own auth, its own DB, its own
  lifecycle. Copy the folder into any project and it minds its own business.
- **SQLite by default**, Postgres when you need it — schema & indexes are created on
  boot, no migration tool required.
- **`docker compose up` → a fully populated demo** in seconds.

## Features

| | |
|---|---|
| **Active monitor** | Background loop pings each component's `check_url` (HTTP **or** `tcp://host:port`) on an interval, records probes, and computes daily uptime. |
| **90-day uptime** | Per-component bars at 24h / 30d / 90d granularity, a GitHub-style monthly calendar, and response-time charts from real probes. |
| **Auto-incidents** | Opens an incident after N consecutive failures, closes it after N recoveries — with flap protection and maintenance suppression. |
| **Manual control** | Web admin (token-auth, CSRF, login rate-limit) to post incidents, maintenance windows, and per-component status overrides. |
| **Degraded detection** | A slow-but-200 response is flagged “Degraded” (amber) instead of a hard outage, using a latency threshold. |
| **Telegram** | Subscribe via the bot; incident create/update/resolve is pushed to subscribers. Full admin panel *inside* the chat — commands **and** inline buttons. |
| **Brandable** | Name, title, accent color, logo, footer — all from `config.json` or env. |
| **Light & dark** | Themes follow the viewer's OS setting; the brand accent applies to both. |

## Screenshots

Dark theme follows the viewer's OS setting:

<div align="center">
<img src="docs/screenshot-dark.png" alt="Status page in dark theme" width="820">
</div>

The whole page — live status, a 90-day uptime calendar, and full incident history:

<div align="center">
<img src="docs/screenshot-full.png" alt="Full status page with uptime calendar and incident history" width="720">
</div>

## Quickstart

### Demo in one command

```bash
docker compose up
```

Open **<http://localhost:8090>** — a status page pre-loaded with 90 days of uptime,
five historical incidents, and a maintenance window. Admin panel at
**<http://localhost:8090/admin>** (token `demo123`).

### Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
STATUS_ADMIN_TOKEN=secret uvicorn app.main:app --port 8090
```

Want the demo data locally too?

```bash
STATUS_CONFIG_FILE=config.demo.json python seed_demo.py
```

## Configuration

**Components & branding** live in [`config.json`](config.json).
**Secrets & tuning** come from environment variables (see [`.env.example`](.env.example)).

```jsonc
{
  "brand": {
    "name": "Acme Cloud · Status",
    "accent": "#18794D",                       // brand color, applied across the page
    "logo": "/static/logo.svg"                 // your logo, shown in the header (see below)
  },
  "metrics": ["website", "api", "cdn"],        // which components get response-time charts
  "components": [
    { "key": "website", "name": "Website", "group": "Platform",
      "check_url": "https://example.com", "expected_status": 200 },
    { "key": "database", "name": "Database", "group": "Infrastructure" }
    //  ^ no check_url → status is set manually from the admin panel
  ]
}
```

### Logo & branding

Point `brand.logo` at any image and it renders in the page header:

- **Bundled file** — drop `logo.svg` (or `.png`) into `app/static/` and set
  `"logo": "/static/logo.svg"` (the demo ships one this way).
- **External URL** — `"logo": "https://…/logo.png"` works too.
- Leave it `null` to show just the brand name.

`accent` recolors the page; `footer_note` adds a line in the footer; `support_url` and
`telegram_url` add header/footer links. All of it can also be overridden via env
(`STATUS_BRAND_NAME`, `STATUS_ACCENT`, `STATUS_BRAND_LOGO`, …).

Key environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `STATUS_ADMIN_TOKEN` | `change-me` | Admin panel token — **set this in production** |
| `STATUS_DATABASE_URL` | `sqlite:///./data/statuspage.db` | SQLite file or `postgresql+psycopg2://…` |
| `STATUS_CHECK_INTERVAL` | `60` | Seconds between health checks |
| `STATUS_HISTORY_DAYS` | `90` | Retention horizon for probes |
| `STATUS_ALERT_AFTER` | `3` | Consecutive failures before an auto-incident |
| `STATUS_RECOVER_AFTER` | `2` | Consecutive successes before auto-resolve |
| `STATUS_DEGRADED_MS` | `1500` | Slower-than-this 2xx responses are marked “Degraded” |
| `STATUS_TELEGRAM_BOT_TOKEN` | — | Enables Telegram notifications & bot |
| `STATUS_COOKIE_SECURE` | `false` | Set `true` behind HTTPS |

Full list with comments: [`.env.example`](.env.example).

## How monitoring works

Every `STATUS_CHECK_INTERVAL` seconds the monitor probes each component with a `check_url`:

- **HTTP/S** — a `GET` (or configured method); `ok` when the status equals `expected_status`.
- **TCP** — `tcp://host:port`; `ok` when the port accepts a connection (for databases, caches, pools).

Each probe is stored, feeding the uptime bars, the calendar, and the latency charts.
A component **without** a `check_url` is controlled only from the admin panel — handy for
things you can't cheaply ping. A manual status always overrides the monitor.

## Telegram

Set `STATUS_TELEGRAM_BOT_TOKEN` and pick a delivery mode:

- **Long-poll** (no public URL needed): `STATUS_TELEGRAM_POLL=true`.
- **Webhook**: point Telegram at `POST /telegram/webhook/<STATUS_TELEGRAM_WEBHOOK_SECRET>`.

Users `/start` the bot to subscribe. Chats listed in `STATUS_TELEGRAM_ADMIN_CHAT_IDS`
get an in-chat control panel — `/status` renders a live summary with inline buttons to
flip component statuses and resolve incidents, plus text commands (`/incident`,
`/maintenance`, `/update`, `/resolve`, …).

## Deployment notes

- **Postgres in prod:** set `STATUS_DATABASE_URL` to a `postgresql+psycopg2://…` DSN and
  add `psycopg2-binary` to your image. Tables and indexes are created idempotently on boot.
- **Single process:** the monitor keeps flap-protection state in memory, so run **one**
  instance. It's designed to be tiny and vertical, not horizontally sharded.
- **HTTPS:** set `STATUS_COOKIE_SECURE=true` so admin cookies are marked `Secure`.

## Architecture

```
app/
  config.py        # env + config.json → Settings
  db.py            # engine (SQLite/Postgres), WAL pragmas
  models.py        # status_* tables
  monitor.py       # active health-checker + auto-incident logic
  notify.py        # Telegram notifications, bot commands, inline panel
  service.py       # summary builder + incident operations (+ pure helpers)
  cache.py         # short-TTL summary cache with manual invalidation
  routes_public.py # public page, /api/summary, Telegram webhook
  routes_admin.py  # token-auth admin API (CSRF, rate-limit)
  main.py          # app assembly + lifespan (monitor & poller)
  templates/       # index.html, admin.html
  static/          # plain ES modules + one CSS file, no build step
config.json        # components + branding
config.demo.json   # self-contained demo config (used by seed_demo.py)
seed_demo.py       # generates 90 days of showcase data
```

## Testing

```bash
pytest -q
```

Pure logic (`day_status`, `overall`) and service operations are covered on in-memory
SQLite — no network, no external services. CI runs the suite on Python 3.11 & 3.12 and
smoke-boots the Docker image.

## Contributing

Issues and PRs welcome — please keep it lean. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © ijwwsq
