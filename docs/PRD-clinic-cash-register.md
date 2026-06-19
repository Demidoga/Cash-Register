# PRD — Clinic Cash Register

> Status: Draft for review · Origin: synthesized from the `/grill-me` design session, using `Clinic_Cash_Register.xlsx` as the case study.

## Problem Statement

Two doctors running a small dental clinic track all of their money in a shared Excel sheet (`Clinic_Cash_Register.xlsx`). Every day they record patient payments and clinic expenses as rows, and a second sheet hand-rolls monthly summaries and a partner profit-split using fragile `SUMPRODUCT` and ad-hoc formulas.

From their perspective, the pain is:

- **The file lives in one place.** Only one person really "owns" it; the partners are never looking at the same up-to-date numbers.
- **It only adds up totals.** It cannot tell them *what a patient still owes* even though patients pay treatments off in installments, *where money is actually going* by category, or *where it is coming from* by procedure.
- **The settlement math is hand-maintained and confusing.** Working out "who owes whom" between the partners depends on brittle formulas nobody fully trusts.
- **There is no safety or history.** A wrong edit silently overwrites the truth; there is no audit trail, no recoverability, and no way to lock a settled month.
- **It does not scale.** Adding a third partner, changing the profit split, or handing a patient a clean statement is all manual or impossible.

## Solution

A multi-tenant web application (delivered as an installable PWA, mobile-friendly) that replaces the spreadsheet with a structured partnership cash-management system. Each business is an isolated **Clinic**; an owner configures it and invites partners as collaborators.

The product's center of gravity is **income/expense intelligence** — clear answers to *where money is coming from and where it is going* — backed by a correct, structured domain model underneath: patients who pay treatment cases off in installments, expenses attributed to a paying partner and category, money held across personal and joint accounts, and a reliable partner settlement that runs quietly in the background rather than dominating the UI.

It does everything the Excel does, then adds: live outstanding-balance tracking, category/procedure breakdowns and month-over-month trends, in-app reminders, defensible settlement, audit-logged corrections, automatic backups, and clean exports (so the data is never trapped).

## User Stories

**Onboarding, tenancy & access**

1. As a clinic owner, I want to sign up and create a Clinic workspace, so that my practice has its own private space.
2. As a clinic owner, I want all of my clinic's data isolated from every other clinic, so that no one else can ever see our finances.
3. As a clinic owner, I want to invite partners by email as collaborators, so that they can access the same live data.
4. As an invited partner, I want to accept an invitation and join the clinic, so that I can start working immediately.
5. As a user, I want to sign in with Google, so that I don't have to manage another password.
6. As a user, I want to sign in with email and password, so that I can use the app even without a Google account.
7. As a clinic owner, I want only invited (allowlisted) people to access my clinic, so that a valid Google/email login alone is not enough to get in.
8. As a clinic owner, I want owner-level rights to configure the clinic and manage members, so that I control setup while partners focus on day-to-day money.
9. As a partner, I want full access to all financial data and settlement, so that I can see the complete picture.

**Configuration**

10. As an owner, I want to set the clinic's currency (PKR), so that all amounts display correctly.
11. As an owner, I want to define each partner and their profit share, so that profit and settlement are computed against real terms.
12. As an owner, I want share percentages to be effective-dated, so that a partner joining later does not receive a share of earlier profit.
13. As an owner, I want to create accounts and tag each as personal (one partner) or joint (shared), so that the system reflects where money physically lives.
14. As an owner, I want to enable or disable the joint account, so that money can flow to individual or shared accounts depending on how we work.
15. As an owner, I want to manage an editable list of expense categories, so that spending can be grouped and analyzed.
16. As an owner, I want to maintain an editable procedure catalog with default prices, so that opening a case is fast and pricing is consistent.
17. As an owner, I want to record employees (name, role, salary), so that salary expenses tie to a person and I can see what we've paid them.
18. As an owner, I want to enter opening balances at go-live (account balances, open cases with outstanding amounts), so that we switch over from Excel cleanly without importing messy history.

**Recording money — daily entry**

