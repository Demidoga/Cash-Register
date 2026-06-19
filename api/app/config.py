"""Application settings, loaded from environment (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. Tests use SQLite; production targets Postgres / Supabase,
    # e.g. "postgresql+psycopg://user:pass@host:5432/db".
    database_url: str = "sqlite+pysqlite:///./clinic.db"

    # Supabase issues the JWT; FastAPI verifies it (ADR-0001). Legacy-style HS256
    # shared secret. JWKS/RS256 is a production-hardening follow-up.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_audience: str = "authenticated"

    # The single clinic this deployment serves (ADR-0005). Seeded at setup.
    clinic_name: str = "My Clinic"
    clinic_currency: str = "PKR"

    # Local-only convenience: issue a signed JWT for an email without Supabase,
    # so the app runs end-to-end in dev. MUST be False in production.
    dev_login_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
