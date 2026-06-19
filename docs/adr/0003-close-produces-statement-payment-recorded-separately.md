# Period close produces a locked settlement statement; settlement payments are recorded separately

## Decision

Closing a period computes and **locks** a **settlement statement** — the obligations for that period ("Saad owes Hassan 5,000"). Closing does **not** move any cash. The actual **settlement payment** is recorded later, as a real `Transfer` movement, when the partner truly pays — dated when the cash moves and linked back to the statement.

## Why

The PRD requires that "the books show the cash that actually changed hands." Auto-posting the transfer at close would put money on the books before it moved, and — in the case where the paying partner has drawn their cash out — could drive an account negative. A locked statement plus a later real payment keeps the ledger always true.

This is also consistent with the correction model already chosen: a closed period's income/expense entries stay locked; the settlement payment is simply a new forward-dated `Transfer`, the same way corrections to closed periods are made via forward reversing entries — never by editing locked history.

## Consequences

- A settlement statement can be **open** (computed, awaiting payment) or **fully paid** (its obligations matched by recorded Transfers). The dashboard's "needs attention" panel can surface unpaid statements.
- Locking applies to the period's entries, not to the act of recording the later settlement payment (which lands in the open period).
