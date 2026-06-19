"""Dashboard — the income/expense intelligence the product centers on.

Milestone 0 ships the headline numbers (this period's income, expense, net
profit) plus live account balances; richer breakdowns arrive in Milestone 4.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Account, MoneyMovement, Period, PeriodStatus
from app.money_math.types import MovementType
from app.services import account_balances_for_clinic, get_scoped

router = APIRouter(tags=["dashboard"])


def _pick_period(session: Session, clinic_id: int) -> Period | None:
    """Prefer the most recent open period; fall back to the most recent period."""
    open_period = session.scalar(
        select(Period)
        .where(
            Period.clinic_id == clinic_id,
            Period.deleted_at.is_(None),
            Period.status == PeriodStatus.OPEN,
        )
        .order_by(Period.start_date.desc())
    )
    if open_period is not None:
        return open_period
    return session.scalar(
        select(Period)
        .where(Period.clinic_id == clinic_id, Period.deleted_at.is_(None))
        .order_by(Period.start_date.desc())
    )


@router.get("/dashboard/summary", response_model=schemas.DashboardSummary)
def summary(
    period_id: int | None = None,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.DashboardSummary:
    if period_id is not None:
        period = get_scoped(session, Period, period_id, member.clinic_id)
        if period is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "period not found")
    else:
        period = _pick_period(session, member.clinic_id)

    stmt = select(MoneyMovement).where(
        MoneyMovement.clinic_id == member.clinic_id,
        MoneyMovement.deleted_at.is_(None),
    )
    if period is not None:
        stmt = stmt.where(
            MoneyMovement.date >= period.start_date,
            MoneyMovement.date <= period.end_date,
        )
    movements = session.scalars(stmt).all()

    income = sum(m.amount for m in movements if m.type is MovementType.INCOME)
    expense = sum(m.amount for m in movements if m.type is MovementType.EXPENSE)

    balances = account_balances_for_clinic(session, member.clinic_id)
    accounts = session.scalars(
        select(Account).where(
            Account.clinic_id == member.clinic_id, Account.deleted_at.is_(None)
        )
    ).all()

    return schemas.DashboardSummary(
        period_id=period.id if period is not None else None,
        income=income,
        expense=expense,
        net_profit=income - expense,
        account_balances=[
            schemas.AccountBalanceOut(
                account_id=a.id, name=a.name, balance=balances.get(a.id, a.opening_balance)
            )
            for a in accounts
        ],
    )
