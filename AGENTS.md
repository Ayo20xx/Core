# AGENTS.md — CORE

FastAPI + PostgreSQL + SQLAlchemy banking core. `docs/requirements.md` is the authoritative V1 spec (EUR-only wallets in integer cents, double-entry ledger, idempotency, reversals; FORGE is a separate future service); `README.md` is only a one-line summary. Read the spec before implementing features.

## Setup and commands

- Python 3.12 venv at `.venv`; dependencies pinned in `requirements.txt`. There is no `pyproject.toml` or installed package, so invoke tools from the repo root as `.venv/bin/python -m <tool>` or `.venv/bin/<tool>`.
- Config is loaded from `.env` by pydantic-settings in `app/core/config.py`, not from environment variables alone. `.env` is gitignored; create it from `.env.example`, but correct `DATABASE_URL` to match `docker-compose.yml`: dev Postgres is on host port **5442** (not 5432), user `core_user`, db `core_db`. `.env.example` is stale.
- Dev DB: `docker compose up -d db` (postgres:16, container 5432 → host 5442, healthcheck). **Docker daemon must be running** for integration tests and `alembic` commands.
- No lint, formatter, or typecheck config/tooling exists; don't invent commands.

## Tests

- Integration tests require the DB to be up.
- Run from the repo root: `.venv/bin/python -m pytest` (one test: `.venv/bin/python -m pytest tests/integration/test_database.py -q`).
- Bare `pytest` fails with `ModuleNotFoundError: No module named 'app'` (no packaging or conftest path setup) — always use `python -m pytest`.
- Mark new async tests with `@pytest.mark.asyncio`; there is no pytest config changing pytest-asyncio's default strict mode.

## Database and migrations

- `app/models/user.py` defines `User` (`__tablename__ = "users"`) using SQLAlchemy 2.x `Mapped[...]`/`mapped_column(...)`; `app/models/__init__.py` imports it so `Base.metadata` sees the table. Import every new model there or Alembic autogenerate will miss it.
- `alembic/env.py` uses `async_engine_from_config` + `connection.run_sync` because `DATABASE_URL` is asyncpg; a synchronous `engine_from_config` fails with `MissingGreenlet`. Keep model imports in `env.py` as well.
- Revision `044a1e648a26` ("create users table") exists in `alembic/versions/` and is applied; `alembic current` reports it as head.
- `alembic.ini` sets `script_location = %(here)s/alembic` and `prepend_sys_path = .`; its placeholder `sqlalchemy.url` is overwritten at runtime by `env.py`.

## Layout and conventions

- `app/main.py` is empty — FastAPI app + v1 router added; router lives in `app/api/v1/__init__.py` (empty, you attach routes).  
- Keep the file `app/models/user.py` and the class name **`User`** (singular, as committed); do not rename to `Customer` or `Users`. The Pydantic schemas currently keep plural names (`UsersCreate`, `UsersRead`) in `app/schemas/user.py`, exported via `app/schemas/__init__.py`.
- `EmailStr` requires `email-validator` (pinned). `UsersCreate` lowercases email because the DB unique index is case-sensitive; `UsersRead` omits `password_hash` deliberately.
- Import the settings singleton as `from app.core.config import setting` and the URL as `Database_url` (unusual lowercase name); both are used that way in `app/db/session.py` and `alembic/env.py`.
- `SessionDep = Annotated[AsyncSession, Depends(get_session)]` lives in `app/api/deps.py`; use it in router endpoints; repositories still receive a plain `session: AsyncSession` argument.

## Roadmap — steps 1‑14 (status as of commit `ee83b91`)

