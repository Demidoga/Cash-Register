"""Patients and treatment cases (PRD stories 29-32)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Case, Patient, Procedure
from app.services import (
    case_outstanding_value,
    get_scoped,
    list_alive,
    record_audit,
    soft_delete,
)

router = APIRouter(tags=["patients"])


def _case_out(session: Session, clinic_id: int, case: Case) -> schemas.CaseOut:
    return schemas.CaseOut(
        id=case.id,
        patient_id=case.patient_id,
        procedure_name=case.procedure_name,
        agreed_price=case.agreed_price,
        status=case.status,
        outstanding=case_outstanding_value(session, clinic_id, case),
    )


@router.get("/patients", response_model=list[schemas.PatientOut])
def list_patients(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [schemas.PatientOut.model_validate(p) for p in list_alive(session, Patient, member.clinic_id)]


@router.get("/cases", response_model=list[schemas.CaseOut])
def list_cases(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [_case_out(session, member.clinic_id, c) for c in list_alive(session, Case, member.clinic_id)]


@router.post("/patients", response_model=schemas.PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: schemas.PatientCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.PatientOut:
    patient = Patient(
        clinic_id=member.clinic_id,
        name=body.name,
        phone=body.phone,
        notes=body.notes,
        created_by=member.user.id,
    )
    session.add(patient)
    session.flush()
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="create",
        entity_type="patient",
        entity_id=patient.id,
    )
    session.commit()
    return schemas.PatientOut.model_validate(patient)


@router.get("/patients/{patient_id}", response_model=schemas.PatientDetailOut)
def get_patient(
    patient_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.PatientDetailOut:
    patient = get_scoped(session, Patient, patient_id, member.clinic_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    cases = session.scalars(
        select(Case).where(
            Case.patient_id == patient.id,
            Case.clinic_id == member.clinic_id,
            Case.deleted_at.is_(None),
        )
    ).all()
    case_outs = [_case_out(session, member.clinic_id, c) for c in cases]
    # Outstanding across all cases; advances (negative) net against what's owed.
    total = sum(c.outstanding for c in case_outs)
    return schemas.PatientDetailOut(
        id=patient.id,
        name=patient.name,
        phone=patient.phone,
        notes=patient.notes,
        total_outstanding=total,
        cases=case_outs,
    )


def _patient_cases(session: Session, clinic_id: int, patient_id: int, *, alive: bool):
    """The patient's cases, either currently alive or currently soft-deleted."""
    deleted_filter = Case.deleted_at.is_(None) if alive else Case.deleted_at.is_not(None)
    return session.scalars(
        select(Case).where(
            Case.patient_id == patient_id,
            Case.clinic_id == clinic_id,
            deleted_filter,
        )
    ).all()


@router.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(
    patient_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Soft-delete a patient and cascade to their open cases (ADR-0006 —
    recoverable). Money movements are left untouched: the cash really moved, so
    profit/settlement history is never rewritten by removing a patient. Restore
    revives the patient together with the cases that went down with them."""
    patient = get_scoped(session, Patient, patient_id, member.clinic_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    cases = _patient_cases(session, member.clinic_id, patient.id, alive=True)
    for case in cases:
        soft_delete(case, member.user.id)
    soft_delete(patient, member.user.id)
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="delete",
        entity_type="patient",
        entity_id=patient.id,
        detail={"cascaded_case_ids": [c.id for c in cases]},
    )
    session.commit()


@router.post("/patients/{patient_id}/restore", response_model=schemas.PatientOut)
def restore_patient(
    patient_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.PatientOut:
    """Undo a delete: revive the patient and the cases that were cascaded with
    them. (Cases are only ever soft-deleted via the patient cascade, so reviving
    the patient's soft-deleted cases restores exactly that set.)"""
    patient = session.get(Patient, patient_id)
    if patient is None or patient.clinic_id != member.clinic_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    if patient.deleted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "patient is not deleted")
    patient.deleted_at = None
    patient.updated_by = member.user.id
    for case in _patient_cases(session, member.clinic_id, patient.id, alive=False):
        case.deleted_at = None
        case.updated_by = member.user.id
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="restore",
        entity_type="patient",
        entity_id=patient.id,
    )
    session.commit()
    return schemas.PatientOut.model_validate(patient)


@router.post("/cases", response_model=schemas.CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    body: schemas.CaseCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.CaseOut:
    patient = get_scoped(session, Patient, body.patient_id, member.clinic_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patient not found")
    if body.procedure_id is not None and get_scoped(
        session, Procedure, body.procedure_id, member.clinic_id
    ) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "procedure not found")
    case = Case(
        clinic_id=member.clinic_id,
        patient_id=patient.id,
        procedure_name=body.procedure_name,
        procedure_id=body.procedure_id,
        agreed_price=body.agreed_price,
        created_by=member.user.id,
    )
    session.add(case)
    session.flush()
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="create",
        entity_type="case",
        entity_id=case.id,
    )
    session.commit()
    return _case_out(session, member.clinic_id, case)


@router.get("/cases/{case_id}", response_model=schemas.CaseOut)
def get_case(
    case_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.CaseOut:
    case = get_scoped(session, Case, case_id, member.clinic_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    return _case_out(session, member.clinic_id, case)


@router.patch("/cases/{case_id}", response_model=schemas.CaseOut)
def edit_case(
    case_id: int,
    body: schemas.CaseUpdate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
) -> schemas.CaseOut:
    """Correct a case's own details — procedure, agreed price, status. Like the
    movement editor, it records the old → new diff so the audit trail explains
    the change; a no-op edit leaves no trace. Adjustments (discount/write-off)
    stay separate endpoints — editing the agreed price is not a discount."""
    case = get_scoped(session, Case, case_id, member.clinic_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")

    changes: dict[str, dict] = {}
    if body.procedure_name is not None and body.procedure_name != case.procedure_name:
        changes["procedure_name"] = {"from": case.procedure_name, "to": body.procedure_name}
        case.procedure_name = body.procedure_name
    if "procedure_id" in body.model_fields_set and body.procedure_id != case.procedure_id:
        if body.procedure_id is not None:
            if get_scoped(session, Procedure, body.procedure_id, member.clinic_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "procedure not found")
        changes["procedure_id"] = {"from": case.procedure_id, "to": body.procedure_id}
        case.procedure_id = body.procedure_id
    if body.agreed_price is not None and body.agreed_price != case.agreed_price:
        changes["agreed_price"] = {"from": case.agreed_price, "to": body.agreed_price}
        case.agreed_price = body.agreed_price
    if body.status is not None and body.status != case.status:
        changes["status"] = {"from": case.status, "to": body.status}
        case.status = body.status

    if changes:
        case.updated_by = member.user.id
        record_audit(
            session,
            clinic_id=member.clinic_id,
            user_id=member.user.id,
            action="edit",
            entity_type="case",
            entity_id=case.id,
            detail=changes,
        )
        session.commit()
    return _case_out(session, member.clinic_id, case)
