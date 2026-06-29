# Application (HTTP / integration) test cases

Companion to [`MONEY-MATH-TEST-CASES.md`](MONEY-MATH-TEST-CASES.md). Those cover
the pure arithmetic; **these cover everything the arithmetic can't reach** — the
behavior you only see when real HTTP requests hit the routers + `services.py` +
the DB: validation, auth/allowlist, tenant scoping, period-locking, the
settlement-payment flow, soft-delete, reports/dashboard semantics, and the
frontend offline queue.

Every status code and money figure below was **executed against a live
`TestClient`** (the same in-memory setup as `conftest.py`) — they're observed,
not assumed.

## How to run

```bash
cd api
uv run pytest tests/test_features.py tests/test_walking_skeleton.py \
              tests/test_access_control.py tests/test_members.py -q
```

The `client` fixture in [`conftest.py`](conftest.py) gives a `TestClient` on a
fresh in-memory DB; `tests/util.py` has `setup_clinic`, `auth(email)`, and
`make_token(...)` (which accepts `secret=`, `audience=`, `sub=`, `name=` and is
how you forge the adversarial tokens in section A). The standard fixture clinic:
**Saad** & **Hassan**, 50/50, each a personal cash account + a shared **Joint**.

## Legend

- `[COVERED]` — already asserted (existing test named in *italics*); listed so you see the whole surface.
- `[NEW]` — real gap, worth adding.
- `[PROBE]` — behavior/limitation to eyeball; needs a manual toggle or hand-seeded state.
- ⚠ `[GAP]` — accepted today but arguably *shouldn't* be; a correctness/guardrail hole. Expected value shown is the **current** behavior.

---

# A. Authentication — JWT verification (`security.py`, `deps.get_claims`)

Authentication only proves identity; the token is verified before any allowlist check.

| ID | Title | Tag | Request | Expected |
|----|-------|-----|---------|----------|
| A-01 | No token | `[COVERED]` *test_no_token_is_unauthorized* | `GET /me` no header | `401` |
| A-02 | Garbage token | `[COVERED]` *test_garbage_token_is_unauthorized* | `Bearer not-a-jwt` | `401` |
| A-03 | Signed with wrong secret | `[COVERED]` *test_token_signed_with_wrong_secret_is_unauthorized* | `make_token(secret="attacker")` | `401` |
| A-04 | Header without `Bearer ` prefix | `[NEW]` | `Authorization: <raw token>` | `401` "missing bearer token" |
| A-05 | Token with no `email` claim | `[NEW]` | valid sig, drop `email` | `401` "token has no email claim" |
| A-06 | Expired token | `[NEW]` | `exp` in the past | `401` "invalid token: Signature has expired" |
| A-07 | Wrong audience | `[NEW]` | `aud="wrong"` | `401` "invalid token: Audience doesn't match" |
| A-08 | Unsupported / `none` alg | `[NEW]` | header `alg: none` (or HS384) | `401` "unsupported token algorithm" |
| A-09 | ES256/RS256 but `SUPABASE_URL` unset | `[PROBE]` | asym-signed token, no `SUPABASE_URL` | `401` (AuthError: JWKS not configured). Needs an asym key + cleared `SUPABASE_URL`. |
| A-10 | User belongs to >1 clinic | `[PROBE]` | hand-seed a 2nd `Membership` (via the `db` fixture, like *test_cannot_revoke_self...*) then `GET /me` | `500` "clinic resolution is not implemented" (deliberate fail-loud, ADR-0005) |

---

# B. Authorization, allowlist & tenant scoping (`deps.get_current_member`, `services.get_scoped`)

| ID | Title | Tag | Request | Expected |
|----|-------|-----|---------|----------|
| B-01 | Valid login, not on allowlist | `[COVERED]` *test_valid_login_not_on_allowlist_is_forbidden* | `GET /me` / `POST /patients` as stranger | `403` "not on the clinic allowlist" |
| B-02 | Allowlisted owner | `[COVERED]` *test_allowlisted_owner_is_permitted* | `GET /me` as owner | `200` |
| B-03 | Revoked user with a still-valid JWT | `[COVERED]` *test_revoke_blocks_access_despite_valid_jwt* | revoke, then act | `403` (blocked at authorization, not the token) |
| B-04 | Unknown id is 404, never leaked/500 | `[COVERED]` *test_unknown_settlement_statement_is_not_found_not_leaked* | `GET /settlements/999999` | `404` |
| B-05 | **2nd authenticated user calls `/setup` after clinic exists** | `[NEW]` | `POST /setup` as a non-owner stranger | `409` "clinic already set up" — **not 403.** `/setup` uses `get_identity` (bootstrap path), so the clinic-exists guard fires before any allowlist check. Confirm that's intended. |
| B-06 | Cross-clinic read returns 404, not another clinic's row | `[PROBE]` | needs a 2nd clinic (only constructable by hand-seed, since `/setup` is single-clinic-guarded) | every `get_scoped` miss → `404` |