| # | Done? | What |
|---|---|---|
| 1 | ✅ | Finish and review the **User** SQLAlchemy model (`app/models/user.py`, `User`, `__tablename__ = "users"`). |
| 2 | ✅ | Ensure model imports and Alembic metadata are correct (`app/models/__init__.py` imports `User`; `alembic/env.py` imports `User`). |
| 3 | ✅ | Generate and inspect the first migration (`alembic revision --autogenerate -m "create users table"` → `044a1e648a26`). |
| 4 | ✅ | Apply the migration and verify the database table (`alembic current` → `044a1e648a26`; 9 columns, native `uuid`, `timestamptz`, `users_pkey`, unique `ix_users_email`). |
| 5 | ✅ | Create Pydantic registration schemas (`app/schemas/user.py`: `UsersCreate`, `UsersRead`; exported via `app/schemas/__init__.py`). |
| 6 | 🟡 | **Password hashing** — `argon2-cffi` installed and pinned (`argon2-cffi==25.1.0`, `argon2-cffi-bindings==26.2.0`, `cffi==2.1.1`, `pycparser==3.12`); helper not yet written. |
| 6.5 | 🟡 | **Registration service/repository/endpoint** — yours to implement; expect `UsersCreate` → hash → `User` row → `UsersRead` response. |
| 7 | 🟡 | Email verification with expiring, single‑use codes (store `code_hash`, `expires_at`, `used_at`, `attempts` in Postgres; consume atomically). |
| 8 | 🟡 | Login / authentication (short‑lived JWT access‑token + opaque refresh‑token flow; see trade‑off below). |
| 9 | 🟡 | Account and Wallet models. |
| 10 | 🟡 | Automatic EUR wallet creation after verification. |
| 11 | 🟡 | Deposits and internal transfers. |
| 12 | 🟡 | Double‑entry ledger, atomicity, idempotency and concurrency safety. |
| 13 | 🟡 | Meaningful unit, integration and end‑to‑end tests. |
| 14 | 🟡 | Polish V1 and prepare for delivery. |

**Current blockers:** Docker daemon stopped; `app/api/deps.py` (SessionDep alias) and argon2‑cffi are installed but not yet used in code. `app/main.py` empty → FastAPI app + v1 router added; `app/api/v1/__init__.py` empty router.

## Token‑auth trade‑off (step 8)

| Aspect | JWT access‑token | Opaque refresh‑token |
|---|---|---|
| **Storage** | Stateless on client; nothing to server between requests. | Stored hashed row in DB (`refresh_tokens` table or `users` column). |
| **Revocation** | Hard — need separate blacklist or very short TTL (5‑15 min). | Trivial — delete the row; next refresh fails immediately. |
| **CSRF / XSS risk** | Access tokens in `localStorage` → XSS risk. | Refresh tokens stored in `httpOnly` cookie → immune to XSS. |
| **Login flow** | Client sends JWT; server validates signature locally (fast). | Client sends refresh token; server validates hash+expiry+rotation in DB; issues new access‑token + new refresh token. |
| **Auditability** | Claims visible; can embed `email_verified_at`/`is_active` but become stale. | Every use touches DB → always check latest `email_verified_at`/`is_active`. |
| **Recommendation for V1** | **Short‑lived JWT access‑tokens** (15 min TTL) with `sub` = user‑id and baked‑in claims. ✅ **Opaque refresh‑tokens** stored in DB with `expires_at`, `revoked_at`, `rotation_count`. Logout = DELETE the row. |

## What to do now

1. Add a `refresh_tokens` table (or a `token` column on `users` with `expires_at`, `revoked_at`).  
2. Implement the refresh endpoint: hash the incoming token, compare to DB, check expiry, rotate, issue new access‑token + new refresh token.  
3. Keep access‑token JWT very short (10‑20 min) so you rarely need to revoke it; if you must, just delete the refresh row and the client will stop getting new access tokens.  
4. Skip a blacklist for now; it’s only needed if you ever need to revoke a specific JWT before its natural expiry.

If you’d like, I can write the opaque‑refresh storage + rotation snippet for you, or just the login‑only access‑token flow first.

▣  Build · Nemotron 3.5 Lightning Free · 2m 42s
hm let me take my time to decide 
+ Thought: 1.7s
No rush at all — your project, your pace. 
Where you are right now (as of today):
- ✅ Steps 1–5 done (model, migration, schemas, basic plumbing).  
- ⏳ Steps 6–14 pending; you can tackle them whenever you’re ready.  
- Docker daemon is stopped — start it with docker compose up -d db whenever you restart work.  
- app/api/deps.py (SessionDep alias) and argon2-cffi are installed; the rest of the service/repository/endpoint is yours to implement whenever you say.

Whenever you’re ready, the roadmap, the “write by hand / delegate” checklist, and the interview‑question bank are all still here. Just message me or run .venv/bin/python -m pytest whenever you want to continue.

Good luck, and feel free to ping me whenever you’re ready to move forward.