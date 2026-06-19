# Clinic Cash Register — API

FastAPI backend for the Clinic Cash Register. See `../docs/V1-build-plan.md`.

This is **Milestone 0** (the walking skeleton): login + allowlist → seed clinic →
partners + accounts → patient + case → take a payment → dashboard number →
close period + settlement statement → record settlement payment. Both test seams
(money-math + HTTP API) are live.

## Run tests

```bash
cd api
uv run pytest
```

## Run the dev server

```bash
cd api
uv run uvicorn app.main:app --reload
```

Configuration is via environment variables (see `app/config.py`):

- `DATABASE_URL` — SQLAlchemy URL. Defaults to a local SQLite file. Production
  targets Postgres (e.g. Supabase): `postgresql+psycopg://...`.
- `JWT_SECRET` — HS256 secret used to verify the Supabase JWT.
- `JWT_AUDIENCE` — expected audience claim (default `authenticated`).

> Tests use SQLite; production uses Postgres. Models are kept DB-agnostic.
