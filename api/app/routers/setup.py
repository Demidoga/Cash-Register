"""Setup (seed the single clinic) and identity (/me).

Setup is the one write that does not require an existing Membership: the first
authenticated owner bootstraps the clinic (ADR-0005). Every later request is
gated by the allowlist.
"""

from __future__ import annotations

from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas
from app.config import get_settings
from app.db import get_session
from app.deps import CurrentMember, Identity, get_current_member, get_identity
from app.models import (
    Account,
    Clinic,
    Membership,
    Partner,
    PartnerShare,
    Role,
    ShareWindow,
    User,
)
from app.money_math.types import AccountKind
from app.services import record_audit

router = APIRouter(tags=["setup"])


def _get_or_create_user(session: Session, identity: Identity) -> User:
    user = session.scalar(
        select(User).where(User.email == identity.email, User.deleted_at.is_(None))
    )
    if user is None:
        user = User(
            email=identity.email,
            supabase_sub=identity.sub,
            full_name=identity.full_name,
        )
        session.add(user)
        session.flush()
    return user


@router.post("/setup", response_model=schemas.SetupResponse, status_code=status.HTTP_201_CREATED)
def setup(
    body: schemas.SetupRequest,
    identity: Identity = Depends(get_identity),
    session: Session = Depends(get_session),
) -> schemas.SetupResponse:
    if session.scalar(select(Clinic).where(Clinic.deleted_at.is_(None))) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "clinic already set up")

    total = sum((Fraction(p.share_num, p.share_den) for p in body.partners), Fraction(0))
    if total != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "partner shares must sum to 1"
        )

    user = _get_or_create_user(session, identity)
    clinic = Clinic(name=body.clinic_name or get_settings().clinic_name, currency=body.currency)
    session.add(clinic)
    session.flush()

    session.add(
        Membership(clinic_id=clinic.id, user_id=user.id, role=Role.OWNER, created_by=user.id)
    )

    partners: list[Partner] = []
    for p in body.partners:
        partner = Partner(clinic_id=clinic.id, name=p.name, created_by=user.id)
        session.add(partner)
        partners.append(partner)
    session.flush()

    window = ShareWindow(
        clinic_id=clinic.id, effective_from=body.effective_from, created_by=user.id
    )
    session.add(window)
    session.flush()
    for p_in, partner in zip(body.partners, partners):
        session.add(
            PartnerShare(
                share_window_id=window.id,
                partner_id=partner.id,
                share_num=p_in.share_num,
                share_den=p_in.share_den,
            )
        )

    accounts: list[Account] = []
    for a in body.accounts:
        owner_id: int | None = None
        if a.kind is AccountKind.PERSONAL:
            if a.owner_partner_index is None or not (
                0 <= a.owner_partner_index < len(partners)
            ):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "personal account needs a valid owner_partner_index",
                )
            owner_id = partners[a.owner_partner_index].id
        elif a.owner_partner_index is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "joint account must not have an owner"
            )
        account = Account(
            clinic_id=clinic.id,
            name=a.name,
            kind=a.kind,
            owner_partner_id=owner_id,
            opening_balance=a.opening_balance,
            created_by=user.id,
        )
        session.add(account)
        accounts.append(account)
    session.flush()

    record_audit(
        session,
        clinic_id=clinic.id,
        user_id=user.id,
        action="setup",
        entity_type="clinic",
        entity_id=clinic.id,
    )
    session.commit()

    return schemas.SetupResponse(
        clinic_id=clinic.id,
        share_window_id=window.id,
        partners=[schemas.PartnerOut.model_validate(p) for p in partners],
        accounts=[schemas.AccountOut.model_validate(a) for a in accounts],
    )


@router.get("/me", response_model=schemas.MeResponse)
def me(member: CurrentMember = Depends(get_current_member)) -> schemas.MeResponse:
    return schemas.MeResponse(
        user_id=member.user.id,
        email=member.user.email,
        clinic_id=member.clinic_id,
        role=member.role,
    )
