# Money-math test cases (pure seam)

Exhaustive, worked test cases for the pure money-math seam in
[`app/money_math/core.py`](../app/money_math/core.py): `profit`,
`account_balances`, `case_outstanding`, and `settlement`. No I/O, no DB — every
case is `inputs → expected output`, with the arithmetic spelled out so you can
verify **both** the engine and my math.

> Scope chosen deliberately: this list is the *pure arithmetic* only. It does
> not exercise the HTTP API, routers, period-locking, auth/allowlist, offline
> queue, or the PWA. (Those live one layer up, in `services.py` / `routers/`.)

## How to run

The functions take the value types from `app.money_math` (see
[`types.py`](../app/money_math/types.py)). Drop a case straight into
[`tests/test_money_math.py`](test_money_math.py) — it already defines the
helpers used below — or poke at it in a REPL:

```bash
cd api
uv run pytest tests/test_money_math.py -q          # existing suite
uv run python -c "from app.money_math import *; from datetime import date; from fractions import Fraction; print(profit([]))"
```

### Shared fixtures (same as `test_money_math.py`)

```python
A, B, C, D = 1, 2, 3, 4                                   # partner ids
PERSONAL_A = Account(id=10, kind=AccountKind.PERSONAL, owner_partner_id=A)
PERSONAL_B = Account(id=20, kind=AccountKind.PERSONAL, owner_partner_id=B)
PERSONAL_C = Account(id=30, kind=AccountKind.PERSONAL, owner_partner_id=C)
PERSONAL_D = Account(id=40, kind=AccountKind.PERSONAL, owner_partner_id=D)
JOINT      = Account(id=99, kind=AccountKind.JOINT)

income(amount, to_account, *, partner=None, on=date(2026,1,10))   # INCOME, fills to_account
expense(amount, from_account, *, partner=None, on=date(2026,1,10)) # EXPENSE, fills from_account
fiftyfifty(on=date(2026,1,1)) -> [ShareWindow A:1/2, B:1/2]
thirds(on=date(2026,1,1))     -> [ShareWindow A:1/3, B:1/3, C:1/3]
```

## How to read the expected values (settlement)

`settlement(...)` returns a `SettlementStatement`:

- **`profit`** = Σ Income − Σ Expense (all accounts; signs from the leg).
- **`joint_standing`** = net of Income/Expense whose leg is the **JOINT**
  account. Left standing — never redistributed.
- **`personal_profit[pid]`** = net Income/Expense attributed to partner `pid`
  **by the account leg's owner** (NOT by the movement's `partner_id`).
