# CONTEXT — Clinic Cash Register

A running record of the design conversation behind this project, so any future session can pick up with full context.

---

## What this project is

A **cash-management web app for a small dental clinic** run by two doctors (Saad & Hassan), replacing their shared Excel sheet (`Clinic_Cash_Register.xlsx`). The Excel is a **case study only** — the product is architected as a **general, multi-tenant SaaS** any small partnership business could use, but **run privately for now** (just the two doctors; no billing, no public signup).

The product's center of gravity is **income/expense intelligence** — *where money comes from and where it goes* — on top of a structured domain model (patients paying treatment cases in installments, partner-attributed expenses, money across personal/joint accounts, and a defensible partner settlement that runs quietly in the background).

---

## How we got here (the flow)

Following the Matt Pocock skill flow: `/grill-me` (relentless design interview) → `/to-prd` (this is done) → next is `/to-issues` → then `/implement` (fresh session per issue).

- **Grilling: complete.** Full design tree walked across domain, features, and infrastructure.
- **PRD: complete.** Written to `docs/PRD-clinic-cash-register.md`. (Not published to a tracker — `/setup-matt-pocock-skills` not run, not a git repo yet.)
- **Testing seams agreed:** (1) HTTP API as the primary/highest seam; (2) the pure money-math module as a secondary seam for exhaustive settlement/profit tests.
- **Next decision pending:** whether to `git init` + `/setup-matt-pocock-skills` to publish to a real tracker, or run `/to-issues` straight against the PRD file. Tech stack deliberately left open until implementation.

---

## Source Excel — what it actually was

Two sheets:

- **`Cash Register`** (the journal): `Date · ID · Type(Income/Spending) · Description · Income · S.Expenses · H.Expense · Remarks(who)`. One row per discrete event — transaction-level, not summary.
- **`Monthly Summary`**: hand-rolled `SUMPRODUCT` per month/per doctor, plus a confusing settlement block (`Half of Total Income`, `Net`, `Saad Share = H3 + L3`, etc.).

Things the data quietly revealed:
- 2-doctor **partnership**, currency **PKR**, income split **50/50**, expenses tracked **by who paid** (the two expense columns).
- **Patients pay treatments off in installments** — the `DD-2026…` ID repeats across days with partial payments (e.g. `1750 → 4500 → 7000 → 8400`).
- Income attribution to one doctor is **coincidental**, not structural — anyone can collect.
- Settlement formulas were **ad-hoc and fragile** — the crown-jewel problem worth replacing.
- `capital dental` is a **supplier name** (a supplies expense), not a capital contribution.
- Zero-value income rows exist = **free/charity treatments**.

---

## Every design decision we locked (the full Q&A outcome)

### Domain model

- **What it is:** a partnership **cash journal** with two derived layers (monthly summary + partner settlement). Transaction-level capture is the source of truth.
- **Partners:** configurable, **effective-dated** shares; N partners supported; profit share = expense share (same ratio).
- **Settlement (crown jewel):** Net profit `P = Income − Expenses`, split `s_i × P`. Reconcile via a computed transfer. Generalized to N partners. **Demoted from hero to a back-office "close the month" flow.**
- **Settlement cadence:** explicit **close & settle** action — **monthly by default, on-demand allowed** ("per mutual understanding"). Closing snapshots balances, records real transfers, **locks** the period.
- **Income side:** structured **Patient → Case → Payment**. Case has agreed price → derives **outstanding balance**; over-payment = **advance/credit**. (Chose structure over a flat patient tab.)
- **Expense side:** **categories** (editable list) in v1; expenses **partner-attributed**, always **shared clinic cost**, **always paid on the spot** (no supplier payables); **optionally linked to a case** → per-case profitability.
- **Cash custody — accounts (key decision):** money lives in **accounts**, each tagged **personal** (one partner) or **joint** (shared, **toggleable**). Entry chooses destination/source account. Subsumes payment method (cash/bank). **General accounts model** (any number), ship with a simple default. **Joint pool stays standing** at settlement; settlement only reconciles personal holdings: `settlement_balance_i = personal_i − s_i × Σ personal_j`.
- **Money movements:** one concept, typed `Income · Expense · Transfer · Capital · Drawing`. Only Income/Expense hit profit. Settlement payments recorded as real **Transfers**.
- **Corrections:** audit-logged edits while open; **closed periods locked**; corrections via **reversing entries**; **refunds** = money movements; **discounts** & **write-offs** = case-level adjustments (write-off ≠ income).
- **Employees:** light entity (name, role, salary) tied to salary expenses; recurring-expense templates are a **fast-follow**.
- **Procedure catalog:** editable, overridable default prices to pre-fill cases.
- **Cutover:** clean **opening balances** at go-live; historical Excel import deferred (data too messy — non-unique IDs, ambiguous rows).
- **Tax:** **none** in-app; invest in strong **exports** instead.
- **Scope:** single clinic per tenant. PKR, integer rupees. Patient fields = name, phone, notes. Per-movement notes field.
- **Swept twice for completeness.** Explicitly **dropped:** supplier payables (always paid on spot), inter-partner loans (defer), inventory (out — different product). Explicitly **kept:** patient advances. Shares symmetric (profit = expense).

