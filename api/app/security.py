"""JWT verification. Supabase issues the token; FastAPI verifies it (ADR-0001).

Authorization (the allowlist) and tenant scoping live in FastAPI, not here —
this module only proves the bearer of the token is who Supabase says they are.
"""

from __future__ import annotations

import jwt

from app.config import get_settings


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or otherwise invalid."""


def verify_jwt(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - exercised via deps tests
        raise AuthError(str(exc)) from exc