- **`settlement_balance[pid]`** = (personal profit of `pid`) − (`pid`'s share ×
  the window's personal pool), summed per share-window.
  **Positive ⇒ holds more than their share ⇒ pays in. Negative ⇒ is owed.**
  Always sums to 0 (see SET-30 — except when the latent bug in SET-28 fires).
- **`transfers`** = greedy minimal "X pays Y" set: debtors (>0) pay creditors
  (<0); each side sorted by **descending amount, then ascending id**.

**Capital, Drawing, Transfer are invisible to profit and settlement.** They only
move `account_balances`.

### Two rounding/ordering rules to keep straight (verified against `core.py`)

1. **Rounding ties → lowest `partner_id` wins the +1.** `_round_preserving_zero_sum`
   floors each fraction, then hands the leftover +1s to the largest fractional
   remainders; `sorted(..., reverse=True)` is stable, so equal remainders are
   awarded in ascending-id order. A `+1` on the balance means that partner
   **pays in slightly more** (keeps slightly less).
2. **Transfers:** creditors are paid largest-first; ties broken by lowest id.

## Legend

- `[COVERED]` — already asserted in `test_money_math.py` (named test in *italics*); listed for completeness.
- `[NEW]` — not currently covered; the real gaps.
- `[PROBE]` — documents a behavior/limitation worth eyeballing, not a clean pass/fail.
- ⚠ `[BUG]` — I believe this exposes a real defect; expected output shown is the **current (wrong)** output.

---

# A. `profit(movements)`

`profit = Σ INCOME − Σ EXPENSE`; CAPITAL/DRAWING/TRANSFER never count. Account
legs are **not** inspected.

| ID | Title | Tag | Input | Expected |
|----|-------|-----|-------|----------|
| PR-01 | Income − expense | `[COVERED]` *test_profit_is_income_minus_expense* | `income(5000,A)`, `expense(2000,A)` | `3000` |
| PR-02 | Non-profit types ignored | `[COVERED]` *test_profit_ignores_non_profit_movement_types* | income 5000 + CAPITAL 9999 + DRAWING 4444 + TRANSFER 3333 | `5000` |
| PR-03 | Empty list | `[NEW]` | `profit([])` | `0` |
| PR-04 | Expense only → negative | `[NEW]` | `expense(2000, A)` | `-2000` |
| PR-05 | Refund (negative-amount income) lowers profit | `[NEW]` | `income(10000,A)`, `income(-4000,A)` | `6000` |
| PR-06 | Many mixed | `[NEW]` | income 1000,2000,3000 + expense 500,1500 | `6000 − 2000 = 4000` |
| PR-07 | Legs are irrelevant to profit | `[PROBE]` | `Movement(INCOME, 500, date, to_account_id=None)` | `500` |

> **PR-07 note:** `profit()` happily counts an income with **no account leg** —
> it only looks at `type`/`amount`. So `profit()` alone will *not* catch a
> malformed movement; `settlement()` *will* (it raises — see SET-12/13). Don't
> rely on `profit()` as a validity check.

---

# B. `account_balances(movements, opening_balances=None)`

`balance[acct] = opening + Σ(amount where acct is the to-leg) − Σ(amount where acct is the from-leg)`.
Every movement type contributes its legs (unlike profit). No floor — balances may go negative.

| ID | Title | Tag | Input | Expected |
|----|-------|-----|-------|----------|
| AB-01 | Legs sum over opening | `[COVERED]` *test_account_balances_sum_legs_over_opening* | income 5000→A, expense 2000←A, transfer 1000 A→JOINT; opening `{A:1000, JOINT:0}` | `A=3000`, `JOINT=1000` |
| AB-02 | Default opening is 0 | `[COVERED]` *test_account_balances_default_opening_is_zero* | `income(700, A)` | `A=700` |
| AB-03 | Transfer nets zero across the pair | `[NEW]` | transfer 1000 A→JOINT, no opening | `A=-1000`, `JOINT=+1000` (sum 0) |
| AB-04 | Refund reduces the destination balance | `[NEW]` | `income(-4000, A)`; opening `{A:5000}` | `A=1000` |
| AB-05 | Capital up, drawing down | `[NEW]` | CAPITAL 3000→A, DRAWING 1000←A; opening `{A:0}` | `A=2000` |
| AB-06 | Untouched account keeps its opening | `[NEW]` | `income(200,A)`; opening `{A:1000, B:500}` | `A=1200`, `B=500` |
| AB-07 | Same account accumulates | `[NEW]` | income 100→A, 200→A, 300→A | `A=600` |
| AB-08 | Account can go negative (overdraw) | `[PROBE]` | `expense(5000, A)`; opening `{A:1000}` | `A=-4000` |

> **AB-08 note:** there is no non-negative-balance guard in the pure layer. If
> the product needs "you can't pay out more than the account holds," that rule
> must live in the service/router, not here — worth confirming it's enforced (or
> intentionally not) at the HTTP layer.

---

# C. `case_outstanding(agreed_price, payments=(), adjustments=())`

`outstanding = agreed_price − Σ payments − Σ adjustments`. Negative ⇒
advance/credit. Adjustments (discount/write-off) reduce what's owed but are
**not** income.

