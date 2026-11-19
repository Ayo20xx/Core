# AGENTS.md — CORE

FastAPI + PostgreSQL + SQLAlchemy banking core. `docs/requirements.md` is the authoritative V1 spec (EUR-only wallets in integer cents, double-entry ledger, idempotency, reversals; FORGE is a separate future service); `README.md` is only a one-line summary. Read the spec before implementing features.

## Setup and commands

- Python 3.12 venv at `.venv`; dependencies pinned in `requirements.txt`. There is no `pyproject.toml` or installed package, so invoke tools from the repo root as `.venv/bin/python -m <tool>` or `.venv/bin/<tool>`.
- Config is loaded from `.env` by pydantic-settings in `app/core/config.py`, not from environment variables alone. `.env` is gitignored; create it from `.env.example`, but correct `DATABASE_URL` to match `docker-compose.yml`: dev Postgres is on host port **5442** (not 5432), user `core_user`, db `core_db`. `.env.example` is stale.
- Dev DB: `docker compose up -d db` (postgres:16, container 5432 → host 5442, healthcheck).
- No lint, formatter, or typecheck config/tooling exists; don't invent commands.

## Tests

- Integration tests require the DB to be up.
- Run from the repo root: `.venv/bin/python -m pytest` (one test: `.venv/bin/python -m pytest tests/integration/test_database.py -q`).
- Bare `pytest` fails with `ModuleNotFoundError: No module named 'app'` (no packaging or conftest path setup) — always use `python -m pytest`.
- Mark new async tests with `@pytest.mark.asyncio`; there is no pytest config changing pytest-asyncio's default strict mode.

## Migrations — currently broken

- `alembic/env.py` injects the asyncpg `DATABASE_URL` into a synchronous `engine_from_config`, so `alembic current/upgrade/revision` crashes with `sqlalchemy.exc.MissingGreenlet`. It needs an async engine (`async_engine_from_config` + `connection.run_sync`) or a separate sync driver URL.
- No revisions exist yet (`alembic/versions/` is absent), and models are annotation-only stubs (`app/models/user.py` has no `Column`s), so `--autogenerate` has nothing to detect.
- `alembic.ini` sets `script_location = %(here)s/alembic` and `prepend_sys_path = .`; its placeholder `sqlalchemy.url` is overwritten at runtime by `env.py`.

## Layout and conventions

- `app/main.py` is empty — no FastAPI app object or routes yet. Intended layering: `app/models` → `app/repositories` → `app/services` → `app/api/v1`, with `app/db/base.py` (DeclarativeBase) and `app/db/session.py` (async engine, `SessionLocal`, `get_session` dependency).
- Import the settings singleton as `from app.core.config import setting` and the URL as `Database_url` (unusual lowercase name); both are used that way in `app/db/session.py` and `alembic/env.py`.
