"""Application settings, loaded from environment (12-factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. Tests use SQLite; production targets Postgres / Supabase,
    # e.g. "postgresql+psycopg://user:pass@host:5432/db". A bare "postgresql://"
    # (as Supabase hands out) is normalized to the psycopg driver in db.py.
    database_url: str = "sqlite+pysqlite:///./clinic.db"

    # Postgres/Supabase connection pool. Conservative defaults so a single
    # container stays well under Supabase's connection limits (ignored on SQLite).
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # Set true ONLY when database_url points at Supabase's transaction-mode pooler
    # (port 6543), which rejects server-side prepared statements.
    db_disable_prepared_statements: bool = False

    # Supabase issues the JWT; FastAPI verifies it (ADR-0001). HS256 uses the
    # shared secret below; newer Supabase projects sign with asymmetric keys
    # (ES256/RS256) verified against the project's JWKS — set ``supabase_url`` and
    # security.py fetches the keys from {supabase_url}/auth/v1/.well-known/jwks.json.
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_audience: str = "authenticated"
    supabase_url: str = ""

    # The single clinic this deployment serves (ADR-0005). Seeded at setup — this
    # is only the fallback name if /setup is called without one (the setup wizard
    # always sends a name, and currency, in the request body).
    clinic_name: str = "My Clinic"

    # Local-only convenience: issue a signed JWT for an email without Supabase,
    # so the app runs end-to-end in dev. MUST be False in production.
    dev_login_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
