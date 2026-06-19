# Money movements are single typed rows with from/to legs, not double-entry

## Decision

A money movement is **one row** carrying a `type` (`Income · Expense · Transfer · Capital · Drawing`), an integer-rupee `amount`, a `date`, an attributed partner, an optional note, and optional `from_account` / `to_account` legs: Income/Capital fill `to`; Expense/Drawing fill `from`; Transfer fills both. An account's balance is the sum of its legs (plus its opening balance); profit is `Σ Income − Σ Expense`. We do **not** model a full double-entry general ledger.

## Why

The app tracks **cash sitting in real accounts**, not accrual accounting. Full double-entry would force contra-accounts for equity, drawings, and profit — concepts the two doctors never reason about — for rigor a cash-tracking app doesn't need. The single typed-row model still gives provable balances (legs always reconcile) and a clean profit figure. The PRD already routed formal accounting to "strong exports for the accountant" rather than building an accrual GL.

## Consequences

- The `money_movements` table is the core ledger; settlement payments are `Transfer` rows linked to a settlement statement.
- If formal accrual accounting is ever needed, it is derived at export time or in a later system — not retrofitted into this table.
