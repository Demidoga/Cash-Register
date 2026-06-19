# V1 Build Plan — Clinic Cash Register

> The development plan for V1, derived from `PRD-clinic-cash-register.md` via a grilling/domain-modeling session. V1 = **all 69 PRD stories**. This doc sequences them and records the foundational decisions. Architecture rationale lives in `docs/adr/`; vocabulary lives in `context.md` (glossary section).

## How to build this

**Skeleton-first.** Build one thin vertical slice end-to-end and deploy it (Milestone 0), then attach the remaining stories to that proven spine, milestone by milestone. Same destination as a big-bang build (all 69 stories), just an order that de-risks the stack and the settlement math first.

## Stack (ADR-0001)

- **Backend/API:** FastAPI (Python) + Pydantic + auto OpenAPI. Standalone HTTP API (API-first; a future native app reuses it).
- **DB:** Postgres via SQLAlchemy 2.0 + Alembic. Money as **integer rupees**.
- **Managed DB + identity:** Supabase (Postgres + Auth for Google + email/password). FastAPI verifies the JWT; **authorization (allowlist) + scoping live in FastAPI**.
- **Frontend:** React + Vite + `vite-plugin-pwa`; consumes a TS client generated from the OpenAPI spec.
- **money-math:** pure Python module, zero I/O.

Repo layout:

```
/api        FastAPI app
  /money_math   pure settlement/profit/balance functions (pytest)
  /tests        HTTP integration tests (TestClient)
/web        React + Vite PWA
docs/
  PRD-clinic-cash-register.md
  V1-build-plan.md
  adr/0001..0007
context.md  design log + glossary
```

## Cross-cutting foundations — in from Milestone 0 (ADR-0006, ADR-0005)

These are data-model patterns, not features. Their *screens* ship late; the *patterns* exist from the first migration:

- **`clinic_id`** on top-level tables, scoped through one standard query path (single-clinic now, multi-clinic-ready later — ADR-0005).
- **Soft-deletes** (`deleted_at`) on every table.
- **Audit-stamping** (who/what/when) on every write.

## Domain model (reference)

- **Clinic** — one row; `clinic_id` everywhere.
- **User / Membership** — authenticated identity + role (Owner | Partner | Staff[dormant]).
- **Partner** + **ShareWindow** — effective-dated share fractions (Σ = 1 within a window).
- **Account** — cash container; `personal` (owner partner) or `joint` (toggleable).
- **MoneyMovement** — typed row with from/to legs (ADR-0007); attributed partner; optional category/case/note.
- **Category** (expense), **Procedure** (catalog + default price), **Employee** (name/role/salary).
- **Patient → Case → Payment** — Payment is an Income movement linked to a Case; Case derives outstanding = agreed price − payments (negative = advance/credit).
- **CaseAdjustment** — discount / write-off (reportable; write-off ≠ income).
- **Period** — open/closed span; close snapshots + **locks**.
- **SettlementStatement** — obligations produced at close; settlement payments are linked `Transfer` movements (ADR-0003).
- **AuditLog** — who/what/when for every write.

## money-math module (the secondary test seam)

Pure functions over date-stamped movements, effective-dated share windows, and account kinds:

- `profit(movements) -> int`
- `account_balances(movements, opening_balances) -> {account_id: int}`
- `settlement(movements, share_windows, accounts) -> SettlementStatement` (per-partner settlement balance + minimal transfers)

**Mandatory tests:** capital/drawing exclusion (ADR-0002) · cash-conservation invariant `Σ personal_i + joint = P` · ≥3-partner split · mid-period share-change split (ADR-0004) · advances/over-payment · write-offs (≠ income) · joint pool stays standing.

## Test seams

1. **HTTP API (primary).** FastAPI `TestClient` fires real requests at a test DB: entry flows, corrections, period close + locking, access control, exports. Bulk of coverage.
2. **money-math (secondary).** Exhaustive pytest unit tests on the pure functions above.

## Milestones

| # | Milestone | PRD stories | Delivers |
|---|---|---|---|
| **0** | **Walking skeleton** | slice of 1, 5–9, 11, 13, 19, 22, 30–31, 35, 50–51, 53 | Login + allowlist → seed clinic → 1 partner + 1 account → patient+case → take a payment → one dashboard number → close month + settlement statement → record settlement payment. Money-math v1 (2-partner). Both seams live. **Deployed.** |
| **1** | Configuration | 10–18 | Currency, effective-dated shares, accounts (personal/joint + toggle), categories, procedure catalog, employees, opening balances. |
| **2** | Money entry | 19–28 | All movement types; quick-add flows + smart defaults. |
| **3** | Patients & cases | 29–34 | Outstanding across cases, advances, charity/zero-value, per-patient view. |
| **4** | Dashboard & intelligence | 35–44 | Breakdowns + trends, receivables/chase list, custom-range P&L, per-procedure, per-case profit, per-partner contribution. |
| **5** | Settlement (complete) | 50–55 | N-partner, mid-period split, joint pool, lock, statement history. |
| **6** | Corrections & integrity | 56–62 | Edit-while-open, void/restore, refund, discount, write-off, reversing entries, audit trail. |
| **7** | Reminders | 45–49 | In-app needs-attention panel. |
| **8** | Exports & data safety | 63–67 | CSV/Excel journal, PDF monthly + patient statement, backups. |
| **9** | Resilience / PWA | 68–69 | Installable PWA + offline hold-and-retry queue. |

## Decision log (ADRs)

- 0001 — Tech stack: FastAPI + Postgres + React/Vite PWA, polyglot monorepo
- 0002 — Settlement rebalances profit only (not capital/drawings/opening balances)
- 0003 — Close produces a locked statement; settlement payment recorded separately
- 0004 — Settlement splits a period at effective-dated share-change boundaries
- 0005 — Single-clinic in practice, multi-clinic-ready in schema
- 0006 — Soft-delete + audit foundational from Milestone 0
- 0007 — Money movements as single typed rows, not double-entry

