"""Application settings, loaded from environment (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. Tests use SQLite; production targets Postgres / Supabase,
    # e.g. "postgresql+psycopg://user:pass@host:5432/db".
    database_url: str = "sqlite+pysqlite:///./clinic.db"

    # Supabase issues the JWT; FastAPI verifies it (ADR-0001). HS256 uses the
    # shared secret below; newer Supabase projects sign with asymmetric keys
    # (ES256/RS256) verified against the project's JWKS — set ``supabase_url`` and
    # security.py fetches the keys from {supabase_url}/auth/v1/.well-known/jwks.json.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_audience: str = "authenticated"
    supabase_url: str = ""

    # The single clinic this deployment serves (ADR-0005). Seeded at setup.
    clinic_name: str = "My Clinic"
    clinic_currency: str = "PKR"

    # Local-only convenience: issue a signed JWT for an email without Supabase,
    # so the app runs end-to-end in dev. MUST be False in production.
    dev_login_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
