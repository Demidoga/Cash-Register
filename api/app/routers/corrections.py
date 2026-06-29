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
from app.models import (
    Account,
    AdjustmentType,
    AuditLog,
    Case,
    CaseAdjustment,
    Category,
    MoneyMovement,
    Partner,
)
from app.routers.patients import _case_out
from app.services import (
    case_outstanding_value,
    closed_period_covering,
    discount_for_movement,
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

    # Record what actually changed (old → new) so the audit trail explains the
    # correction, not just that one happened. A no-op edit leaves no trace.
    changes: dict[str, dict] = {}
    if body.amount is not None and body.amount != movement.amount:
        changes["amount"] = {"from": movement.amount, "to": body.amount}
        movement.amount = body.amount
    if body.note is not None and body.note != movement.note:
        changes["note"] = {"from": movement.note, "to": body.note}
        movement.note = body.note
    if "category_id" in body.model_fields_set and body.category_id != movement.category_id:
        if body.category_id is not None:
            if get_scoped(session, Category, body.category_id, member.clinic_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
        changes["category_id"] = {"from": movement.category_id, "to": body.category_id}
        movement.category_id = body.category_id
    # Re-pointable references: who collected/paid, which case, and the account
    # legs. Each is validated against the member's clinic; a field sent with an
    # explicit null is a deliberate clear (e.g. unlinking an expense from a case).
    if "partner_id" in body.model_fields_set and body.partner_id != movement.partner_id:
        if body.partner_id is not None:
            if get_scoped(session, Partner, body.partner_id, member.clinic_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "partner not found")
        changes["partner_id"] = {"from": movement.partner_id, "to": body.partner_id}
        movement.partner_id = body.partner_id
    if "case_id" in body.model_fields_set and body.case_id != movement.case_id:
        if body.case_id is not None:
            if get_scoped(session, Case, body.case_id, member.clinic_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
        changes["case_id"] = {"from": movement.case_id, "to": body.case_id}
        movement.case_id = body.case_id
    if "from_account_id" in body.model_fields_set and body.from_account_id != movement.from_account_id:
        if body.from_account_id is not None:
            if get_scoped(session, Account, body.from_account_id, member.clinic_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
        changes["from_account_id"] = {"from": movement.from_account_id, "to": body.from_account_id}
        movement.from_account_id = body.from_account_id
    if "to_account_id" in body.model_fields_set and body.to_account_id != movement.to_account_id:
        if body.to_account_id is not None:
            if get_scoped(session, Account, body.to_account_id, member.clinic_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
        changes["to_account_id"] = {"from": movement.to_account_id, "to": body.to_account_id}
        movement.to_account_id = body.to_account_id
    if body.date is not None and body.date != movement.date:
        _assert_open(session, member.clinic_id, body.date)  # can't move it into a closed period
        changes["date"] = {"from": movement.date.isoformat(), "to": body.date.isoformat()}
        movement.date = body.date

    # The discount that rode along with this payment is a separate adjustment
    # linked back to it (movement_id). Editing rewrites *that* discount to the
    # given absolute amount rather than stacking a new one: 0 removes it, and a
    # re-pointed case carries it along. Runs after case_id so it lands on the
    # final case.
    if "discount" in body.model_fields_set:
        if movement.case_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a discount needs a case")
        target = body.discount or 0
        if target < 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "discount cannot be negative")
        existing = session.scalar(
            select(CaseAdjustment).where(
                CaseAdjustment.movement_id == movement.id,
                CaseAdjustment.type == AdjustmentType.DISCOUNT,
                CaseAdjustment.deleted_at.is_(None),
            )
        )
        old = existing.amount if existing is not None else 0
        if existing is not None and target == 0:
            soft_delete(existing, member.user.id)
            changes["discount"] = {"from": old, "to": 0}
        elif existing is not None and (existing.amount != target or existing.case_id != movement.case_id):
            existing.amount = target
            existing.case_id = movement.case_id  # follow a re-pointed case
            existing.updated_by = member.user.id
            changes["discount"] = {"from": old, "to": target}
        elif existing is None and target > 0:
            session.add(
                CaseAdjustment(
                    clinic_id=member.clinic_id,
                    case_id=movement.case_id,
                    type=AdjustmentType.DISCOUNT,
                    amount=target,
                    note=movement.note,
                    movement_id=movement.id,
                    created_by=member.user.id,
                )
            )
            changes["discount"] = {"from": 0, "to": target}

    if changes:
        movement.updated_by = member.user.id
        record_audit(
            session,
            clinic_id=member.clinic_id,
            user_id=member.user.id,
            action="edit",
            entity_type="money_movement",
            entity_id=movement.id,
            detail=changes,
        )
        session.commit()
    movement_out = schemas.MovementOut.model_validate(movement)
    movement_out.discount = discount_for_movement(session, movement.id)
    return movement_out


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