| ID | Title | Tag | Input | Expected |
|----|-------|-----|-------|----------|
| CO-01 | Payments accumulate | `[COVERED]` *test_outstanding_drops_as_payments_accumulate* | `10000, payments=[1750,2750,2500]` | `3000` |
| CO-02 | Over-payment → negative (advance) | `[COVERED]` *test_overpayment_is_a_negative_outstanding_advance* | `8000, payments=[5000,5000]` | `-2000` |
| CO-03 | Write-off clears, not income | `[COVERED]` *test_writeoff_clears_outstanding_without_being_income* | `4000, payments=[1000], adjustments=[3000]` | `0` |
| CO-04 | No activity = agreed price | `[NEW]` | `10000` | `10000` |
| CO-05 | Refund = negative payment raises it back | `[NEW]` | `10000, payments=[10000, -4000]` | `4000` |
| CO-06 | Discount + write-off both reduce | `[NEW]` | `10000, payments=[2000], adjustments=[1000, 7000]` | `0` |
| CO-07 | Over-adjustment → negative (credit) | `[NEW]` | `5000, payments=[1000], adjustments=[6000]` | `-2000` |
| CO-08 | Zero-price case, payment → advance | `[NEW]` | `0, payments=[500]` | `-500` |

> **CO-05 note:** this is exactly how a real refund must net at the case level —
> the refund row is an `income(-amount)`, which appears in `payments` as a
> negative number and *raises* outstanding. Confirm the service feeds the
> negative-income row into the `payments` list (it does, via the INCOME query in
> `services.case_outstanding_value`).

---

# D. `settlement(movements, share_windows, accounts)`

The crown jewel. Unless stated, accounts are `[PERSONAL_A, PERSONAL_B]` (or
`+PERSONAL_C` for 3 partners) and the window is `fiftyfifty()` / `thirds()`.

### D.1 — Already covered (listed for completeness)

| ID | Title | Tag | Gist | Expected |
|----|-------|-----|------|----------|
| SET-01 | 2-partner single transfer | `[COVERED]` *test_two_partner_settlement_single_transfer* | A collects 10000, 50/50 | bal `A=+5000, B=-5000`; `A→B 5000`; profit 10000 |
| SET-02 | Capital/drawing don't move settlement | `[COVERED]` *test_capital_and_drawing_do_not_change_settlement* | add CAPITAL/DRAWING noise | identical balances & profit |
| SET-03 | Joint stays standing + cash conserved | `[COVERED]` *test_joint_pool_stays_standing_and_cash_is_conserved* | personal + joint mix | `joint_standing=3500`; `A=+4500, B=-4500`; Σpersonal+joint=profit |
| SET-04 | 3-partner minimal transfers | `[COVERED]` *test_three_partner_minimal_transfers* | A 9000, B 3000, thirds | `A=+5000,B=-1000,C=-4000`; `A→C 4000, A→B 1000` |
| SET-05 | Mid-period share change (late joiner) | `[COVERED]` *test_mid_period_share_change_does_not_backdate_new_partner* | window split at 01-15 | `A=-500, B=-1500, C=+2000` |
| SET-06 | Indivisible thirds, zero-sum preserved | `[COVERED]` *test_settlement_rounds_to_integers_preserving_zero_sum* | 10000, thirds | `A=+6667, B=-3333, C=-3334` (sum 0) |
| SET-07 | No window covers a date → `ValueError` | `[COVERED]` *test_settlement_raises_when_no_window_covers_a_movement_date* | movement on 2025-12-31, window from 2026-01-01 | raises `ValueError` |

### D.2 — Degenerate & error paths `[NEW]`

**SET-08 — Empty `share_windows` → `ValueError`**
- Input: any movements, `share_windows=[]`.
- Expected: raises `ValueError("settlement requires at least one share window")`.

**SET-09 — No movements → all zeros**
- Input: `movements=[]`, `fiftyfifty()`, `[PERSONAL_A, PERSONAL_B]`.
- Expected: `profit=0`, `joint_standing=0`, `personal_profit={A:0,B:0}`,
  `settlement_balance={A:0,B:0}`, `transfers=[]`.

