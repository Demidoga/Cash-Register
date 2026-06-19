# Tech stack: FastAPI + Postgres backend, React/Vite PWA, polyglot monorepo

## Decision

V1 is built as a **polyglot monorepo** with a standalone HTTP API:

- **Backend / API:** FastAPI (Python), Pydantic for validation + automatic OpenAPI.
- **Database:** Postgres via SQLAlchemy 2.0 + Alembic migrations. Money stored as integer rupees.
- **Managed DB + identity:** Supabase (Postgres + Supabase Auth for Google + email/password). FastAPI verifies the Supabase JWT on each request; **authorization (the per-clinic allowlist) and tenant scoping live in FastAPI**, not in Supabase.
- **`money-math`:** a pure Python module, zero I/O, exhaustively unit-tested with pytest — the project's secondary test seam.
- **Frontend:** React + Vite + `vite-plugin-pwa` (installable PWA, owns the quick-add hold-and-retry queue). Consumes the API via a TS client generated from the OpenAPI spec.
- **Testing:** pytest + FastAPI `TestClient` firing real HTTP at endpoints against a test DB (primary seam); pytest on `money-math` (secondary seam).
- **Contract between halves:** the OpenAPI spec. No shared code package across the Python/TS boundary.

## Why

The PRD's hardest architecture rule is **API-first**: "a documented HTTP API is the single integration surface… a future native mobile app will reuse it unchanged." A standalone FastAPI service satisfies this directly, and `TestClient` maps 1:1 onto the primary test seam. Python was chosen over TypeScript on the backend per developer preference; the PRD's **integer-rupee** decision means we give up nothing on money-correctness by not having `Decimal`, and settlement math lives server-side only so the lost "shared money-math package" costs little.

## Considered and rejected

- **TypeScript end-to-end (one language, shared `money-math` package).** Cleaner in theory; lost to developer fluency in Python. The shared-package benefit is small because the frontend never runs settlement math.
- **Next.js full-stack.** App Router pulls toward Server Components/Actions, which a native app cannot reuse — violating API-first. Honoring API-first in Next means route-handlers-only, i.e. Next as a heavier SPA-host with no SSR payoff (the app is private/behind-login, so SEO is irrelevant).
- **BaaS — React direct to Supabase via RLS + Postgres functions.** The crown-jewel settlement math, period-close locking, audit trail, and reversing entries are too important to live as SQL/RLS. They belong in a tested application layer that *is* the documented API. RLS, if used, is a second safety net under the API — never the backend itself.
