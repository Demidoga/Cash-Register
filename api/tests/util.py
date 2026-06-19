"""Helpers for minting Supabase-style JWTs in tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings


def make_token(
    email: str,
    *,
    sub: str | None = None,
    name: str | None = None,
    secret: str | None = None,
    audience: str | None = None,
) -> str:
    settings = get_settings()
    payload: dict = {
        "email": email,
        "aud": audience or settings.jwt_audience,
        "sub": sub or email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    if name:
        payload["user_metadata"] = {"full_name": name}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm="HS256")


def auth(email: str, **kwargs) -> dict[str, str]:
    """Authorization header for ``email`` (a valid signed token)."""
    return {"Authorization": f"Bearer {make_token(email, **kwargs)}"}


# A realistic Milestone-0 clinic: two 50/50 partners, each with a personal cash
# account, plus a shared joint account.
OWNER_EMAIL = "saad@smileclinic.test"

SETUP_BODY = {
    "clinic_name": "Smile Clinic",
    "currency": "PKR",
    "effective_from": "2026-01-01",
    "partners": [
        {"name": "Saad", "share_num": 1, "share_den": 2},
        {"name": "Hassan", "share_num": 1, "share_den": 2},
    ],
    "accounts": [
        {"name": "Saad Cash", "kind": "personal", "owner_partner_index": 0},
        {"name": "Hassan Cash", "kind": "personal", "owner_partner_index": 1},
        {"name": "Joint", "kind": "joint"},
    ],
}


def setup_clinic(client) -> dict:
    response = client.post("/setup", json=SETUP_BODY, headers=auth(OWNER_EMAIL))
    assert response.status_code == 201, response.text
    return response.json()