---

# C. Input validation (Pydantic `Field` + router guards)

| ID | Title | Tag | Request | Expected |
|----|-------|-----|---------|----------|
| C-01 | Zero/negative amount, every money endpoint | `[NEW]` | `amount: 0` or `-5` on `/payments`, `/expenses`, `/transfers`, `/capital`, `/drawings`, `/refunds` | `422` "Input should be greater than 0" (`Field(gt=0)`) |
| C-02 | Transfer to the same account | `[NEW]` | `from_account_id == to_account_id` | `422` "transfer needs two different accounts" |
| C-03 | Period `end_date < start_date` | `[NEW]` | `POST /periods` reversed dates | `422` "end_date before start_date" |
| C-04 | Case `agreed_price < 0` | `[NEW]` | `POST /cases` price `-1` | `422` (`Field(ge=0)`) |
| C-05 | Personal account with no owner | `[NEW]` | `POST /accounts` `{kind:personal}` no owner | `422` "personal account needs a valid owner_partner_id" |
| C-06 | Joint account with an owner | `[NEW]` | `POST /accounts` `{kind:joint, owner_partner_id:X}` | `422` "joint account must not have an owner" |
| C-07 | `/setup` personal account, bad `owner_partner_index` | `[NEW]` | index out of range / missing | `422` "personal account needs a valid owner_partner_index" |
| C-08 | `/setup` joint account with an `owner_partner_index` | `[NEW]` | joint + index set | `422` "joint account must not have an owner" |
| C-09 | `/setup` shares don't sum to 1 | `[COVERED]` *test_setup_rejects_shares_that_do_not_sum_to_one* | 1/2 + 1/3 | `422` |
| C-10 | `/share-windows` shares don't sum to 1 | `[NEW]` | config-time window 1/3 + 1/3 | `422` "partner shares must sum to 1" |
| C-11 | `/share-windows` unknown partner id | `[NEW]` | `partner_id: 99999` | `404` "partner 99999 not found" |
| C-12 | Discount without an amount | `[NEW]` | `POST /cases/{id}/discount` `{}` | `422` "amount is required" |
| C-13 | Write-off without an amount → clears outstanding | `[COVERED]` *test_discount_and_writeoff_reduce_outstanding_not_income* | `POST /cases/{id}/write-off` `{}` | `201`, outstanding → `0` |
| C-14 | Invite invalid email | `[COVERED]` *test_invalid_email_is_rejected* | `not-an-email` | `422` |
| C-15 | Missing required body field | `[NEW]` | `/payments` without `case_id` | `422` (Pydantic) |
| C-16 | `/setup` idempotent guard | `[COVERED]` *test_setup_is_idempotent_guarded* | second `/setup` | `409` |

---

# D. ⚠ Money-routing guardrails — the silent-misattribution holes

These are the HTTP-layer manifestation of findings #2 from the money-math doc
(SET-20/21). **All verified — the API accepts them.** Combined with settlement
following the *account leg's owner*, a wrong account choice quietly rewrites who
owes whom, with no error.

**D-01 — Take a payment into the JOINT account** ⚠`[GAP]`
- `POST /payments {case_id, account_id: JOINT, partner_id: Saad, amount: 4000}` → **`201`**.
- The income's `to_account` is the joint account, so at settlement it becomes
  `joint_standing` (left standing), **not** anyone's personal profit. Nothing
  warns that this payment won't enter the profit split.

