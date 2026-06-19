"""Domain services: the bridge between the SQLAlchemy models and the pure
money-math seam, plus audit-stamping and period-locking helpers.

Keeping the arithmetic in ``money_math`` (pure) and the persistence here means
the crown-jewel settlement logic is provable in isolation (ADR-0001).
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import money_math
from app.models import (
    Account,
    AuditLog,
    Case,
    MoneyMovement,
    PartnerShare,
    Period,
    PeriodStatus,
    ShareWindow,
)
from app.money_math.types import MovementType


def get_scoped(session: Session, model, entity_id: int, clinic_id: int):
    """Fetch a row by id only if it belongs to ``clinic_id`` and is alive.

    The clinic check is the tenant-scoping path (ADR-0005): even with one clinic,
    every read goes through it so multi-clinic is a migration, not a rewrite.
    """
    obj = session.get(model, entity_id)
    if obj is None or obj.clinic_id != clinic_id or obj.deleted_at is not None:
        return None
    return obj


def record_audit(
    session: Session,
    *,
    clinic_id: int,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """Stamp who/what/when for a write (ADR-0006). Complete from the first entry."""
    session.add(
        AuditLog(
            clinic_id=clinic_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )


def _clinic_movements(session: Session, clinic_id: int) -> list[MoneyMovement]:
    return list(
        session.scalars(
            select(MoneyMovement).where(
                MoneyMovement.clinic_id == clinic_id,
                MoneyMovement.deleted_at.is_(None),
            )
        )
    )


def case_outstanding_value(session: Session, clinic_id: int, case: Case) -> int:
    """Outstanding = agreed price − payments (negative ⇒ advance/credit)."""
    payments = session.scalars(
        select(MoneyMovement.amount).where(
            MoneyMovement.clinic_id == clinic_id,
            MoneyMovement.case_id == case.id,
            MoneyMovement.type == MovementType.INCOME,
            MoneyMovement.deleted_at.is_(None),
        )
    ).all()
    # Case-level adjustments (discount/write-off) arrive in Milestone 6.
    return money_math.case_outstanding(case.agreed_price, payments=payments)


def account_balances_for_clinic(session: Session, clinic_id: int) -> dict[int, int]:
    accounts = session.scalars(
        select(Account).where(
            Account.clinic_id == clinic_id, Account.deleted_at.is_(None)
        )
    ).all()
    opening = {a.id: a.opening_balance for a in accounts}
    movements = [
        money_math.Movement(
            type=m.type,
            amount=m.amount,
            date=m.date,
            from_account_id=m.from_account_id,
            to_account_id=m.to_account_id,
        )
        for m in _clinic_movements(session, clinic_id)
    ]
    return money_math.account_balances(movements, opening)


def _share_windows(session: Session, clinic_id: int) -> list[money_math.ShareWindow]:
    windows = session.scalars(
        select(ShareWindow).where(
            ShareWindow.clinic_id == clinic_id, ShareWindow.deleted_at.is_(None)
        )
    ).all()
    result: list[money_math.ShareWindow] = []
    for w in windows:
        shares = session.scalars(
            select(PartnerShare).where(PartnerShare.share_window_id == w.id)
        ).all()
        result.append(
            money_math.ShareWindow(
                effective_from=w.effective_from,
                shares={ps.partner_id: Fraction(ps.share_num, ps.share_den) for ps in shares},
            )
        )
    return result


def build_settlement(
    session: Session, clinic_id: int, period: Period
) -> money_math.SettlementStatement:
    """Compute the settlement statement for a period from its movements."""
    accounts = session.scalars(
        select(Account).where(
            Account.clinic_id == clinic_id, Account.deleted_at.is_(None)
        )
    ).all()
    mm_accounts = [
        money_math.Account(id=a.id, kind=a.kind, owner_partner_id=a.owner_partner_id)
        for a in accounts
    ]
    movements = session.scalars(
        select(MoneyMovement).where(
            MoneyMovement.clinic_id == clinic_id,
            MoneyMovement.deleted_at.is_(None),
            MoneyMovement.date >= period.start_date,
            MoneyMovement.date <= period.end_date,
        )
    ).all()
    mm_movements = [
        money_math.Movement(
            type=m.type,
            amount=m.amount,
            date=m.date,
            partner_id=m.partner_id,
            from_account_id=m.from_account_id,
            to_account_id=m.to_account_id,
        )
        for m in movements
    ]
    return money_math.settlement(mm_movements, _share_windows(session, clinic_id), mm_accounts)


def closed_period_covering(
    session: Session, clinic_id: int, on: date
) -> Period | None:
    """A closed period whose span covers ``on`` — used to lock edits (story 54)."""
    return session.scalar(
        select(Period).where(
            Period.clinic_id == clinic_id,
            Period.deleted_at.is_(None),
            Period.status == PeriodStatus.CLOSED,
            Period.start_date <= on,
            Period.end_date >= on,
        )
    )