**SET-10 — Joint income only → standing, nobody settles**
- Input: `income(4000, JOINT, partner=A)`, `fiftyfifty()`, `[PERSONAL_A,PERSONAL_B,JOINT]`.
- Expected: `profit=4000`, `joint_standing=4000`, `personal_profit={A:0,B:0}`,
  `settlement_balance={A:0,B:0}`, `transfers=[]`.

**SET-11 — Personal account with no owner → `ValueError`**
- Setup: `BROKEN = Account(id=50, kind=PERSONAL, owner_partner_id=None)`.
- Input: `income(1000, BROKEN)`, `fiftyfifty()`, `[BROKEN, PERSONAL_B]`.
- Expected: raises `ValueError("personal account 50 has no owner partner")`.

**SET-12 — Income with no account leg → `ValueError`**
- Input: `Movement(INCOME, 1000, date(2026,1,10), to_account_id=None)`.
- Expected: raises `ValueError(... "has no account leg to settle against")`.
- Contrast PR-07: `profit()` would have counted this 1000 silently.

**SET-13 — Expense with no account leg → `ValueError`**
- Input: `Movement(EXPENSE, 1000, date(2026,1,10), from_account_id=None)`.
- Expected: raises `ValueError(...)` (the EXPENSE reads `from_account_id`).

### D.3 — Share-window boundary attribution `[NEW]` (ADR-0004)

Windows for SET-14/15: `W1` eff `2026-01-01` `{A:1/2, B:1/2}`; `W2` eff
`2026-01-15` `{A:1/3, B:1/3, C:1/3}`. Accounts `[PERSONAL_A,PERSONAL_B,PERSONAL_C]`.
`partner_ids = {A,B,C}`.

**SET-14 — Date *exactly on* the boundary lands in the NEW window**
- `window_for` uses `effective_from <= d`, so `2026-01-15` is **W2**.
- Input: `income(3000, PERSONAL_C, partner=C, on=date(2026,1,15))`.
- Work: W2 pool 3000; `A=−1000, B=−1000, C=3000−1000=+2000`. W1 empty.
- Expected: `settlement_balance={A:-1000,B:-1000,C:+2000}`; `transfers: C→A 1000, C→B 1000`; `profit=3000`.

**SET-15 — One day earlier lands in the OLD window (pre-join collection is fully shared)**
- Input: `income(3000, PERSONAL_C, partner=C, on=date(2026,1,14))` → **W1**.
- Work: W1 pool 3000; C's W1 share is `0`. `A=0−1500=−1500`, `B=−1500`, `C=3000−0=+3000`.
- Expected: `settlement_balance={A:-1500,B:-1500,C:+3000}`; `transfers: C→A 1500, C→B 1500`; `profit=3000`.
- **Why it matters:** money C collected *before* C had a share belongs to the
  then-partners A & B — so C must pay all of it out. Flip one day (SET-14) and C
  keeps 2/3. A payment mis-dated across the boundary silently changes who's owed.

### D.4 — Rounding & tie-breaking `[NEW]`

**SET-16 — Odd pool, 2 partners, tie → lowest id pays the extra rupee**
- Input: `income(5, PERSONAL_A, partner=A)`, `fiftyfifty()`.
- Work: `A=5−5/2=2.5`, `B=−2.5`. floors `A=2, B=−3` (sum −1, deficit 1).
  Remainders both `0.5` → tie → award +1 to **A** (lowest id).
- Expected: `settlement_balance={A:+3, B:-3}`; `transfers: A→B 3`.
- Note: the +1 lands on A's balance ⇒ A **pays in 3** (keeps 2), B receives 3.

**SET-17 — Indivisible thirds, the tie-break made explicit**
- Input: `income(100, PERSONAL_A, partner=A)`, `thirds()`.
- Work: `A=200/3≈66.67, B=C=−100/3≈−33.33`. floors `A=66,B=−34,C=−34` (sum −2,
  deficit 2). All three remainders `2/3` → tie → +1 to **A and B** (two lowest ids).