**D-02 — Take a payment into *another partner's* personal account** ⚠`[GAP]`
- `POST /payments {account_id: HassanCash, partner_id: Saad, amount: 6000}` → **`201`**.
- `partner_id` (the collector, Saad) is recorded but **ignored by settlement**;
  the 6000 is attributed to **Hassan** (the account's owner). No check that the
  account belongs to the collecting partner.

**D-03 — The combined real scenario (verified end-to-end)** ⚠`[GAP]` ⭐
- Saad collects the clinic's entire 10000: 4000 into **Joint** (D-01) + 6000 into
  **Hassan's** account (D-02), both in a Jan period. Close the period.
- **Observed result:** `profit=10000`, `joint_standing=4000`,
  `settlement_balance = {Saad: -3000, Hassan: +3000}`, obligation **Hassan → Saad 3000**.
- **Saad collected every rupee, yet the statement says Hassan owes Saad** — and
  only 6000 of the 10000 entered the personal split (4000 sits in joint). This is
  the single most dangerous data-entry mistake in the app: it produces a
  *plausible-looking but wrong* settlement.

**D-04 — Log an expense from another partner's account** ⚠`[GAP]`
- `POST /expenses {account_id: SaadCash, partner_id: Hassan, amount: 2000}` → `201`.
- Settlement charges the expense to **Saad** (account owner), not Hassan (tagged). Mirror of D-02.

**D-05 — Settlement payment between accounts unrelated to the obligation** ⚠`[GAP]`
- For an obligation "Saad pays Hassan", `POST /settlements/{id}/payments
  {obligation_id, from_account_id: JOINT, to_account_id: SaadCash}` → **`201`**.
- The accounts aren't validated against the obligation's partners; the transfer's
  `partner_id` is forced to `obligation.from_partner_id` but the cash legs can be
  anyone's. The obligation is marked paid regardless.

**D-06 — Nonexistent case / account / partner** `[NEW]`
- `POST /payments {case_id: 99999, ...}` → `404` "case not found" (likewise account/partner). Good — only the *valid-but-wrong* account is unguarded.

> **Recommendation:** constrain account selection at the API — a payment/expense
> account must be the **collecting partner's own personal account or the joint
> account**; settlement-payment `from`/`to` accounts should belong to the
> obligation's two partners. Until then, D-01…D-05 are correctness footguns the
> tests above will catch if you add the guards.

---

# E. Period close & locking

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| E-01 | Close an empty period | `[NEW]` | period with no movements → close | `200`, `profit=0`, all balances `0`, `obligations=[]` |
| E-02 | Close a period whose movement predates every share window | `[NEW]` | movement on 2025-12-15, earliest window 2026-01-01 → close | `422` "no share window effective on 2025-12-15" (ValueError→422) |
| E-03 | Movement dated outside the period is ignored by its settlement | `[NEW]` | pay 1000 dated 2026-05-10, close Jan period | the 1000 is **not** in the Jan statement (settlement filters by `start..end`) |
| E-04 | **Overlapping periods are allowed** | ⚠`[GAP]` | create Jan 1–31, then Jan 15–Feb 15 | both `201`. Nothing prevents overlap; `closed_period_covering` then returns *one* arbitrary match. Consider rejecting overlaps. |
| E-05 | Double close | `[COVERED]` *test_double_close_is_rejected* | close twice | `409` "period already closed" |
| E-06 | Backdated entry into a closed period | `[COVERED]` *test_full_skeleton...* / *test_edit_void_restore_and_lock* | payment/edit/void dated inside closed | `409` |
| E-07 | Edit a movement's date *into* a closed period | `[NEW]` | `PATCH /movements/{id} {date: <inside closed>}` | `409` (the new date is also `_assert_open`-checked) |
| E-08 | Restore a not-voided movement | `[NEW]` | `POST /movements/{id}/restore` on a live row | `409` "movement is not voided" |
| E-09 | Restore a voided movement whose date now sits in a closed period | `[NEW]` | void in open period, close a covering period, restore | `409` |

---

# F. Settlement-payment flow (`POST /settlements/{id}/payments`)

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| F-01 | Happy path: pay obligation as a Transfer | `[COVERED]` *test_full_skeleton...* | pay the obligation | `201`, type `transfer`, amount = obligation amount, obligation `paid=true`, profit unchanged, balances move |
| F-02 | Pay the same obligation twice | `[NEW]` | pay, then pay again | 1st `201`, 2nd `409` "obligation already paid" |
| F-03 | Pay dated inside a closed period | `[NEW]` | obligation payment dated within a closed span | `409` "that date falls in a closed period" (settlement cash must land in the open period) |
| F-04 | `obligation_id` belonging to a different statement | `[NEW]` | mismatched obligation/statement | `404` "obligation not found" |
| F-05 | Nonexistent statement | `[NEW]` | `POST /settlements/999999/payments` | `404` "settlement statement not found" |
| F-06 | Accounts unrelated to the obligation partners | see D-05 ⚠`[GAP]` | arbitrary `from`/`to` | `201` (currently unguarded) |

---

# G. Corrections & adjustments

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| G-01 | Edit amount re-derives case outstanding | `[COVERED]` *test_edit_void_restore_and_lock* | `PATCH /movements/{id} {amount}` | outstanding recomputed |
| G-02 | Void then restore round-trips outstanding | `[COVERED]` *same* | delete → restore | outstanding falls then returns |
| G-03 | Edit to a nonexistent `category_id` | `[NEW]` | `PATCH /movements/{id} {category_id: 99999}` | `404` "category not found" |
| G-04 | Discount then write-off the remainder | `[COVERED]` *test_discount_and_writeoff_reduce_outstanding_not_income* | discount 1000, write-off rest | outstanding `0`, income unchanged |
| G-05 | Over-adjust (write-off > remaining) | `[NEW]` | write-off a fixed amount beyond outstanding | outstanding goes negative (credit); confirm intended vs. clamped |
| G-06 | Refund raises outstanding & lowers profit | `[COVERED]` *test_refund_raises_outstanding_and_lowers_profit* | `POST /refunds` | outstanding ↑, profit ↓, balance ↓ |

---

# H. Dashboard & reports semantics

**H-01 — ⚠ Dashboard net-profit is period-scoped, but account balances are clinic-wide (all-time)** ⚠`[GAP]` ⭐ (verified)
- Setup: in a Jan period, collect 4000 (Joint) + 6000 (a personal acct); also
  collect 1000 dated **2026-05-10** (outside the period). `GET /dashboard/summary?period_id=<Jan>`.
- **Observed:** `income=10000`, `net_profit=10000` (the May 1000 correctly
  excluded from the period total) **but** `account_balances` total `11000` — the
  out-of-period 1000 *is* in the balances. The headline number and the balances
  don't reconcile. Decide the intended semantics and label them (e.g. "balances
  are live/all-time", "profit is this period").

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| H-02 | Dashboard with no periods at all | `[NEW]` | summary before any period exists | `period_id=null`, income/expense over **all** movements |
| H-03 | Dashboard with a nonexistent `period_id` | `[NEW]` | `?period_id=99999` | `404` "period not found" |
| H-04 | `by-category` buckets uncategorized expenses | `[NEW]` | expense with no `category_id` | a row `{category_id:null, name:"Uncategorized"}` |
| H-05 | `receivables` excludes settled/advance patients | `[NEW]` | one case overpaid (advance), one owing | only the owing patient appears (`outstanding > 0`); advances net within a patient |
| H-06 | `per-partner.entitled` uses the **latest** window × **all-time** profit | `[PROBE]` | change shares mid-history, then read per-partner | `entitled` may diverge from the windowed settlement (it's a snapshot, not the windowed split) — confirm this is acceptable for the report |
| H-07 | `trends` month bucketing across a year boundary | `[NEW]` | movements in 2025-12 and 2026-01 | distinct `2025-12` / `2026-01` buckets, correct net each |
| H-08 | P&L / by-category / by-collector / per-partner happy path | `[COVERED]` *test_reports* | mixed income+expense | matches hand totals |

---

# I. Soft-delete & audit (ADR-0006)

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| I-01 | Voided movement disappears from `journal.csv` | `[NEW]` (verified) | void a payment, export | the voided row is **absent** |
| I-02 | Voided movement excluded from balances/reports/receivables | `[NEW]` | void, re-read dashboard & reports | totals drop accordingly (every read filters `deleted_at IS NULL`) |
| I-03 | Audit log records *all* write actions | `[NEW]` | exercise void/restore/edit/close/discount/write-off/revoke | each action string appears in `/audit-logs` (only `take_payment`+`setup`+`invite` are asserted today) |
| I-04 | Audit trail records writes | `[COVERED]` *test_audit_trail_records_writes* / *test_invite_is_audit_logged* | take payment / invite | `take_payment`, `setup`, `invite` logged |

---

# J. Exports

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| J-01 | Journal CSV / summary PDF / statement CSV | `[COVERED]` *test_exports* | export each | `200`, correct content-type, `%PDF` magic, headers present |
| J-02 | Period summary PDF for a period predating any window | `[NEW]` | period with a pre-window movement | `422` (build_settlement ValueError→422) |
| J-03 | Statement (CSV/PDF) for a nonexistent patient | `[NEW]` | `GET /exports/patients/99999/statement.csv` | `404` |
| J-04 | Statement totals match outstanding (incl. refund/adjustment) | `[NEW]` | case with payment + refund + discount | per-row `paid`/`outstanding` and the TOTAL line reconcile |

---

# K. Frontend offline queue & PWA (`web/src/api.ts`) — manual / JS

No JS test harness ships in the repo, so run these by hand in the browser
(DevTools → Network → Offline) or add a vitest suite. Only the two **quick-add**
flows (`takePayment`, `logExpense`) use the hold-and-retry queue.

| ID | Title | Tag | Steps | Expected |
|----|-------|-----|-------|----------|
| K-01 | Quick-add succeeds online | `[NEW]` | log a payment online | result returned, queue length unchanged |
| K-02 | Network drop holds the entry | `[NEW]` | go offline, log a payment | returns `{queued:true}`, `ccr:queue` event with depth+1, entry in `localStorage["ccr_offline_queue"]` |
| K-03 | A real 4xx is **not** queued | `[NEW]` | trigger a 422 (e.g. bad amount) while online | `ApiError` surfaces to the user; queue unchanged |
| K-04 | Flush on reconnect replays in order | `[NEW]` | queue 2 entries offline, go online (or wait 15s tick) | both POST in FIFO order, queue empties, `flushQueue` returns count |
| K-05 | Held entry rejected on replay is dropped | `[NEW]` | queue an entry that the server will 4xx (e.g. case later closed) | on flush it 4xxes → dropped (can never succeed), not retried forever |
| K-06 | Flush while still offline keeps entries | `[NEW]` | flush with no connectivity | loop breaks on the network error, entries retained |
| K-07 | Flush with no token is a no-op | `[NEW]` | clear token, flush | returns `0`, nothing sent |
| K-08 | Only payment & expense are held | `[PROBE]` | go offline, attempt a transfer/capital/drawing/refund | these call `request` directly → they **throw** and are **not** queued (deliberate quick-add-only scope; the entry is lost unless the user retries) |
| K-09 | 401 clears session | `[NEW]` | expired/invalid token mid-request | token cleared, `ccr:unauthorized` fired, error thrown |
| K-10 | Queue persists across reload | `[NEW]` | queue offline, reload the PWA | entries survive (localStorage); `startQueueRetry` resumes flushing |
| K-11 | **⚠ Double-submit on lost response** | ⚠`[GAP]` | server commits the payment, but the response is lost (drop *after* commit) | the client can't distinguish "never arrived" from "reply lost", so it re-queues and **replays → duplicate payment**. There's no idempotency key sent to the server (`crypto.randomUUID` is local-only). For a money app this can double-count income. **Recommend a client-generated idempotency key honored server-side.** |
| K-12 | PWA: service worker doesn't swallow `/api` | `[NEW]` | install PWA, go offline, navigate | app shell loads from SW; `/api` calls bypass the SW (`navigateFallbackDenylist: [/^\/api/]`) and fail/queue rather than returning a cached page |

---

# Coverage summary

| Area | Cases | New gaps | Already covered |
|------|-------|----------|-----------------|
| A. Authentication | A-01…10 | A-04…10 | A-01, A-02, A-03 |
| B. Authorization/scoping | B-01…06 | B-05, B-06 | B-01…04 |
| C. Validation | C-01…16 | C-01…08, C-10…12, C-15 | C-09, C-13, C-14, C-16 |
| D. Money-routing guardrails | D-01…06 | **all** (D-01…05 are ⚠ gaps) | — |
| E. Period close & locking | E-01…09 | E-01…04, E-07…09 | E-05, E-06 |
| F. Settlement payment | F-01…06 | F-02…06 | F-01 |
| G. Corrections | G-01…06 | G-03, G-05 | G-01, G-02, G-04, G-06 |
| H. Dashboard & reports | H-01…08 | H-01…07 | H-08 |
| I. Soft-delete & audit | I-01…04 | I-01, I-02, I-03 | I-04 |
| J. Exports | J-01…04 | J-02, J-03, J-04 | J-01 |
| K. Offline queue & PWA | K-01…12 | all (manual) | — |

## Findings worth acting on (HTTP/frontend layer)

1. **⚠ Money-routing guardrails (D-01…D-05).** The API accepts payments/expenses
   into *any* account and settlement payments between *arbitrary* accounts.
   Because settlement follows the account leg, D-03 shows the collector (Saad)
   ending up *owed* by Hassan despite collecting everything. Highest priority —
   add account-selection validation. (Pairs with money-math findings #1/#2.)
2. **⚠ Dashboard reconciliation (H-01).** Period-scoped `net_profit` vs.
   all-time `account_balances` won't add up; clarify/label the semantics.
3. **⚠ Overlapping periods (E-04).** Permitted today; `closed_period_covering`
   then picks one arbitrarily. Consider rejecting overlaps at create-time.
4. **⚠ Offline double-submit (K-11).** No idempotency key → a payment can post
   twice if the HTTP response is lost after the server commits. Add an
   idempotency key for the two quick-add flows.
5. **`/setup` returns 409 (not 403) for a non-allowlisted second user (B-05)** —
   minor, a consequence of the bootstrap path; confirm it's intended.
