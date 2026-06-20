"""FastAPI dependencies: authentication, the allowlist, and tenant scoping.

Authentication proves identity (the verified JWT); **authorization is the
allowlist** — a Membership row — and every query is scoped to the member's
clinic (ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Membership, Role, User
from app.security import AuthError, verify_jwt


@dataclass
class Identity:
    email: str
    sub: str | None
    full_name: str | None


@dataclass
class CurrentMember:
    user: User
    membership: Membership
    clinic_id: int
    role: Role


def get_claims(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return verify_jwt(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}")


def get_identity(claims: dict = Depends(get_claims)) -> Identity:
    email = claims.get("email")
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token has no email claim")
    meta = claims.get("user_metadata")
    full_name = meta.get("full_name") if isinstance(meta, dict) else claims.get("name")
    # Strip + lowercase so this matches the allowlist email exactly — invite
    # normalizes the same way (_normalize_email in routers/members.py).
    return Identity(email=email.strip().lower(), sub=claims.get("sub"), full_name=full_name)


def get_current_member(
    identity: Identity = Depends(get_identity),
    session: Session = Depends(get_session),
) -> CurrentMember:
    """Authenticated *and* allowlisted. A valid login alone is not enough — the
    identity must have a Membership (PRD story 7)."""
    user = session.scalar(
        select(User).where(User.email == identity.email, User.deleted_at.is_(None))
    )
    if user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not on the clinic allowlist")
    memberships = session.scalars(
        select(Membership).where(
            Membership.user_id == user.id, Membership.deleted_at.is_(None)
        )
    ).all()
    if not memberships:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not on the clinic allowlist")
    if len(memberships) > 1:
        # Single-clinic invariant (ADR-0005): a user has at most one membership.
        # If that ever breaks we must not silently pick one — fail loudly here so
        # whoever adds multi-clinic support resolves the intended clinic explicitly
        # (ADR-0008 consequences).
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "user belongs to multiple clinics; clinic resolution is not implemented",
        )
    membership = memberships[0]
    _backfill_stub_identity(session, user, identity)
    return CurrentMember(
        user=user,
        membership=membership,
        clinic_id=membership.clinic_id,
        role=membership.role,
    )


def _backfill_stub_identity(session: Session, user: User, identity: Identity) -> None:
    """First sign-in of an invited stub: an invite creates a ``User`` with email
    only (ADR-0008), so the verified JWT is where we first learn that person's
    Supabase ``sub`` and display name. Idempotent — only fills blanks."""
    changed = False
    if identity.sub and user.supabase_sub is None:
        user.supabase_sub = identity.sub
        changed = True
    if identity.full_name and user.full_name is None:
        user.full_name = identity.full_name
        changed = True
    if changed:
        session.commit()


def require_owner(member: CurrentMember = Depends(get_current_member)) -> CurrentMember:
    """The app's first real role gate: only an ``owner`` may invite, list, or
    revoke members (ADR-0008). Every other endpoint settles for any Membership."""
    if member.role is not Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner access required")
    return member
