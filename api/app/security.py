"""JWT verification. Supabase issues the token; FastAPI verifies it (ADR-0001).

Supabase signs tokens one of two ways depending on project age:

* **HS256** — a shared secret (``jwt_secret``). Classic / legacy projects.
* **ES256 / RS256** — asymmetric signing keys. Newer projects. The public keys
  are published at ``{supabase_url}/auth/v1/.well-known/jwks.json``; we fetch and
  cache them and verify against the key named by the token's ``kid``.

We pick the path from the token's own ``alg`` header, so either kind of project
works without reconfiguration. Authorization (the allowlist) and tenant scoping
live in FastAPI, not here — this module only proves the bearer is who Supabase
says they are.
"""

from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.config import get_settings

_ASYMMETRIC_ALGS = ("ES256", "RS256")


class AuthError(Exception):
    """Raised when a token is missing, malformed, expired, or otherwise invalid."""


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    # Cached so the JWKS is fetched once and reused (PyJWKClient caches keys).
    return PyJWKClient(jwks_url)


def verify_jwt(token: str) -> dict:
    settings = get_settings()
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
        if alg == "HS256":
            return jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=["HS256"],
                audience=settings.jwt_audience,
            )
        if alg in _ASYMMETRIC_ALGS:
            if not settings.supabase_url:
                raise AuthError(
                    f"token signed with {alg} but SUPABASE_URL is not configured "
                    "for JWKS verification"
                )
            jwks_url = (
                settings.supabase_url.rstrip("/")
                + "/auth/v1/.well-known/jwks.json"
            )
            signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience=settings.jwt_audience,
            )
        raise AuthError(f"unsupported token algorithm: {alg or 'none'}")
    except jwt.PyJWTError as exc:  # includes PyJWKClientError (key fetch/lookup)
        raise AuthError(str(exc)) from exc
