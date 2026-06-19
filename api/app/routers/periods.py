"""Period close, settlement statements, and settlement payments.

Closing computes and locks a settlement statement but moves no cash (ADR-0003);
the real settlement payment is recorded separately as a Transfer.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import (
    Account,
    MoneyMovement,
    Period,
    PeriodStatus,
    SettlementBalance,
    SettlementObligation,
    SettlementStatement,
)
from app.money_math.types import MovementType
from app.services import build_settlement, closed_period_covering, get_scoped, record_audit

router = APIRouter(tags=["periods"])


def _statement_out(
    session: Session, statement: SettlementStatement
) -> schemas.SettlementStatementOut:
    balances = session.scalars(
        select(SettlementBalance).where(SettlementBalance.statement_id == statement.id)
    ).all()
    obligations = session.scalars(
        select(SettlementObligation).where(
            SettlementObligation.statement_id == statement.id
        )
    ).all()
    return schemas.SettlementStatementOut(
        id=statement.id,
        period_id=statement.period_id,
        profit=statement.profit,
        joint_standing=statement.joint_standing,
        balances=[
            schemas.SettlementBalanceOut(
                partner_id=b.partner_id,
                personal_profit=b.personal_profit,
                settlement_balance=b.settlement_balance,
            )
            for b in balances
        ],
        obligations=[
            schemas.SettlementObligationOut(
                id=o.id,
                from_partner_id=o.from_partner_id,
                to_partner_id=o.to_partner_id,
                amount=o.amount,
                paid=o.paid_movement_id is not None,
            )
            for o in obligations
        ],
    )


@router.get("/periods", response_model=list[schemas.PeriodOut])
def list_periods(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    periods = session.scalars(
        select(Period)
        .where(Period.clinic_id == member.clinic_id, Period.deleted_at.is_(None))
        .order_by(Period.start_date.desc())
    ).all()
    return [schemas.PeriodOut.model_validate(p) for p in periods]


@router.get("/settlements", response_model=list[schemas.SettlementStatementOut])
def list_settlements(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    statements = session.scalars(
        select(SettlementStatement)
        .where(
            SettlementStatement.clinic_id == member.clinic_id,
            SettlementStatement.deleted_at.is_(None),
        )
        .order_by(SettlementStatement.id.desc())
    ).all()
    return [_statement_out(session, s) for s in statements]


@router.post("/periods", response_model=schemas.PeriodOut, status_code=status.HTTP_201_CREATED)
def create_period(
    body: schemas.PeriodCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.PeriodOut:
    if body.end_date < body.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "end_date before start_date")
    period = Period(
        clinic_id=member.clinic_id,
        start_date=body.start_date,
        end_date=body.end_date,
        status=PeriodStatus.OPEN,
        created_by=member.user.id,
    )
    session.add(period)
    session.flush()
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="open_period",
        entity_type="period",
        entity_id=period.id,
    )
    session.commit()
    return schemas.PeriodOut.model_validate(period)


@router.post("/periods/{period_id}/close", response_model=schemas.SettlementStatementOut)
def close_period(
    period_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.SettlementStatementOut:
    period = get_scoped(session, Period, period_id, member.clinic_id)
    if period is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "period not found")
    if period.status is PeriodStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "period already closed")

    try:
        computed = build_settlement(session, member.clinic_id, period)
    except ValueError as exc:
        # e.g. an entry dated before any share window is effective.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    statement = SettlementStatement(
        clinic_id=member.clinic_id,
        period_id=period.id,
        profit=computed.profit,
        joint_standing=computed.joint_standing,
        created_by=member.user.id,
    )
    session.add(statement)
    session.flush()

    for partner_id, balance in computed.settlement_balance.items():
        session.add(
            SettlementBalance(
                statement_id=statement.id,
                partner_id=partner_id,
                personal_profit=computed.personal_profit.get(partner_id, 0),
                settlement_balance=balance,
            )
        )
    for transfer in computed.transfers:
        session.add(
            SettlementObligation(
                statement_id=statement.id,
                from_partner_id=transfer.from_partner_id,
                to_partner_id=transfer.to_partner_id,
                amount=transfer.amount,
            )
        )

    period.status = PeriodStatus.CLOSED
    period.closed_at = datetime.now(timezone.utc)
    period.closed_by = member.user.id
    period.updated_by = member.user.id
    session.flush()

    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="close_period",
        entity_type="period",
        entity_id=period.id,
        detail={"statement_id": statement.id, "profit": computed.profit},
    )
    session.commit()
    return _statement_out(session, statement)


@router.get("/settlements/{statement_id}", response_model=schemas.SettlementStatementOut)
def get_settlement(
    statement_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.SettlementStatementOut:
    statement = get_scoped(session, SettlementStatement, statement_id, member.clinic_id)
    if statement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settlement statement not found")
    return _statement_out(session, statement)


@router.post(
    "/settlements/{statement_id}/payments",
    response_model=schemas.MovementOut,
    status_code=status.HTTP_201_CREATED,
)
def record_settlement_payment(
    statement_id: int,
    body: schemas.SettlementPaymentRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    statement = get_scoped(session, SettlementStatement, statement_id, member.clinic_id)
    if statement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settlement statement not found")

    obligation = session.get(SettlementObligation, body.obligation_id)
    if obligation is None or obligation.statement_id != statement.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "obligation not found")
    if obligation.paid_movement_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "obligation already paid")

    from_account = get_scoped(session, Account, body.from_account_id, member.clinic_id)
    to_account = get_scoped(session, Account, body.to_account_id, member.clinic_id)
    if from_account is None or to_account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

    amount = obligation.amount  # a settlement payment settles the obligation in full
    when = body.date or date.today()

    # The settlement payment lands in the open period, dated when cash moves —
    # it must not be backdated into a locked period (ADR-0003).
    if closed_period_covering(session, member.clinic_id, when) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "that date falls in a closed period"
        )

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.TRANSFER,
        amount=amount,
        date=when,
        partner_id=obligation.from_partner_id,
        from_account_id=from_account.id,
        to_account_id=to_account.id,
        note=body.note,
        settlement_statement_id=statement.id,
        created_by=member.user.id,
    )
    session.add(movement)
    session.flush()

    obligation.paid_movement_id = movement.id
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="settlement_payment",
        entity_type="money_movement",
        entity_id=movement.id,
        detail={"statement_id": statement.id, "obligation_id": obligation.id},
    )
    session.commit()
    return schemas.MovementOut.model_validate(movement)
