"""Pure money-math: profit, account balances, case outstanding, settlement.

No I/O, no framework imports — exhaustively unit-tested in isolation. The
settlement algorithm is the project's crown jewel (replaces the Excel's fragile
``M/N`` block); see ``context.md`` and ADR-0002 / ADR-0004.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from fractions import Fraction

from app.money_math.types import (
    Account,
    AccountKind,
    Movement,
    MovementType,
    SettlementStatement,
    SettlementTransfer,
    ShareWindow,
)


def profit(movements: Iterable[Movement]) -> int:
    """Period profit = Σ Income − Σ Expense. Other types never affect it."""
    total = 0
    for m in movements:
        if m.type is MovementType.INCOME:
            total += m.amount
        elif m.type is MovementType.EXPENSE:
            total -= m.amount
    return total


def account_balances(
    movements: Iterable[Movement],
    opening_balances: Mapping[int, int] | None = None,
) -> dict[int, int]:
    """Each account's balance = opening balance + Σ of its legs (ADR-0007)."""
    balances: dict[int, int] = dict(opening_balances or {})
    for m in movements:
        if m.to_account_id is not None:
            balances[m.to_account_id] = balances.get(m.to_account_id, 0) + m.amount
        if m.from_account_id is not None:
            balances[m.from_account_id] = balances.get(m.from_account_id, 0) - m.amount
    return balances


def case_outstanding(
    agreed_price: int,
    payments: Iterable[int] = (),
    adjustments: Iterable[int] = (),
) -> int:
    """Outstanding = agreed price − payments − adjustments.

    Negative ⇒ advance/credit (over-payment). ``adjustments`` are discounts and
    write-offs, which reduce what is owed but are **not** income.
    """
    return agreed_price - sum(payments) - sum(adjustments)


def settlement(
    movements: Iterable[Movement],
    share_windows: Iterable[ShareWindow],
    accounts: Iterable[Account],
) -> SettlementStatement:
    """Compute the settlement statement for a period's movements.

    Splits the period at effective-dated share-change boundaries (ADR-0004):
    each Income/Expense is attributed to the share window its date falls in,
    each window is settled by the shares effective in that window, and the
    per-window settlement balances are summed. Joint flows stay standing
    (ADR-0002); Capital/Drawing/Transfer are invisible to settlement.
    """
    account_by_id = {a.id: a for a in accounts}
    windows = sorted(share_windows, key=lambda w: w.effective_from)
    if not windows:
        raise ValueError("settlement requires at least one share window")

    partner_ids = sorted({pid for w in windows for pid in w.shares})

    def window_for(d) -> ShareWindow:
        chosen: ShareWindow | None = None
        for w in windows:
            if w.effective_from <= d:
                chosen = w
            else:
                break
        if chosen is None:
            raise ValueError(f"no share window effective on {d}")
        return chosen

    # Per-window personal profit, keyed by window identity.
    window_personal: dict[int, dict[int, int]] = {
        id(w): {pid: 0 for pid in partner_ids} for w in windows
    }
    personal_profit_total: dict[int, int] = {pid: 0 for pid in partner_ids}
    joint_standing = 0
    total_profit = 0

    for m in movements:
        if m.type is MovementType.INCOME:
            sign, account_id = 1, m.to_account_id
        elif m.type is MovementType.EXPENSE:
            sign, account_id = -1, m.from_account_id
        else:
            continue  # Capital/Drawing/Transfer: invisible to profit & settlement

        total_profit += sign * m.amount

        account = account_by_id.get(account_id) if account_id is not None else None
        if account is None:
            raise ValueError(
                f"{m.type.value} movement on {m.date} has no account leg to settle against"
            )

        if account.kind is AccountKind.JOINT:
            joint_standing += sign * m.amount
            continue

        owner = account.owner_partner_id
        if owner is None:
            raise ValueError(f"personal account {account.id} has no owner partner")
        window = window_for(m.date)
        window_personal[id(window)][owner] = (
            window_personal[id(window)].get(owner, 0) + sign * m.amount
        )
        personal_profit_total[owner] = personal_profit_total.get(owner, 0) + sign * m.amount

    # Settle each window by its own shares, then sum (ADR-0004).
    balances: dict[int, Fraction] = {pid: Fraction(0) for pid in partner_ids}
    for w in windows:
        wp = window_personal[id(w)]
        pool = sum(wp.values())
        for pid in partner_ids:
            share = w.shares.get(pid, Fraction(0))
            balances[pid] += Fraction(wp.get(pid, 0)) - share * pool

    rounded = _round_preserving_zero_sum(balances, partner_ids)
    transfers = _minimal_transfers(rounded)

    return SettlementStatement(
        profit=total_profit,
        joint_standing=joint_standing,
        personal_profit={pid: personal_profit_total.get(pid, 0) for pid in partner_ids},
        settlement_balance=rounded,
        transfers=transfers,
    )


def _round_preserving_zero_sum(
    values: Mapping[int, Fraction], ids: list[int]
) -> dict[int, int]:
    """Round Fraction balances (which sum to exactly 0) to integers that still
    sum to 0, using the largest-remainder method."""
    floors = {k: math.floor(values[k]) for k in ids}
    deficit = -sum(floors.values())  # how many +1s to hand back; an exact integer
    # Hand the +1s to the largest fractional remainders first.
    by_remainder = sorted(ids, key=lambda k: values[k] - floors[k], reverse=True)
    result = dict(floors)
    for k in by_remainder[:deficit]:
        result[k] += 1
    return result


def _minimal_transfers(balances: Mapping[int, int]) -> list[SettlementTransfer]:
    """Greedy minimal settlement: debtors (>0) pay creditors (<0). For the small
    partner counts here this yields the natural minimal set of payments."""
    debtors = sorted(
        ([pid, bal] for pid, bal in balances.items() if bal > 0),
        key=lambda x: (-x[1], x[0]),
    )
    creditors = sorted(
        ([pid, -bal] for pid, bal in balances.items() if bal < 0),
        key=lambda x: (-x[1], x[0]),
    )
    transfers: list[SettlementTransfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        payer, owed = debtors[i], creditors[j]
        amount = min(payer[1], owed[1])
        transfers.append(
            SettlementTransfer(
                from_partner_id=payer[0], to_partner_id=owed[0], amount=amount
            )
        )
        payer[1] -= amount
        owed[1] -= amount
        if payer[1] == 0:
            i += 1
        if owed[1] == 0:
            j += 1
    return transfers
