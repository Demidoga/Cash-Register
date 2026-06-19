"""Daily money entry (Milestone 2) and the journal.

The income path ("Take a payment") is tuned hardest; expense is the mirror;
transfer/capital/drawing are the rarer types; a refund is recorded as a
negative-amount Income against the case so profit, the account balance, and the
case's outstanding all move correctly without inventing a new movement type.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Account, Case, Category, MoneyMovement, Partner
from app.money_math.types import MovementType
from app.routers.patients import _case_out
from app.services import closed_period_covering, get_scoped, record_audit

router = APIRouter(tags=["movements"])


def _guard_open(session: Session, clinic_id: int, when: date) -> None:
    if closed_period_covering(session, clinic_id, when) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "that date falls in a closed period")


def _require(session: Session, model, entity_id: int | None, clinic_id: int, label: str):
    if entity_id is None:
        return None
    obj = get_scoped(session, model, entity_id, clinic_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} not found")
    return obj


def _persist(session: Session, member: CurrentMember, movement: MoneyMovement, action: str):
    session.add(movement)
    session.flush()
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action=action,
        entity_type="money_movement",
        entity_id=movement.id,
        detail={"type": movement.type.value, "amount": movement.amount},
    )
    session.commit()


@router.post(
    "/payments", response_model=schemas.TakePaymentResponse, status_code=status.HTTP_201_CREATED
)
def take_payment(
    body: schemas.TakePaymentRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.TakePaymentResponse:
    when = body.date or date.today()
    _guard_open(session, member.clinic_id, when)
    case = _require(session, Case, body.case_id, member.clinic_id, "case")
    _require(session, Account, body.account_id, member.clinic_id, "account")
    _require(session, Partner, body.partner_id, member.clinic_id, "partner")

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.INCOME,
        amount=body.amount,
        date=when,
        partner_id=body.partner_id,
        to_account_id=body.account_id,
        case_id=body.case_id,
        note=body.note,
        created_by=member.user.id,
    )
    _persist(session, member, movement, "take_payment")
    return schemas.TakePaymentResponse(
        movement=schemas.MovementOut.model_validate(movement),
        case=_case_out(session, member.clinic_id, case),
    )


@router.post("/expenses", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
def log_expense(
    body: schemas.LogExpenseRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    when = body.date or date.today()
    _guard_open(session, member.clinic_id, when)
    _require(session, Account, body.account_id, member.clinic_id, "account")
    _require(session, Partner, body.partner_id, member.clinic_id, "partner")
    _require(session, Category, body.category_id, member.clinic_id, "category")
    _require(session, Case, body.case_id, member.clinic_id, "case")

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.EXPENSE,
        amount=body.amount,
        date=when,
        partner_id=body.partner_id,
        from_account_id=body.account_id,
        category_id=body.category_id,
        case_id=body.case_id,
        note=body.note,
        created_by=member.user.id,
    )
    _persist(session, member, movement, "log_expense")
    return schemas.MovementOut.model_validate(movement)


@router.post("/transfers", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
def record_transfer(
    body: schemas.TransferRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    when = body.date or date.today()
    _guard_open(session, member.clinic_id, when)
    if body.from_account_id == body.to_account_id:
        raise HTTPException(422, "transfer needs two different accounts")
    _require(session, Account, body.from_account_id, member.clinic_id, "account")
    _require(session, Account, body.to_account_id, member.clinic_id, "account")
    _require(session, Partner, body.partner_id, member.clinic_id, "partner")

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.TRANSFER,
        amount=body.amount,
        date=when,
        partner_id=body.partner_id,
        from_account_id=body.from_account_id,
        to_account_id=body.to_account_id,
        note=body.note,
        created_by=member.user.id,
    )
    _persist(session, member, movement, "transfer")
    return schemas.MovementOut.model_validate(movement)


@router.post("/capital", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
def record_capital(
    body: schemas.CapitalRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    when = body.date or date.today()
    _guard_open(session, member.clinic_id, when)
    _require(session, Account, body.account_id, member.clinic_id, "account")
    _require(session, Partner, body.partner_id, member.clinic_id, "partner")

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.CAPITAL,
        amount=body.amount,
        date=when,
        partner_id=body.partner_id,
        to_account_id=body.account_id,
        note=body.note,
        created_by=member.user.id,
    )
    _persist(session, member, movement, "capital")
    return schemas.MovementOut.model_validate(movement)


@router.post("/drawings", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
def record_drawing(
    body: schemas.DrawingRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    when = body.date or date.today()
    _guard_open(session, member.clinic_id, when)
    _require(session, Account, body.account_id, member.clinic_id, "account")
    _require(session, Partner, body.partner_id, member.clinic_id, "partner")

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.DRAWING,
        amount=body.amount,
        date=when,
        partner_id=body.partner_id,
        from_account_id=body.account_id,
        note=body.note,
        created_by=member.user.id,
    )
    _persist(session, member, movement, "drawing")
    return schemas.MovementOut.model_validate(movement)


@router.post("/refunds", response_model=schemas.MovementOut, status_code=status.HTTP_201_CREATED)
def record_refund(
    body: schemas.RefundRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    when = body.date or date.today()
    _guard_open(session, member.clinic_id, when)
    _require(session, Case, body.case_id, member.clinic_id, "case")
    _require(session, Account, body.account_id, member.clinic_id, "account")
    _require(session, Partner, body.partner_id, member.clinic_id, "partner")

    # Negative Income on the to-leg: balance ↓, profit ↓, outstanding ↑ — all
    # the correct directions, with no new movement type (ADR-0007).
    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.INCOME,
        amount=-body.amount,
        date=when,
        partner_id=body.partner_id,
        to_account_id=body.account_id,
        case_id=body.case_id,
        note=body.note or "refund",
        created_by=member.user.id,
    )
    _persist(session, member, movement, "refund")
    return schemas.MovementOut.model_validate(movement)


@router.get("/movements", response_model=list[schemas.MovementOut])
def list_movements(
    type: MovementType | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=500, le=2000),
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    stmt = select(MoneyMovement).where(
        MoneyMovement.clinic_id == member.clinic_id, MoneyMovement.deleted_at.is_(None)
    )
    if type is not None:
        stmt = stmt.where(MoneyMovement.type == type)
    if start is not None:
        stmt = stmt.where(MoneyMovement.date >= start)
    if end is not None:
        stmt = stmt.where(MoneyMovement.date <= end)
    stmt = stmt.order_by(MoneyMovement.date.desc(), MoneyMovement.id.desc()).limit(limit)
    return [schemas.MovementOut.model_validate(m) for m in session.scalars(stmt)]
