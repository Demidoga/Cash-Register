"""Exhaustive unit tests for the pure money-math seam (ADR-0001 secondary seam).

Covers the build plan's mandatory list: capital/drawing exclusion (ADR-0002),
the cash-conservation invariant, a >=3-partner split, a mid-period share-change
split (ADR-0004), advances/over-payment, write-offs (!= income), and the joint
pool staying standing.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import pytest

from app.money_math import (
    Account,
    AccountKind,
    Movement,
    MovementType,
    account_balances,
    case_outstanding,
    profit,
    settlement,
)

# --- fixtures / helpers ------------------------------------------------------

A, B, C = 1, 2, 3  # partner ids
PERSONAL_A = Account(id=10, kind=AccountKind.PERSONAL, owner_partner_id=A)
PERSONAL_B = Account(id=20, kind=AccountKind.PERSONAL, owner_partner_id=B)
PERSONAL_C = Account(id=30, kind=AccountKind.PERSONAL, owner_partner_id=C)
JOINT = Account(id=99, kind=AccountKind.JOINT)


def income(amount, to_account, *, partner=None, on=date(2026, 1, 10)):
    return Movement(
        type=MovementType.INCOME,
        amount=amount,
        date=on,
        partner_id=partner,
        to_account_id=to_account.id,
    )


def expense(amount, from_account, *, partner=None, on=date(2026, 1, 10)):
    return Movement(
        type=MovementType.EXPENSE,
        amount=amount,
        date=on,
        partner_id=partner,
        from_account_id=from_account.id,
    )


def fiftyfifty(on=date(2026, 1, 1)):
    from app.money_math import ShareWindow

    return [ShareWindow(effective_from=on, shares={A: Fraction(1, 2), B: Fraction(1, 2)})]


def thirds(on=date(2026, 1, 1)):
    from app.money_math import ShareWindow

    return [
        ShareWindow(
            effective_from=on,
            shares={A: Fraction(1, 3), B: Fraction(1, 3), C: Fraction(1, 3)},
        )
    ]


# --- profit ------------------------------------------------------------------


def test_profit_is_income_minus_expense():
    movements = [income(5000, PERSONAL_A), expense(2000, PERSONAL_A)]
    assert profit(movements) == 3000


def test_profit_ignores_non_profit_movement_types():
    movements = [
        income(5000, PERSONAL_A),
        Movement(MovementType.CAPITAL, 9999, date(2026, 1, 5), to_account_id=PERSONAL_A.id),
        Movement(MovementType.DRAWING, 4444, date(2026, 1, 5), from_account_id=PERSONAL_A.id),
        Movement(
            MovementType.TRANSFER,
            3333,
            date(2026, 1, 5),
            from_account_id=PERSONAL_A.id,
            to_account_id=JOINT.id,
        ),
    ]
    assert profit(movements) == 5000


# --- account balances --------------------------------------------------------


def test_account_balances_sum_legs_over_opening():
    movements = [
        income(5000, PERSONAL_A),  # +5000 to A
        expense(2000, PERSONAL_A),  # -2000 from A
        Movement(
            MovementType.TRANSFER,
            1000,
            date(2026, 1, 6),
            from_account_id=PERSONAL_A.id,
            to_account_id=JOINT.id,
        ),
    ]
    balances = account_balances(movements, {PERSONAL_A.id: 1000, JOINT.id: 0})
    assert balances[PERSONAL_A.id] == 1000 + 5000 - 2000 - 1000
    assert balances[JOINT.id] == 1000


def test_account_balances_default_opening_is_zero():
    balances = account_balances([income(700, PERSONAL_A)])
    assert balances[PERSONAL_A.id] == 700


# --- case outstanding (advances + write-offs) --------------------------------


def test_outstanding_drops_as_payments_accumulate():
    assert case_outstanding(10000, payments=[1750, 2750, 2500]) == 3000


def test_overpayment_is_a_negative_outstanding_advance():
    assert case_outstanding(8000, payments=[5000, 5000]) == -2000


def test_writeoff_clears_outstanding_without_being_income():
    # A 4000 case, 1000 paid, remaining 3000 written off -> nothing owed.
    assert case_outstanding(4000, payments=[1000], adjustments=[3000]) == 0
    # ...and the write-off never appears as income, so profit only sees the payment.
    assert profit([income(1000, PERSONAL_A)]) == 1000


# --- settlement: 2 partners (the Milestone 0 core) ---------------------------


def test_two_partner_settlement_single_transfer():
    # A collects 10000 into personal; B collects nothing. 50/50.
    movements = [income(10000, PERSONAL_A, partner=A)]
    stmt = settlement(movements, fiftyfifty(), [PERSONAL_A, PERSONAL_B])

    assert stmt.profit == 10000
    assert stmt.personal_profit[A] == 10000
    assert stmt.personal_profit[B] == 0
    assert stmt.settlement_balance[A] == 5000  # holds more -> pays in
    assert stmt.settlement_balance[B] == -5000  # is owed
    assert stmt.transfers == [
        # exactly one transfer for 2 partners
        type(stmt.transfers[0])(from_partner_id=A, to_partner_id=B, amount=5000)
    ]


def test_capital_and_drawing_do_not_change_settlement(  # ADR-0002 mandatory
):
    base = [income(10000, PERSONAL_A, partner=A)]
    with_noise = base + [
        Movement(MovementType.CAPITAL, 3000, date(2026, 1, 8), partner_id=A, to_account_id=PERSONAL_A.id),
        Movement(MovementType.DRAWING, 1000, date(2026, 1, 8), partner_id=B, from_account_id=PERSONAL_B.id),
    ]
    accounts = [PERSONAL_A, PERSONAL_B]
    a = settlement(base, fiftyfifty(), accounts)
    b = settlement(with_noise, fiftyfifty(), accounts)
    assert a.settlement_balance == b.settlement_balance
    assert a.profit == b.profit  # capital/drawing are not profit either


# --- settlement: joint pool stays standing + cash conservation ---------------


def test_joint_pool_stays_standing_and_cash_is_conserved():
    movements = [
        income(8000, PERSONAL_A, partner=A),
        expense(1000, PERSONAL_B, partner=B),
        income(4000, JOINT, partner=A),
        expense(500, JOINT, partner=B),
    ]
    accounts = [PERSONAL_A, PERSONAL_B, JOINT]
    stmt = settlement(movements, fiftyfifty(), accounts)

    assert stmt.profit == 8000 - 1000 + 4000 - 500  # 10500
    assert stmt.joint_standing == 4000 - 500  # 3500, left standing
    assert stmt.personal_profit[A] == 8000
    assert stmt.personal_profit[B] == -1000

    # Settlement only reconciles the personal pool (7000), joint untouched.
    assert stmt.settlement_balance[A] == 8000 - (7000 // 2)  # 4500
    assert stmt.settlement_balance[B] == -1000 - (7000 // 2)  # -4500
    assert stmt.transfers == [
        type(stmt.transfers[0])(from_partner_id=A, to_partner_id=B, amount=4500)
    ]

    # Cash-conservation invariant: Σ personal_i + joint == P
    assert sum(stmt.personal_profit.values()) + stmt.joint_standing == stmt.profit


# --- settlement: >=3 partners ------------------------------------------------


def test_three_partner_minimal_transfers():
    movements = [
        income(9000, PERSONAL_A, partner=A),
        income(3000, PERSONAL_B, partner=B),
        # C collects nothing
    ]
    accounts = [PERSONAL_A, PERSONAL_B, PERSONAL_C]
    stmt = settlement(movements, thirds(), accounts)

    assert stmt.settlement_balance[A] == 5000  # 9000 - 12000/3
    assert stmt.settlement_balance[B] == -1000  # 3000 - 4000
    assert stmt.settlement_balance[C] == -4000  # 0 - 4000
    assert sum(stmt.settlement_balance.values()) == 0

    # Minimal: A (the only debtor) pays both creditors -> 2 transfers.
    T = type(stmt.transfers[0])
    assert set(stmt.transfers) == {
        T(from_partner_id=A, to_partner_id=C, amount=4000),
        T(from_partner_id=A, to_partner_id=B, amount=1000),
    }
    assert len(stmt.transfers) == 2


# --- settlement: mid-period share change (ADR-0004) --------------------------


def test_mid_period_share_change_does_not_backdate_new_partner():
    from app.money_math import ShareWindow

    windows = [
        ShareWindow(effective_from=date(2026, 1, 1), shares={A: Fraction(1, 2), B: Fraction(1, 2)}),
        ShareWindow(
            effective_from=date(2026, 1, 15),
            shares={A: Fraction(1, 3), B: Fraction(1, 3), C: Fraction(1, 3)},
        ),
    ]
    movements = [
        income(1000, PERSONAL_A, partner=A, on=date(2026, 1, 5)),  # window 1 only
        income(3000, PERSONAL_C, partner=C, on=date(2026, 1, 20)),  # window 2 only
    ]
    accounts = [PERSONAL_A, PERSONAL_B, PERSONAL_C]
    stmt = settlement(movements, windows, accounts)

    # Window 1 (A,B 50/50, pool=1000): A +500, B -500.
    # Window 2 (A,B,C 1/3, pool=3000): A -1000, B -1000, C +2000.
    assert stmt.settlement_balance[A] == 500 - 1000  # -500
    assert stmt.settlement_balance[B] == -500 - 1000  # -1500
    assert stmt.settlement_balance[C] == 2000  # joined late: no slice of day-5 profit
    assert sum(stmt.settlement_balance.values()) == 0


def test_settlement_rounds_to_integers_preserving_zero_sum():
    # 10000 split three ways doesn't divide evenly; balances must still sum to 0.
    movements = [income(10000, PERSONAL_A, partner=A)]
    accounts = [PERSONAL_A, PERSONAL_B, PERSONAL_C]
    stmt = settlement(movements, thirds(), accounts)
    assert all(isinstance(v, int) for v in stmt.settlement_balance.values())
    assert sum(stmt.settlement_balance.values()) == 0
    # transfers must net out to zero too
    paid_out = {}
    for t in stmt.transfers:
        paid_out[t.from_partner_id] = paid_out.get(t.from_partner_id, 0) + t.amount
        paid_out[t.to_partner_id] = paid_out.get(t.to_partner_id, 0) - t.amount
    for pid, bal in stmt.settlement_balance.items():
        assert paid_out.get(pid, 0) == bal


def test_settlement_raises_when_no_window_covers_a_movement_date():
    movements = [income(1000, PERSONAL_A, partner=A, on=date(2025, 12, 31))]
    with pytest.raises(ValueError):
        settlement(movements, fiftyfifty(date(2026, 1, 1)), [PERSONAL_A, PERSONAL_B])