- Expected: `settlement_balance={A:+67, B:-33, C:-34}`; `transfers: A→C 34, A→B 33`; `profit=100`.
- This is SET-06 (the `[COVERED]` 10000 case) shrunk so the tie-break is obvious:
  **C, the highest id, eats the −1.**

### D.5 — Refunds & loss periods through settlement `[NEW]`

**SET-18 — Refund reduces the collector's personal profit and the pool**
- Input: `income(10000, PERSONAL_A, partner=A)`, `income(-4000, PERSONAL_A, partner=A)`, `fiftyfifty()`.
- Work: personal `A=6000, B=0`, pool 6000. `A=6000−3000=+3000, B=−3000`.
- Expected: `settlement_balance={A:+3000,B:-3000}`; `transfers: A→B 3000`; `profit=6000`.

**SET-19 — Loss period: the *non-collector* pays the collector**
- Input: `income(1000, PERSONAL_A, partner=A)`, `income(-5000, PERSONAL_A, partner=A)`, `fiftyfifty()`.
- Work: personal `A=−4000, B=0`, pool −4000.
  `A=−4000−(½)(−4000)=−2000`, `B=0−(½)(−4000)=+2000`.
- Expected: `settlement_balance={A:-2000,B:+2000}`; `transfers: B→A 2000`; `profit=-4000`.
- **Why it matters:** A absorbed a 4000 net loss for the partnership; B (collected
  nothing) must pay A 2000 to share the loss 50/50. A negative pool still settles.

### D.6 — Attribution semantics: account leg, not `partner_id` `[NEW]` ⭐

