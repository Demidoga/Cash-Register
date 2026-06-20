# Clinic Cash Register

Partnership cash-management for a small dental clinic — replacing a shared Excel
sheet with a structured domain model and a defensible partner settlement. See
[`docs/PRD-clinic-cash-register.md`](docs/PRD-clinic-cash-register.md) and
[`docs/V1-build-plan.md`](docs/V1-build-plan.md); architecture decisions live in
[`docs/adr/`](docs/adr/).

This repo implements **all of V1** (all 69 PRD stories) as a polyglot monorepo
(ADR-0001):

```
/api   FastAPI + SQLAlchemy 2.0 + Alembic + pure money-math module (Python)
/web   React + Vite installable PWA (TypeScript)
/docs  PRD, build plan, ADRs
```

## Run it locally

**1. API** (Python, via [uv](https://docs.astral.sh/uv/)):

```bash
cd api
uv sync
uv run alembic upgrade head          # creates the schema (SQLite by default)
uv run uvicorn app.main:app --reload # http://localhost:8000  (OpenAPI at /docs)
```

By default the API uses a local SQLite file and a dev sign-in. For production set
`DATABASE_URL` to Postgres/Supabase, set a strong `JWT_SECRET`, and set
`DEV_LOGIN_ENABLED=false`.

**2. Web** (Node):

```bash
cd web
npm install
npm run dev                          # http://localhost:5173
```

Open the web app, sign in (any email — the first user becomes the owner and runs
setup), and you https://cblkjkdicfnvwigfxlkx.supabase.co/rest/v1/'re live.

## Test & typecheck

```bash
cd api && uv run pytest && uv run mypy app      # money-math + HTTP API seams
cd web && npm run build                          # type-checks the frontend
```

## What's inside (by milestone)

- **Money-math** (pure, exhaustively tested): profit, balances, case outstanding,
  and the settlement algorithm — N-partner, effective-dated share windows, joint
  pool standing, capital/drawings excluded, cash-conservation invariant.
- **Daily entry**: take-payment & log-expense quick-adds, transfer/capital/
  drawing/refund, all with closed-period locking.
- **Patients → cases → installments**, advances, discounts, write-offs.
- **Dashboard intelligence**: P&L, by-category/procedure/collector, receivables,
  trends, per-partner contribution.
- **Close & settle**: locked settlement statements, recorded settlement payments,
  statement history.
- **Integrity**: edit-while-open, void/restore, audit trail, soft-deletes,
  `clinic_id` scoping everywhere.
- **Exports**: CSV journal, PDF monthly summary, PDF/CSV patient statements.
- **Resilience**: installable PWA + offline hold-and-retry queue for quick-add.