19. As a partner, I want a one-tap "Take a payment" flow, so that I can record a patient payment in seconds while they're standing there.
20. As a partner, I want a one-tap "Log an expense" flow, so that recording a cost is just as fast.
21. As a partner, I want smart defaults (today's date, last-used account, recent categories, catalog price pre-fill), so that I type as little as possible.
22. As a partner, I want each income entry attributed to the partner who collected it and the account it landed in, so that holdings and settlement are accurate.
23. As a partner, I want each expense attributed to the partner who paid it, its category, and the account it came from, so that costs are correctly tracked and shared.
24. As a partner, I want to optionally link an expense to a treatment case, so that I can see per-case profitability.
25. As a partner, I want to record a transfer between accounts (e.g. pocket cash into the joint account), so that relocating money doesn't distort profit.
26. As a partner, I want to record a capital contribution, so that money I put into the clinic is tracked without counting as profit.
27. As a partner, I want to record a drawing, so that money I take out for personal use is tracked without counting as an expense.
28. As a partner, I want an optional note on any money movement, so that I can preserve the context the Excel "Remarks" column held.

**Patients, cases & installments**

29. As a partner, I want to create a patient (name, phone, notes), so that payments are tied to a real person.
30. As a partner, I want to open a treatment case for a patient with a procedure and agreed price, so that installment payments roll up against it.
31. As a partner, I want each payment recorded against a case, so that the case's outstanding balance updates automatically.
32. As a partner, I want to see a patient's outstanding balance across all their cases, so that I know what they still owe.
33. As a partner, I want over-payments treated as an advance/credit on the case, so that prepayments aren't a glitch.
34. As a partner, I want to record a zero-value/charity case, so that free treatments are still captured.

**Dashboard & income/expense intelligence**

35. As a partner, I want a home dashboard showing this month's total income, total expenses, and net profit, so that I instantly know if we're up or down.
36. As a partner, I want to see where income is coming from (by procedure, by collector, biggest patients/cases), so that I understand our revenue.
37. As a partner, I want to see where money is going (expenses by category, biggest line items), so that I can control spending.
38. As a partner, I want month-over-month trends of income vs expenses, so that I can see direction, not just a snapshot.
39. As a partner, I want live balances of every account, so that I know how much cash sits where.
40. As a partner, I want total outstanding receivables with a "patients to chase" list, so that I can collect what's owed.
41. As a partner, I want a P&L for any custom date range, so that I can analyze any period.
42. As a partner, I want per-procedure volume and revenue, so that I know which procedures drive the business.
43. As a partner, I want per-case profitability for cases with linked expenses, so that I see true margins.
44. As a partner, I want per-partner contribution (collected vs paid vs entitled share), so that contributions are transparent.

**Reminders (in-app)**

45. As a partner, I want an in-app "needs attention" panel, so that the system surfaces what to act on.
46. As a partner, I want reminders of patients with outstanding balances, so that I follow up on money owed.
47. As a partner, I want reminders that recurring costs (rent, salaries) are due, so that nothing is missed.
48. As a partner, I want a month-end settlement reminder, so that we close the books on time.
49. As a partner, I want alerts on large unpaid balances going cold, so that big receivables don't slip.

**Settlement**

50. As a partner, I want the system to compute each partner's settlement balance from real data, so that "who owes whom" is trustworthy.
51. As a partner, I want to close a period (monthly by default, or on demand), so that we settle when we mutually agree.
52. As a partner, I want the settlement to account for personal and joint accounts correctly, with the joint pool staying standing, so that the math matches our arrangement.
53. As a partner, I want settlement payments recorded as real transfers, so that the books show the cash that actually changed hands.
54. As a partner, I want a closed period locked from edits, so that settled books can't be silently altered.
55. As a partner, I want to view past closed periods and their settlement statements, so that we have a reliable history.

**Corrections & integrity**

56. As a partner, I want to edit an entry before its period is closed, with the change logged, so that fixing mistakes is safe and auditable.
57. As a partner, I want to void/soft-delete an erroneous entry, so that it's removed but recoverable.
58. As a partner, I want to record a refund as a money movement, so that money handed back is tracked without being an "expense."
59. As a partner, I want to apply a discount to a case, so that the outstanding drops without recording a fake payment, and discounts are reportable.
60. As a partner, I want to write off a case's outstanding as bad debt, so that it stops showing as owed without counting as income.
61. As a partner, I want to correct a closed period via a reversing entry in the current period, so that history stays intact and auditable.
62. As a partner, I want an audit trail of who changed what and when, so that we can trust the record.

**Exports & data safety**

63. As a partner, I want to export the full journal to CSV/Excel, so that our data is never trapped and our accountant has what they need.
64. As a partner, I want a PDF monthly summary, so that I have a clean record of each month.
65. As a partner, I want a PDF per-patient statement, so that I can hand a patient a clear record of payments and balance.
66. As a partner, I want automatic backups of our data, so that an outage or mistake can be recovered.
67. As a partner, I want deletes to be soft/recoverable, so that nothing important is ever truly lost.

**Resilience**

68. As a partner, I want a quick-add entry to be held locally and retried if the connection drops mid-save, so that a payment is never lost.
69. As a partner, I want to install the app to my phone's home screen, so that it feels like a native app.

## Implementation Decisions

**Architecture**

- **Multi-tenant SaaS, architected general but run privately.** A top-level **Clinic** (organization/tenant) entity owns all data, with strict tenant isolation enforced on every query. No billing, subscription, or public signup is built; rollout is private (owner creates the clinic and invites the partner). The clean tenant model is retained so the product can be published later without rework.
- **API-first backend.** A documented HTTP API is the single integration surface; the PWA consumes it now, and a future native mobile app will reuse it unchanged.
- **Delivery: responsive web app as an installable PWA**, mobile-friendly, leading the income flow's UX. Built "assume online" (clinic internet is reliable); quick-add forms hold an entry locally and retry on failure so a dropped connection never loses data.
- **Managed database** with automated daily backups + point-in-time recovery. **Soft-deletes everywhere** for recoverability and to back the audit trail.
- **Tech stack (frameworks/DB/hosting) intentionally deferred** to the implementation step as the first architectural choice there.

**Authentication & roles**

- Auth supports **Google sign-in and email/password**. Access to a clinic is gated by a **per-clinic invitation/allowlist** — authentication proves identity; authorization is the allowlist. Google handles credential security; the app owns authorization and sessions, with long-lived sessions on trusted devices.
- Roles: **Owner** (configures clinic, manages members) → **Partner** (full financial + settlement access) → **Staff** (operational only: payments, patient balances; cannot see profit/settlement/partner accounts/drawings). v1 has partner/owner logins only; the **Staff** role exists in the model but is dormant.

**Domain model**

- **Partners** with configurable, **effective-dated** share fractions (sum to 1 within an effective window). Profit share and expense share are the **same** ratio.
- **Accounts**: any number, each tagged **personal** (belongs to one partner) or **joint** (shared, toggleable). Accounts subsume payment method (cash vs bank).
- **Money movement** is one concept with a **type**: `Income · Expense · Transfer · Capital · Drawing`. Only `Income` and `Expense` affect profit. Every movement records date, amount, account(s), attributed partner, and optional note.
  - `Income` = a payment **against a treatment case**, attributed to the collecting partner, into a destination account.
  - `Expense` = a shared clinic cost, paid **from** an account by a partner, assigned a **category**, optionally **linked to a case**. Always paid on the spot (no supplier payables).
  - `Transfer` = account→account relocation, no profit impact (also how settlement payments are recorded).
  - `Capital` = partner injects outside money (not profit).
  - `Drawing` = partner takes money out for personal use (not an expense).
- **Patients → Cases → Payments.** A case has an agreed price (pre-fillable from the **procedure catalog**, overridable) and derives an **outstanding balance**. Payments accumulate against the case; over-payment is an **advance/credit**.
- **Expense categories** and **procedure catalog** are editable per-clinic lists. **Employees** are a light entity (name, role, salary) that salary expenses reference (recurring-expense templates are a fast-follow).
- **Corrections:** edits allowed while a period is open and **audit-logged**; **closed periods are locked**; corrections to closed periods are made via **reversing entries** in the open period. **Refunds** are money movements; **discounts** and **write-offs** are case-level adjustments (reportable, and write-offs are explicitly not income).
- **Currency:** PKR, stored as integer rupees (no decimals).
- **Cutover:** clean **opening balances** at go-live (account balances + open cases). Historical Excel import is out of v1.

**Settlement algorithm** (the crown-jewel money math — encoded precisely because prose alone is fragile, exactly the failure mode of the Excel):

```
Given, for a closed period:
  P            = total Income − total Expenses            // net profit for the period
  s_i          = partner i's effective share (Σ s_i = 1)
  personal_i   = (income i collected into personal accounts)
                 − (expenses i paid from personal accounts)   // partner i's personal holding
  joint        = (income into joint) − (expenses from joint)  // shared pool, stays standing

Entitlement_i = s_i × P
Joint is implicitly owned s_i × joint by each partner (left standing, not distributed).

Settlement reconciles ONLY the personal holdings:
  settlement_balance_i = personal_i − s_i × (Σ_j personal_j)

  settlement_balance_i > 0  → partner i holds more than their share → pays in
  settlement_balance_i < 0  → partner i is owed

For 2 partners this collapses to a single "A pays B X" figure; for 3+,
compute a minimal set of transfers. Recorded settlement payments are `Transfer` movements.
Cash is conserved: Σ (personal_i) + joint = P.
```

**API contract (shape, not paths)**

- Tenant-scoped resources: clinics, members/invitations, partners & share-periods, accounts, categories, procedures, employees, patients, cases, money-movements, period-closes/settlements, exports.
- Reads for the dashboard are served by aggregate/report endpoints (period P&L, by-category, by-procedure, by-partner, receivables, account balances, trends) computed server-side from movements.
- Writes for entry go through dedicated quick-add endpoints (take-payment, log-expense) plus generic movement endpoints for transfer/capital/drawing.

## Testing Decisions

- **What makes a good test here:** assert **external behavior**, never implementation details. A good test states a real scenario ("partner A collects 5000 into personal, partner B pays 2000 rent from joint; after close, A owes B X") and asserts the observable outcome (response payload, derived balance, locked state), not internal structure.
- **Two seams (confirmed with developer):**
  1. **HTTP API — primary/highest seam.** Integration tests fire real requests at endpoints against a test database and assert responses and resulting state: entry flows, corrections (edit/void/refund/discount/write-off/reversing), period close + locking, access control & tenant isolation, exports. The bulk of coverage lives here, decoupled from implementation.
  2. **Pure money-math module — secondary seam.** Exhaustive, fast, example-driven unit tests on the settlement/profit/outstanding/period-close functions as **pure functions** (no I/O). The arithmetic is non-negotiable and cheapest to prove in isolation; cover share splits, effective-dated changes, joint-vs-personal flows, cash-conservation invariants, advances, write-offs, and N-partner (≥3) cases.
- **Tenant isolation must be tested as a first-class behavior** at the API seam: requests authenticated for clinic A must never read or mutate clinic B's data.
- **Prior art:** none — greenfield. These two seams *establish* the project's testing patterns; later features should reuse seam #1 wherever possible and only fall back to pure-module tests for similarly critical isolated logic.

## Out of Scope

- **Clinical/practice-management features:** appointments, scheduling, clinical notes, tooth charts. The product's identity is *money*, not *medicine*.
- **Inventory/stock control** of consumables.
- **Supplier payables / buying on credit** — expenses are always paid on the spot.
- **Inter-partner personal loans** — expressible as a Transfer + note if ever needed.
- **Tax logic** (sales tax, withholding, income tax) — replaced by strong exports for an accountant.
- **Billing/subscriptions, public signup, and go-to-market** — architected for, not built.
- **Multi-branch / multiple locations** — single clinic per tenant.
- **Multi-currency** — PKR only.
- **Differing profit vs expense shares** — they are the same ratio.

## Further Notes

- **Origin:** `Clinic_Cash_Register.xlsx` (two sheets: `Cash Register` journal + `Monthly Summary`) is the case study. The new model deliberately replaces its two free-text expense columns (`S. Expenses` / `H. Expense`) with partner-attributed accounts, and its hand-rolled `M/N` settlement block with the algorithm above.
- **Settlement is deliberately demoted** from hero to a back-office "close the month" flow; the dashboard leads with income/expense intelligence.
- **Deferred fast-follows (not v1, but designed-for):** recurring-expense templates (pair with employees/salaries); WhatsApp/SMS patient payment reminders (phone numbers are stored to enable this — WhatsApp likely the right channel in Pakistan); insight-style analytics ("expenses up 22% vs last month"); historical Excel import (best-effort, clearly labeled pre-migration); native mobile app; subscription billing; full offline-first sync.
- **Number formatting:** consider Pakistani digit grouping (lakh/crore) in display; minor UX detail.
- **Tracker note:** `/setup-matt-pocock-skills` has not been run and this is not yet a git repository, so this PRD is saved to `docs/PRD-clinic-cash-register.md` rather than published to an issue tracker. Initialize the repo + tracker to publish it and apply the `ready-for-agent` label.
