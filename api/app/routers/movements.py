"""Daily money entry — the "Take a payment" quick-add (PRD stories 19, 22, 31).

Income is a payment against a treatment case, attributed to the collecting
partner, landing in a destination account.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Account, Case, MoneyMovement, Partner
from app.money_math.types import MovementType
from app.routers.patients import _case_out
from app.services import closed_period_covering, get_scoped, record_audit

router = APIRouter(tags=["movements"])


@router.post(
    "/payments", response_model=schemas.TakePaymentResponse, status_code=status.HTTP_201_CREATED
)
def take_payment(
    body: schemas.TakePaymentRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.TakePaymentResponse:
    when = body.date or date.today()

    # A closed period is locked — its entries cannot be added to (story 54).
    if closed_period_covering(session, member.clinic_id, when) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "that date falls in a closed period"
        )

    case = get_scoped(session, Case, body.case_id, member.clinic_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    account = get_scoped(session, Account, body.account_id, member.clinic_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    partner = get_scoped(session, Partner, body.partner_id, member.clinic_id)
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "partner not found")

    movement = MoneyMovement(
        clinic_id=member.clinic_id,
        type=MovementType.INCOME,
        amount=body.amount,
        date=when,
        partner_id=partner.id,
        to_account_id=account.id,
        case_id=case.id,
        note=body.note,
        created_by=member.user.id,
    )
    session.add(movement)
    session.flush()
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="take_payment",
        entity_type="money_movement",
        entity_id=movement.id,
        detail={"case_id": case.id, "amount": body.amount},
    )
    session.commit()

    return schemas.TakePaymentResponse(
        movement=schemas.MovementOut.model_validate(movement),
        case=_case_out(session, member.clinic_id, case),
    )
