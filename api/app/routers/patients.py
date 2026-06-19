"""Patients and treatment cases (PRD stories 29-32)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import Case, Patient, Procedure
from app.services import case_outstanding_value, get_scoped, list_alive, record_audit

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
