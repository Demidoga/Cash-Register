# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Clinic Cash Register: partnership cash-management for a small dental clinic, replacing a shared Excel sheet. Polyglot monorepo (ADR-0001): a FastAPI backend (`/api`) and a React/Vite installable PWA (`/web`), integrating only over a documented HTTP API. The product spec is `docs/PRD-clinic-cash-register.md`; the build plan is `docs/V1-build-plan.md`; design decisions are in `docs/adr/`. Domain glossary lives in `context.md`. This repo implements all of V1 (69 PRD stories).

## Commands

Backend (`cd api`, uses [uv](https://docs.astral.sh/uv/)):

```bash
uv sync                                  # install deps
uv run alembic upgrade head              # create/upgrade schema (SQLite by default)
uv run uvicorn app.main:app --reload     # dev server → http://localhost:8000 (OpenAPI at /docs)
uv run pytest                            # all tests
uv run pytest tests/test_money_math.py   # one file
uv run pytest tests/test_features.py::test_name -q   # one test
uv run mypy app                          # type-check
uv run alembic revision --autogenerate -m "msg"      # new migration after model changes
```

Frontend (`cd web`, Node):

```bash
npm install
npm run dev        # → http://localhost:5173 (proxies /api to :8000)
npm run build      # tsc -b + vite build — this is the frontend's typecheck/CI gate
```

There is no separate frontend lint/test step; `npm run build` (which runs `tsc -b`) is the type gate.

## Architecture

### The two test seams (ADR-0001)
The whole design exists to make money-correctness provable. Hold this in mind when changing anything financial:

1. **`money-math`** (`api/app/money_math/`) — a pure, zero-I/O Python module: `profit`, `account_balances`, `case_outstanding`, and `settlement`. No framework or SQLAlchemy imports; its value types (`types.py`) are deliberately decoupled from the DB models. This is where the crown-jewel settlement arithmetic lives and is exhaustively unit-tested (`tests/test_money_math.py`). **Put financial logic here, not in routers or services.**
2. **HTTP API** — pytest + FastAPI `TestClient` firing real HTTP at endpoints (`tests/test_features.py`, `test_access_control.py`, `test_walking_skeleton.py`). Each test runs against a fresh in-memory SQLite DB.

`api/app/services.py` is the **bridge**: it loads SQLAlchemy rows, maps them to the pure money-math value types, calls the pure functions, and persists results. It also holds the shared `get_scoped` / `list_alive` / `soft_delete` / `record_audit` helpers.

### Request flow & layering
`routers/*.py` (one per domain area: setup, movements, patients, corrections, periods, reports, reminders, dashboard, exports, config, devauth) → `services.py` → `money_math/` (pure) and `models.py` (persistence). Pydantic `schemas.py` defines request/response models; the OpenAPI spec they generate is the **only** contract between backend and frontend — there is no shared code package across the Python/TS boundary.

### Auth, allowlist, tenant scoping (deps.py, security.py)
- **Authentication** = a verified JWT. Supabase issues it; FastAPI verifies it in `security.py`, picking HS256 (shared `jwt_secret`) vs ES256/RS256 (JWKS fetched from `{supabase_url}/auth/v1/.well-known/jwks.json`) from the token's own `alg` header. `verify_jwt` only proves identity.
- **Authorization** = the allowlist: a valid login is not enough; the email must have a `Membership` row (`get_current_member` in `deps.py`).
- **Tenant scoping**: every entity carries `clinic_id`; every read goes through `get_scoped`/`list_alive` filtered by the member's clinic (ADR-0005 — single clinic in practice, multi-clinic-ready in schema, so going multi-clinic is a migration not a rewrite).
- **Dev login** (`devauth.py`, `/dev/login`): when `DEV_LOGIN_ENABLED=true`, the API mints a signed JWT for any email so the app runs end-to-end without Supabase. **Must be `false` in production.** The first user to run `/setup` becomes the owner.

### Domain model invariants (read before touching money or models)
- **Money is integer rupees everywhere** — no floats/Decimal (ADR-0001). Share fractions use `Fraction`.
- **A money movement is one typed row, not double-entry** (ADR-0007): `type ∈ {income, expense, transfer, capital, drawing}` with optional `from_account`/`to_account` legs. Income/Capital fill `to`; Expense/Drawing fill `from`; Transfer fills both. Only INCOME/EXPENSE affect profit (`profit = ΣIncome − ΣExpense`). A **refund is a negative-amount Income**.
- **Settlement** rebalances profit only; the joint pool stays standing; capital/drawings are excluded (ADR-0002). It splits a period at effective-dated share-window boundaries (ADR-0004) and obeys a cash-conservation invariant.
- **Close → statement, payment recorded separately** (ADR-0003): closing a period produces a locked `SettlementStatement`; settlement payments are separate `Transfer` rows linked back to it.
- **Closed-period locking**: edits to movements dated inside a closed period are rejected (`closed_period_covering` in services).
- **Soft-delete + audit are foundational** (ADR-0006): rows carry `deleted_at`; never hard-delete. Mutations stamp an `AuditLog` via `record_audit`. Most models mix in `TimestampMixin`/`SoftDeleteMixin`/`AuditMixin`. Reads must filter `deleted_at IS NULL`.

### Database
SQLAlchemy 2.0 + Alembic. Models are DB-agnostic: **tests use in-memory SQLite, production targets Postgres/Supabase**. `db.py` defines `Base`, a rebindable engine/`SessionLocal` (`configure()` for tests), and an explicit constraint `NAMING_CONVENTION` (required for SQLite batch migrations and clean Alembic ALTERs). The Alembic URL is injected from app settings in `migrations/env.py`, not hard-coded in `alembic.ini`. Tests build the schema with `Base.metadata.create_all`, not migrations — so when you add a model, you must **both** keep it test-importable and generate an Alembic migration for real deployments.

### Frontend
`web/src/api.ts` is the single typed API client: it holds the JWT (localStorage), scopes every request, and — for the two **quick-add** flows (take-payment, log-expense) — runs an **offline hold-and-retry queue** (PRD story 68) so an entry is never lost if the network drops mid-save; queue depth is surfaced via the `ccr:queue` window event. `auth.tsx` mirrors the Supabase access token into the localStorage bearer token on every auth-state change, and falls back to dev-login when Supabase env vars are absent. Routing/pages live in `src/pages/`. PWA config (manifest, service worker, `navigateFallbackDenylist: [/^\/api/]` so the SW doesn't swallow API calls) is in `vite.config.ts`.

## Configuration

Backend env (see `api/app/config.py`): `DATABASE_URL` (SQLAlchemy URL; defaults to local SQLite), `JWT_SECRET`, `JWT_AUDIENCE` (default `authenticated`), `SUPABASE_URL` (enables JWKS verification), `CLINIC_NAME`, `CLINIC_CURRENCY` (default `PKR`), `DEV_LOGIN_ENABLED` (default true — **set false in prod**).

Frontend env (see `web/.env.example`): `VITE_API_BASE` (default `/api`), `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (leave both blank to use dev login). `VITE_API_TARGET` controls the dev proxy target.

**Production checklist:** point `DATABASE_URL` at Postgres, set a strong `JWT_SECRET`, set `DEV_LOGIN_ENABLED=false`, configure the Supabase env vars on both halves.
