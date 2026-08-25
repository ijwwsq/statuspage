# statuspage — автономная витрина статуса

Самописный status page: компоненты, аптайм (90-дневные полоски), инциденты с таймлайном,
плановые работы, Telegram-уведомления. Один сервис, без внешних зависимостей кроме БД.
Переносится на другой проект копипастом `services/statuspage/` + правкой `config.json`.

## Что внутри

- **Активный монитор** — фоновый цикл пингует `check_url` каждого компонента раз в
  `STATUS_CHECK_INTERVAL` секунд, пишет пробы, считает аптайм по дням, чистит старьё за
  горизонтом `STATUS_HISTORY_DAYS`.
- **Компоненты** — задаются в `config.json`, upsert в БД при старте. Компонент без `check_url`
  (напр. postgres) статус получает только вручную из админки.
- **Инциденты и работы** — создаются в админке, статусы `investigating → identified →
  monitoring → resolved`, влияние `none/minor/major/critical`, таймлайн обновлений.
- **Уведомления** — Telegram: при создании/обновлении инцидента рассылка подписчикам.
  Подписка через бота (`/start` / `/stop`) на вебхуке или затравкой `STATUS_TELEGRAM_CHAT_IDS`.
- **Общий статус** — считается из худшего статуса компонентов и наличия активных инцидентов.

## Запуск

В составе стека (docker-compose): сервис `statuspage`, порт **8090**.
Витрина — `http://localhost:8090`, админка — `http://localhost:8090/admin` (вход по
`STATUS_ADMIN_TOKEN`).

Локально:

```bash
cd services/statuspage
pip install -r requirements.txt
STATUS_ADMIN_TOKEN=secret uvicorn app.main:app --port 8090
```

## Конфигурация

Компоненты и бренд — `config.json`. Секреты и параметры — env (см. `.env.example`).
БД по умолчанию — SQLite (`STATUS_DATABASE_URL`), для прода можно указать Postgres.

## Структура

```
app/
  config.py       # env + config.json → Settings
  db.py           # движок (SQLite/Postgres)
  models.py       # status_* таблицы
  monitor.py      # активный health-checker
  notify.py       # Telegram + подписки
  service.py      # сводка, операции с инцидентами (+ чистые day_status/overall)
  routes_public.py# витрина, /api/summary, вебхук
  routes_admin.py # admin-API (токен)
  main.py         # сборка приложения + lifespan (монитор)
  templates/      # index.html, admin.html (скелеты)
  static/js/      # api, labels, uptime, status, admin — чистые ES-модули
  static/css/     # status.css
config.json       # компоненты + бренд
```

## Тесты

```bash
cd services/statuspage && pytest
```

## Перенос на другой проект

1. Скопировать `services/statuspage/`.
2. Переписать `config.json` (компоненты, бренд).
3. Задать env (токен, БД, Telegram).

Ноль связей с порталом «Байтерек» — своя БД, своя авторизация, свой жизненный цикл.
