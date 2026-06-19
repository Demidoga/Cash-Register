"""Configuration (Milestone 1): partners/shares, accounts, categories,
procedures, employees. Owner-managed clinic setup beyond the initial seed."""

from __future__ import annotations

from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, get_current_member
from app.models import (
    Account,
    Category,
    Employee,
    Partner,
    PartnerShare,
    Procedure,
    ShareWindow,
)
from app.money_math.types import AccountKind
from app.services import get_scoped, list_alive, record_audit, soft_delete

router = APIRouter(tags=["config"])


def _audit(session, member, action, entity_type, entity_id):
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )


# --- partners ----------------------------------------------------------------


@router.get("/partners", response_model=list[schemas.PartnerOut])
def list_partners(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [schemas.PartnerOut.model_validate(p) for p in list_alive(session, Partner, member.clinic_id)]


# --- share windows (effective-dated shares, story 12) ------------------------


@router.get("/share-windows", response_model=list[schemas.ShareWindowOut])
def list_share_windows(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    windows = session.scalars(
        select(ShareWindow)
        .where(ShareWindow.clinic_id == member.clinic_id, ShareWindow.deleted_at.is_(None))
        .order_by(ShareWindow.effective_from)
    ).all()
    out = []
    for w in windows:
        shares = session.scalars(
            select(PartnerShare).where(PartnerShare.share_window_id == w.id)
        ).all()
        out.append(
            schemas.ShareWindowOut(
                id=w.id,
                effective_from=w.effective_from,
                shares=[
                    schemas.ShareEntry(
                        partner_id=s.partner_id, share_num=s.share_num, share_den=s.share_den
                    )
                    for s in shares
                ],
            )
        )
    return out


@router.post("/share-windows", response_model=schemas.ShareWindowOut, status_code=201)
def create_share_window(
    body: schemas.ShareWindowCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    total = sum((Fraction(s.share_num, s.share_den) for s in body.shares), Fraction(0))
    if total != 1:
        raise HTTPException(422, "partner shares must sum to 1")
    for s in body.shares:
        if get_scoped(session, Partner, s.partner_id, member.clinic_id) is None:
            raise HTTPException(404, f"partner {s.partner_id} not found")

    window = ShareWindow(
        clinic_id=member.clinic_id, effective_from=body.effective_from, created_by=member.user.id
    )
    session.add(window)
    session.flush()
    for s in body.shares:
        session.add(
            PartnerShare(
                share_window_id=window.id,
                partner_id=s.partner_id,
                share_num=s.share_num,
                share_den=s.share_den,
            )
        )
    _audit(session, member, "create", "share_window", window.id)
    session.commit()
    return schemas.ShareWindowOut(
        id=window.id, effective_from=window.effective_from, shares=body.shares
    )


# --- accounts ----------------------------------------------------------------


@router.get("/accounts", response_model=list[schemas.AccountFullOut])
def list_accounts(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [
        schemas.AccountFullOut.model_validate(a)
        for a in list_alive(session, Account, member.clinic_id)
    ]


@router.post("/accounts", response_model=schemas.AccountFullOut, status_code=201)
def create_account(
    body: schemas.AccountCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    if body.kind is AccountKind.PERSONAL:
        if body.owner_partner_id is None or get_scoped(
            session, Partner, body.owner_partner_id, member.clinic_id
        ) is None:
            raise HTTPException(422, "personal account needs a valid owner_partner_id")
    elif body.owner_partner_id is not None:
        raise HTTPException(422, "joint account must not have an owner")

    account = Account(
        clinic_id=member.clinic_id,
        name=body.name,
        kind=body.kind,
        owner_partner_id=body.owner_partner_id,
        opening_balance=body.opening_balance,
        created_by=member.user.id,
    )
    session.add(account)
    session.flush()
    _audit(session, member, "create", "account", account.id)
    session.commit()
    return schemas.AccountFullOut.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=schemas.AccountFullOut)
def update_account(
    account_id: int,
    body: schemas.AccountUpdate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    account = get_scoped(session, Account, account_id, member.clinic_id)
    if account is None:
        raise HTTPException(404, "account not found")
    if body.name is not None:
        account.name = body.name
    if body.is_active is not None:
        account.is_active = body.is_active  # enable/disable, e.g. the joint account
    account.updated_by = member.user.id
    _audit(session, member, "update", "account", account.id)
    session.commit()
    return schemas.AccountFullOut.model_validate(account)


# --- categories / procedures / employees (simple owned lists) ----------------


@router.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [schemas.CategoryOut.model_validate(c) for c in list_alive(session, Category, member.clinic_id)]


@router.post("/categories", response_model=schemas.CategoryOut, status_code=201)
def create_category(
    body: schemas.CategoryCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    category = Category(clinic_id=member.clinic_id, name=body.name, created_by=member.user.id)
    session.add(category)
    session.flush()
    _audit(session, member, "create", "category", category.id)
    session.commit()
    return schemas.CategoryOut.model_validate(category)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    category = get_scoped(session, Category, category_id, member.clinic_id)
    if category is None:
        raise HTTPException(404, "category not found")
    soft_delete(category, member.user.id)
    _audit(session, member, "delete", "category", category.id)
    session.commit()


@router.get("/procedures", response_model=list[schemas.ProcedureOut])
def list_procedures(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [schemas.ProcedureOut.model_validate(p) for p in list_alive(session, Procedure, member.clinic_id)]


@router.post("/procedures", response_model=schemas.ProcedureOut, status_code=201)
def create_procedure(
    body: schemas.ProcedureCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    procedure = Procedure(
        clinic_id=member.clinic_id,
        name=body.name,
        default_price=body.default_price,
        created_by=member.user.id,
    )
    session.add(procedure)
    session.flush()
    _audit(session, member, "create", "procedure", procedure.id)
    session.commit()
    return schemas.ProcedureOut.model_validate(procedure)


@router.delete("/procedures/{procedure_id}", status_code=204)
def delete_procedure(
    procedure_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    procedure = get_scoped(session, Procedure, procedure_id, member.clinic_id)
    if procedure is None:
        raise HTTPException(404, "procedure not found")
    soft_delete(procedure, member.user.id)
    _audit(session, member, "delete", "procedure", procedure.id)
    session.commit()


@router.get("/employees", response_model=list[schemas.EmployeeOut])
def list_employees(
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return [schemas.EmployeeOut.model_validate(e) for e in list_alive(session, Employee, member.clinic_id)]


@router.post("/employees", response_model=schemas.EmployeeOut, status_code=201)
def create_employee(
    body: schemas.EmployeeCreate,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    employee = Employee(
        clinic_id=member.clinic_id,
        name=body.name,
        role=body.role,
        salary=body.salary,
        created_by=member.user.id,
    )
    session.add(employee)
    session.flush()
    _audit(session, member, "create", "employee", employee.id)
    session.commit()
    return schemas.EmployeeOut.model_validate(employee)


@router.delete("/employees/{employee_id}", status_code=204)
def delete_employee(
    employee_id: int,
    member: CurrentMember = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    employee = get_scoped(session, Employee, employee_id, member.clinic_id)
    if employee is None:
        raise HTTPException(404, "employee not found")
    soft_delete(employee, member.user.id)
    _audit(session, member, "delete", "employee", employee.id)
    session.commit()
