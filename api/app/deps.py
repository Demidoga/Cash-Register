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
    return Identity(email=email.lower(), sub=claims.get("sub"), full_name=full_name)


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
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.deleted_at.is_(None)
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not on the clinic allowlist")
    return CurrentMember(
        user=user,
        membership=membership,
        clinic_id=membership.clinic_id,
        role=membership.role,
    )
