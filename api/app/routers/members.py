"""Members / the allowlist (ADR-0008): invite by email, list, revoke.

The clinic owner grants access by **adding an email** — the backend creates a
``User`` stub (email only) plus a ``Membership`` with the ``partner`` access
tier. No email is sent and no token is issued: the invitee gains access by
signing in to Supabase with that email, at which point ``get_current_member``
matches by email and backfills the stub. These are the only endpoints gated by
``require_owner`` — the app's first real role gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_session
from app.deps import CurrentMember, require_owner
from app.models import Membership, Role, User
from app.services import record_audit, soft_delete

router = APIRouter(tags=["members"])


def _normalize_email(raw: str) -> str:
    """Lowercase + trim to match ``get_identity`` (which lowercases the JWT
    email), with a minimal shape check — we deliberately avoid the
    email-validator dependency."""
    email = raw.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email")
    return email


def _member_out(membership: Membership, user: User) -> schemas.MemberOut:
    return schemas.MemberOut(
        id=membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        # A stub that has never signed in has no Supabase sub yet → pending.
        status="active" if user.supabase_sub else "pending",
        role=membership.role,
    )


@router.post("/members", response_model=schemas.InviteResponse)
def invite_member(
    body: schemas.InviteRequest,
    response: Response,
    member: CurrentMember = Depends(require_owner),
    session: Session = Depends(get_session),
) -> schemas.InviteResponse:
    email = _normalize_email(body.email)

    # User.email is globally unique (ignoring soft-delete), so look up without a
    # deleted_at filter — otherwise a soft-deleted row with this email would slip
    # past and the INSERT below would hit the unique constraint.
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        # The second place that ever creates a User (the first is /setup): a stub
        # with email only — the JWT backfills sub/name on first sign-in.
        user = User(email=email)
        session.add(user)
        session.flush()
    elif user.deleted_at is not None:
        user.deleted_at = None  # granting access to this email revives its identity

    # Look up the membership ignoring soft-delete: uq_membership is
    # (clinic_id, user_id) and ignores deleted_at, so a revoked email already has
    # a row we must reactivate rather than insert a colliding one (ADR-0008).
    membership = session.scalar(
        select(Membership).where(
            Membership.clinic_id == member.clinic_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        membership = Membership(
            clinic_id=member.clinic_id,
            user_id=user.id,
            role=Role.PARTNER,
            created_by=member.user.id,
        )
        session.add(membership)
        session.flush()
        outcome = "invited"
    elif membership.deleted_at is not None:
        # Restore the existing row (uq_membership ignores soft-delete, so we must
        # reactivate, not insert) keeping its prior tier — don't silently demote.
        membership.deleted_at = None
        membership.updated_by = member.user.id
        outcome = "reactivated"
    else:
        # Already on the allowlist — idempotent no-op, not a 500 (uq violation).
        response.status_code = status.HTTP_200_OK
        return schemas.InviteResponse(
            member=_member_out(membership, user), status="already_member"
        )

    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="invite",
        entity_type="membership",
        entity_id=membership.id,
        detail={"email": email, "outcome": outcome},
    )
    session.commit()
    response.status_code = (
        status.HTTP_201_CREATED if outcome == "invited" else status.HTTP_200_OK
    )
    return schemas.InviteResponse(member=_member_out(membership, user), status=outcome)


@router.get("/members", response_model=list[schemas.MemberOut])
def list_members(
    member: CurrentMember = Depends(require_owner),
    session: Session = Depends(get_session),
) -> list[schemas.MemberOut]:
    """The clinic's allowlist. Revoked (soft-deleted) memberships drop off;
    invited-but-never-signed-in stubs show as ``pending``."""
    rows = session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.clinic_id == member.clinic_id,
            Membership.deleted_at.is_(None),
        )
        .order_by(Membership.id)
    ).all()
    return [_member_out(m, u) for m, u in rows]


@router.delete("/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_member(
    membership_id: int,
    member: CurrentMember = Depends(require_owner),
    session: Session = Depends(get_session),
) -> None:
    """Soft-delete a Membership. The revoked user is blocked immediately at
    ``get_current_member`` even if they still hold a valid JWT (ADR-0008)."""
    membership = session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.clinic_id == member.clinic_id,
            Membership.deleted_at.is_(None),
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    # Last-owner before self: a sole owner revoking themselves is *also* the last
    # owner, and "the clinic must keep an owner" is the stronger invariant — so
    # that case reports the last-owner reason, leaving the self guard to fire only
    # when a co-owner exists (ADR-0008).
    if membership.role is Role.OWNER:
        owner_count = session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.clinic_id == member.clinic_id,
                Membership.role == Role.OWNER,
                Membership.deleted_at.is_(None),
            )
        )
        if (owner_count or 0) <= 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "cannot revoke the last owner"
            )
    if membership.user_id == member.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot revoke yourself")

    soft_delete(membership, member.user.id)
    record_audit(
        session,
        clinic_id=member.clinic_id,
        user_id=member.user.id,
        action="revoke",
        entity_type="membership",
        entity_id=membership.id,
    )
    session.commit()
