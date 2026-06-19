"""Dev-only auth: mint a signed JWT for an email without Supabase, so the app
runs end to end locally. Gated by ``DEV_LOGIN_ENABLED`` — MUST be False in prod,
where Supabase issues the token and this endpoint returns 404.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, status

from app import schemas
from app.config import get_settings

router = APIRouter(tags=["dev"])


@router.post("/dev/login", response_model=schemas.DevLoginResponse)
def dev_login(body: schemas.DevLoginRequest) -> schemas.DevLoginResponse:
    settings = get_settings()
    if not settings.dev_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    payload: dict = {
        "email": body.email,
        "aud": settings.jwt_audience,
        "sub": body.email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    if body.name:
        payload["user_metadata"] = {"full_name": body.name}
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return schemas.DevLoginResponse(access_token=token)
