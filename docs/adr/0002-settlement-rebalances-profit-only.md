# Settlement rebalances profit only, never capital, drawings, or opening balances

## Decision

At period close, settlement equalizes each partner's share of the **period's profit** and nothing else. The figure it works on — `personal_i` — is defined strictly as **profit that flowed through a partner's personal accounts**: `(income collected into personal accounts) − (expenses paid from personal accounts)`. `Capital`, `Drawing`, `Transfer`, and **opening balances** change what cash sits in an account but are **invisible to settlement**.

`money-math` MUST include a test asserting that adding a Capital contribution and a Drawing to a scenario does **not** change any partner's settlement balance.

## Why

A partnership settlement must not reshuffle a partner's *own* money — capital they injected from outside, cash they drew for personal use, or money they already had at go-live. Only the clinic's earned profit gets rebalanced.

The trap: the natural reading of "holding" is "the cash balance of the account," which would compute `personal_i` by summing *all* movements. That version redistributes capital/drawings between partners — and it passes every test the PRD originally listed, because none of them exercised a Capital or Drawing movement. So we pin the profit-only definition explicitly, rename the quantity away from "holding" (see glossary: **attributed personal profit**), and make the exclusion a mandatory test.

## Consequences

- The invariant `Σ personal_i + joint = P` holds for this profit-flow definition, and is a `money-math` test.
- A computed settlement transfer can be **unfundable** (a partner may owe more profit than their account currently holds, e.g. because they drew cash out). How the app handles that is a separate decision.