**SET-20 — Settlement follows the account owner; the movement's `partner_id` is ignored**
- Input: `income(10000, PERSONAL_A, partner=A)`, `expense(2000, PERSONAL_A, partner=B)`, `fiftyfifty()`.
  (The expense is *tagged* `partner=B` but its leg is **A's** personal account.)
- Work: both legs hit A → personal `A=10000−2000=8000, B=0`, pool 8000.
  `A=8000−4000=+4000, B=−4000`.
- Expected: `settlement_balance={A:+4000,B:-4000}`; `transfers: A→B 4000`; `profit=8000`.
- **Contrast (what you'd get if `partner_id` drove it):** `A=+6000, B=-6000`,
  `A→B 6000`. It does **not**. The expense burdens the account's owner (A), not
  the tagged collector (B).
- **Why it matters:** if the UI lets you log an expense from A's account while
  attributing it to B, settlement quietly charges A. Verify the data-entry flow
  can't create this mismatch (or that it's intended).

**SET-21 — Same collector, different account → completely different settlement**
- Variant 1 (personal): `income(10000, PERSONAL_A, partner=A)`, `fiftyfifty()`
  → `A=+5000, B=-5000`, `A→B 5000`, `joint_standing=0`.
- Variant 2 (joint): `income(10000, JOINT, partner=A)`, `fiftyfifty()`,
  accounts include `JOINT`
  → `personal_profit={A:0,B:0}`, `settlement_balance={A:0,B:0}`, `transfers=[]`,
  `joint_standing=10000`. profit 10000 in both.
- **Why it matters:** picking the wrong destination account (personal vs joint)
  silently flips whether *anyone owes anyone*. This is the highest-leverage
  data-entry error in the whole system — worth a guardrail check at the UI/API.

### D.7 — Multi-window summation `[NEW]`

**SET-22 — Three windows, movements in each, balances summed per window**
- Windows: `W1` 01-01 `{A:½,B:½}`; `W2` 01-11 `{A:⅓,B:⅓,C:⅓}`; `W3` 01-21 `{A:½,B:½}`.
  Accounts `[A,B,C]`; `partner_ids={A,B,C}`.
- Input: `income(600,A,on=01-05)` (W1), `income(900,B,on=01-15)` (W2), `income(300,C,on=01-25)` (W3).
- Work per window:
  - W1 pool 600: `A=+300, B=−300, C=0` (C share 0 here).
  - W2 pool 900: `A=−300, B=+600, C=−300`.
  - W3 pool 300: `A=−150, B=−150, C=+300` (C share 0 again — left after W2).
  - Sum: `A=−150, B=+150, C=0`.
- Expected: `settlement_balance={A:-150,B:+150,C:0}`; `transfers: B→A 150`; `profit=1800`.
- Note C nets to 0: owed 300 in W2 (had a ⅓ share, collected nothing), pays 300
  in W3 (collected with no share).

**SET-23 — Partner absent from a window carries 0 share there**
- Windows: `W1` 01-01 `{A:½,B:½}`; `W2` 01-15 `{A:½,C:½}` (B absent, sums to 1). Accounts `[A,B,C]`.
- Input: `income(1000, PERSONAL_A, partner=A, on=01-20)` (W2).
- Work: W2 pool 1000; `A=1000−500=+500`, `B=0−0=0` (absent ⇒ share 0), `C=0−500=−500`.
- Expected: `settlement_balance={A:+500,B:0,C:-500}`; `transfers: A→C 500`; `profit=1000`.

**SET-24 — A future window puts a partner on the roster but doesn't distort today**
- Windows: `W1` 01-01 `{A:½,B:½}`; `W2` 06-01 `{A:⅓,B:⅓,C:⅓}`. Accounts `[A,B,C]`.
- Input: `income(1000, PERSONAL_A, partner=A, on=01-10)` (W1 only).
- Work: `partner_ids={A,B,C}` (C from W2). W1 pool 1000; `A=+500,B=−500,C=0` (C share 0 in W1). W2 empty.
- Expected: `settlement_balance={A:+500,B:-500,C:0}`; `transfers: A→B 500`; `profit=1000`.
- Note: C shows up as `0` even though C isn't "active" yet.

### D.8 — Joint expense & big numbers `[NEW]`

**SET-25 — Joint expense drives `joint_standing` negative**
- Input: `expense(500, JOINT, partner=B)`, `fiftyfifty()`, accounts include JOINT.
- Expected: `profit=-500`, `joint_standing=-500`, `personal_profit={A:0,B:0}`,
  `settlement_balance={A:0,B:0}`, `transfers=[]`.

**SET-26 — Large amounts: no float, no overflow**
- Input: `income(10_000_000_000, PERSONAL_A, partner=A)`, `fiftyfifty()`.
- Expected: `settlement_balance={A:+5_000_000_000, B:-5_000_000_000}`;
  `transfers: A→B 5_000_000_000`; `profit=10_000_000_000`. (Python ints +
  `Fraction` are exact — confirms no precision loss at scale.)

### D.9 — Invariants & limitations `[PROBE]`

**SET-27 — Cash-conservation, assert on *every* settlement case**
- For any inputs: `sum(personal_profit.values()) + joint_standing == profit`
  **and** `sum(settlement_balance.values()) == 0` **and** the transfers net to
  the balances: for each `pid`, `Σ(out) − Σ(in) == settlement_balance[pid]`.
- Use this as a property check layered on top of every D-case (it's the single
  strongest guard). **Exception:** SET-28 below currently *violates* the
  zero-sum half — that's the bug.

**SET-28 — ⚠ `[BUG]` Owner of a personal account is absent from *every* share window**
- Setup: windows `fiftyfifty()` (only A, B). Accounts `[PERSONAL_A, PERSONAL_B, PERSONAL_D]` (D = partner 4).
- Input: `income(6000, PERSONAL_D, partner=D)`.
- **Current (wrong) output:** `profit=6000`, `joint_standing=0`,
  `personal_profit={A:0, B:0}` (D's 6000 has **vanished**),
  `settlement_balance={A:-2999, B:-2999}` (**sum = −5998, not 0**), `transfers=[]`
  (no debtor exists, so nobody ever pays the two "owed" partners).
- **Root cause:** `partner_ids` is built only from the share windows, so D is
  never a key. But D's 6000 is still added into the per-window `pool`
  (`pool = sum(wp.values())` includes the stray `D` key). The balance loop then
  hands A and B each `−½·6000` while crediting D nothing — so the fractions no
  longer sum to 0, and `_round_preserving_zero_sum` (which *assumes* they do:
  `deficit = -sum(floors) = 6000`, then `by_remainder[:6000]` on a 2-element
  list) produces garbage. D's profit is silently redistributed to A & B with no
  offsetting debtor.
- **When it can happen:** a partner who owns a personal account but has no row in
  the current/any share window (e.g. created a personal account, then a share
  window that omits that partner — the API's `share-windows` POST only checks
  the shares sum to 1, not that every account-owning partner is included).
- **Suggested fix to verify against:** in `settlement`, after collecting owners,
  assert every personal-account owner that appears in the movements is in
  `partner_ids` (raise `ValueError`), **or** fold absent owners in with a 0
  share. Then this case should either raise cleanly or settle to a zero-sum
  result.

**SET-29 — `[PROBE]` Two windows with the *same* `effective_from`**
- Windows: `W1` 01-01 `{A:½,B:½}` and `W2` 01-01 `{A:⅓,B:⅓,C:⅓}` (same date).
- `window_for` loops in sorted order and keeps the **last** match, and Python's
  sort is stable, so the *input order* of two equal-dated windows decides which
  one wins — silently. Feed a movement on/after 01-01 and confirm which shares
  apply, then decide whether same-date windows should be rejected upstream.
- Expected: behavior is order-dependent (no error). Treat as "should the API
  forbid duplicate `effective_from`?" — likely yes.

**SET-30 — `[PROBE]` Greedy transfers vs. truly-minimal (4 partners)**
- Input balances (construct via collections): `{A:+5000, B:+1000, C:-2000, D:-4000}`
  e.g. A collects 6000 & B 2000 into personal, C & D collect 0, with a 4-way share
  that yields those balances.
- Greedy output (debtors A,B; creditors D,C by descending amount):
  `A→D 4000, A→C 1000, B→C 1000` — **3 transfers**, which *is* optimal here
  (no proper zero-sum subset exists, so min = n−1 = 3).
- **Caveat to keep in mind:** minimizing settlement cash-flows is NP-hard in
  general; `_minimal_transfers` is a greedy heuristic. For 2–3 partners it is
  always minimal; at 4+ it can occasionally emit one extra transfer when a
  zero-sum subset exists that largest-first matching skips. For a small clinic
  this is cosmetic (the *amounts* are always correct and net out), but if you
  add partners, spot-check the transfer **count**, not just the totals.

---

# Coverage summary

| Function | Cases | New gaps | Already covered |
|----------|-------|----------|-----------------|
| `profit` | PR-01…07 | PR-03,04,05,06,07 | PR-01, PR-02 |
| `account_balances` | AB-01…08 | AB-03…08 | AB-01, AB-02 |
| `case_outstanding` | CO-01…08 | CO-04…08 | CO-01, CO-02, CO-03 |
| `settlement` | SET-01…30 | SET-08…26 | SET-01…07 |

## Findings worth acting on (independent of testing)

1. **⚠ SET-28 — real bug.** An account owner absent from every share window
   breaks the zero-sum invariant and loses their profit. Add a guard in
   `settlement` (raise, or include with 0 share). Highest priority.
2. **SET-20 / SET-21 — silent misattribution.** Settlement is driven by the
   account leg's owner and by personal-vs-joint routing, **not** by the
   movement's `partner_id`. A wrong account choice at data-entry time changes who
   owes whom with no error. Confirm the UI/API constrains account selection (e.g.
   only the collecting partner's own personal account, or the joint account).
3. **SET-14 / SET-15 — boundary dating.** A payment dated one day across a
   share-window change reassigns the whole amount. Make sure the entry date is
   trustworthy / hard to fat-finger.
4. **SET-29 — duplicate `effective_from`.** Same-date windows resolve by input
   order. Consider rejecting them when creating share windows.
5. **AB-08 — no overdraw guard** in the pure layer; verify whether the service
   layer is meant to prevent paying out more than an account holds.
