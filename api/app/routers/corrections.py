"""Corrections & integrity (Milestone 6): edit-while-open, void/restore,
case discounts and write-offs, and the audit trail.

Open periods can be edited (audit-logged); closed periods are locked — a
correction to a closed period is a forward entry in the open period, never a
silent edit of locked history (ADR-0003).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import AdjustmentType, AuditLog, Case, CaseAdjustment, Category, MoneyMovement
from app.routers.patients import _case_out
from app.services import (
    case_outstanding_value,
    closed_period_covering,
    get_scoped,
    record_audit,
    soft_delete,
)

router = APIRouter(tags=["corrections"])


def _assert_open(session: Session, clinic_id: int, on) -> None:
    if closed_period_covering(session, clinic_id, on) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "that entry is in a closed period; correct it with a forward entry",
        )


@router.patch("/movements/{movement_id}", response_model=schemas.MovementOut)
def edit_movement(
    movement_id: int,
    body: schemas.MovementUpdate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    movement = get_scoped(session, MoneyMovement, movement_id, member.clinic_id)
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "movement not found")
    _assert_open(session, member.clinic_id, movement.date)

    if body.amount is not None:
        movement.amount = body.amount
    if body.note is not None:
        movement.note = body.note
    if body.category_id is not None:
        if get_scoped(session, Category, body.category_id, member.clinic_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
        movement.category_id = body.category_id
    if body.date is not None:
        _assert_open(session, member.clinic_id, body.date)  # can't move it into a closed period
        movement.date = body.date

    movement.updated_by = member.user.id
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="edit",
        entity_type="money_movement",
        entity_id=movement.id,
    )
    session.commit()
    return schemas.MovementOut.model_validate(movement)


@router.delete("/movements/{movement_id}", status_code=status.HTTP_204_NO_CONTENT)
def void_movement(
    movement_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    movement = get_scoped(session, MoneyMovement, movement_id, member.clinic_id)
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "movement not found")
    _assert_open(session, member.clinic_id, movement.date)
    soft_delete(movement, member.user.id)
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="void",
        entity_type="money_movement",
        entity_id=movement.id,
    )
    session.commit()


@router.post("/movements/{movement_id}/restore", response_model=schemas.MovementOut)
def restore_movement(
    movement_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.MovementOut:
    movement = session.get(MoneyMovement, movement_id)
    if movement is None or movement.clinic_id != member.clinic_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "movement not found")
    if movement.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "movement is not voided")
    _assert_open(session, member.clinic_id, movement.date)
    movement.deleted_at = None
    movement.updated_by = member.user.id
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="restore",
        entity_type="money_movement",
        entity_id=movement.id,
    )
    session.commit()
    return schemas.MovementOut.model_validate(movement)


def _adjust(session, member, case_id, adj_type, amount, note):
    case = get_scoped(session, Case, case_id, member.clinic_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    if amount is None:
        if adj_type is AdjustmentType.WRITE_OFF:
            amount = max(case_outstanding_value(session, member.clinic_id, case), 0)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "amount is required")
    adjustment = CaseAdjustment(
        clinic_id=member.clinic_id,
        case_id=case.id,
        type=adj_type,
        amount=amount,
        note=note,
        created_by=member.user.id,
    )
    session.add(adjustment)
    session.flush()
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action=adj_type.value,
        entity_type="case_adjustment",
        entity_id=adjustment.id,
        detail={"case_id": case.id, "amount": amount},
    )
    session.commit()
    return _case_out(session, member.clinic_id, case)


@router.post("/cases/{case_id}/discount", response_model=schemas.CaseOut, status_code=201)
def apply_discount(
    case_id: int,
    body: schemas.AdjustmentRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.CaseOut:
    return _adjust(session, member, case_id, AdjustmentType.DISCOUNT, body.amount, body.note)


@router.post("/cases/{case_id}/write-off", response_model=schemas.CaseOut, status_code=201)
def write_off(
    case_id: int,
    body: schemas.AdjustmentRequest,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.CaseOut:
    return _adjust(session, member, case_id, AdjustmentType.WRITE_OFF, body.amount, body.note)


@router.get("/audit-logs", response_model=list[schemas.AuditLogOut])
def list_audit_logs(
    limit: int = 200,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    rows = session.scalars(
        select(AuditLog)
        .where(AuditLog.clinic_id == member.clinic_id)
        .order_by(AuditLog.id.desc())
        .limit(min(limit, 1000))
    ).all()
    return [schemas.AuditLogOut.model_validate(r) for r in rows]
