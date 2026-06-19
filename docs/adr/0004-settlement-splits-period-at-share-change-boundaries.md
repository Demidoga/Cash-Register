# Settlement splits a period at effective-dated share-change boundaries

## Decision

When a partner's share changes mid-period, settlement does **not** apply one share vector to the whole period's profit. Instead it splits the period at each share-change date: every `Income`/`Expense` movement is attributed to the **share window** its date falls in, each window is settled by the shares effective in that window, and the results are summed.

Consequently the pure `money-math` settlement function takes **effective-dated share windows** plus **date-stamped movements** — not a single profit number and a single share vector. A ≥3-partner, mid-period-change scenario is a mandatory test.

## Why

User story #12: "share percentages are effective-dated, so a partner joining later does not receive a share of earlier profit." If a third partner joins on the 15th, profit earned on days 1–14 must be split only among the original partners. Applying month-end shares to the whole month would hand the new partner a slice of earlier profit (the exact thing forbidden); forbidding mid-period changes would make every share change require closing the books that day.