### Features (v1)

- **Dashboard** centered on income/expense intelligence: this-month income/expense/**net profit**; **where it comes from** (procedure/collector/biggest patients); **where it goes** (by category); **month-over-month trends**; account balances; outstanding receivables. Settlement tucked into "close the month."
- **Reporting depth:** breakdowns **+ trends** in v1 (insight-style "expenses up 22%" deferred to fast-follow).
- **Reminders:** **in-app "needs attention"** in v1 (patient outstanding, recurring costs due, settlement due, cold large balances). WhatsApp/SMS to patients is a **fast-follow** (phone stored to enable it).
- **Data entry:** two optimized **quick-add flows** — "Take a payment" / "Log an expense" — income path tuned hardest; smart defaults; mobile-first; rare types (transfer/capital/drawing) tucked away.
- **Exports:** CSV/Excel journal (data-ownership escape hatch) + PDF monthly summary + PDF patient statement.

### Infrastructure / architecture

- **Multi-tenant SaaS, architected general / run private.** Top-level **Clinic** tenant; strict isolation. No billing, no public signup now; private rollout (owner creates clinic, invites partner).
- **Platform:** responsive web app / **PWA** now; **native mobile app planned later** → **API-first backend** so the future app reuses the same API.
- **Internet:** clinic connection is **solid** → build "assume online" + quick-add **holds entry locally and retries** so a payment is never lost mid-save.
- **Auth:** **Google sign-in + email/password** (user correctly pushed for Google as convenient + offloads credential security; we kept email/password too since a general audience can't be assumed to have Gmail). Per-clinic **invite/allowlist** gates access (auth = identity, allowlist = authorization).
- **Roles:** **Owner** (configures, invites) → **Partner** (full financial/settlement) → **Staff** (operational only, **dormant in v1**, partner/owner logins only).
- **Onboarding:** sign up → create clinic → configure (currency, partners+shares, accounts/joint toggle, categories, procedure catalog, opening balances) → invite partners → go live.
- **Billing:** none; launch free, architect for paid later.
- **Data safety:** managed DB with **automated daily backups + point-in-time recovery**, **soft-deletes everywhere**, CSV/Excel export as user-controlled escape hatch.
- **Tech stack:** deliberately **left open** for the implementation step.

---

## Settlement algorithm (precise — replaces the Excel's fragile `M/N` block)

```
For a closed period:
  P            = total Income − total Expenses            // net profit
  s_i          = partner i's effective share (Σ s_i = 1)
  personal_i   = income i collected into personal accounts
                 − expenses i paid from personal accounts
  joint        = income into joint − expenses from joint   // shared pool, stays standing

Entitlement_i = s_i × P
Joint is implicitly owned s_i × joint by each partner (left standing).

Settlement reconciles ONLY personal holdings:
  settlement_balance_i = personal_i − s_i × (Σ_j personal_j)
    > 0 → partner i holds more than their share → pays in
    < 0 → partner i is owed

2 partners → single "A pays B X". 3+ → minimal set of transfers.
Recorded settlement payments are `Transfer` movements.
Invariant: Σ personal_i + joint = P  (cash conserved).
```

---

## Deferred fast-follows (designed-for, not v1)

Recurring-expense templates · WhatsApp/SMS patient reminders · insight-style analytics · historical Excel import (best-effort, labeled pre-migration) · native mobile app · subscription billing · full offline-first sync · Pakistani lakh/crore digit grouping in display.

---

## Explicitly out of scope

Clinical/practice-management (appointments, notes, tooth charts) · inventory/stock · supplier payables · inter-partner loans · tax logic · billing/public signup/go-to-market · multi-branch · multi-currency · differing profit vs expense shares.

---

## Artifacts

- `Clinic_Cash_Register.xlsx` — the source/case-study spreadsheet.
- `docs/PRD-clinic-cash-register.md` — the full PRD (problem, solution, 69 user stories, implementation decisions incl. settlement algorithm, testing decisions, out-of-scope, fast-follows).
- `context.md` — this file.
