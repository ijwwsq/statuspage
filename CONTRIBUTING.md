# Contributing

Thanks for taking the time to contribute! This project stays intentionally small
and dependency-light — please keep changes in that spirit.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
STATUS_ADMIN_TOKEN=secret uvicorn app.main:app --reload --port 8090
```

Open <http://localhost:8090> (public page) and <http://localhost:8090/admin> (token = `secret`).

## Running the tests

```bash
pytest -q
```

The suite runs on in-memory SQLite — no network, no external services.

## Guidelines

- **Keep it lean.** New third-party dependencies need a strong justification;
  the stack is deliberately FastAPI + SQLAlchemy + Jinja + httpx and nothing else.
- **Cover non-trivial logic** with a test in `tests/` (see `test_service.py`).
- **No breaking the drop-in promise.** All tables are `status_*` prefixed and the
  service carries its own auth/DB/lifecycle — keep it self-contained.
- Match the surrounding code style; the frontend is plain ES modules, no build step.

## Pull requests

1. Fork and branch from `main`.
2. Make the change + tests.
3. Ensure `pytest -q` is green and the Docker image still boots (`docker build .`).
4. Open the PR with a short description of what and why.
