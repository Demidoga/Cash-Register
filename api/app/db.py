"""Database engine, session factory, and the declarative Base.

The engine is configurable so tests can point at SQLite while production points
at Postgres (ADR-0001). ``get_session`` is the FastAPI dependency; tests swap
the bound session factory via ``configure``.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Deterministic constraint names — required for SQLite batch migrations and
# tidy on Postgres (lets Alembic ALTER named constraints).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def normalize_url(url: str) -> str:
    """Force the installed psycopg (v3) driver for bare Postgres URLs.

    Supabase (and Heroku-style providers) hand out ``postgresql://...`` or
    ``postgres://...``. SQLAlchemy maps those to psycopg2, which is **not**
    installed — only psycopg (v3) is — so connecting would raise ModuleNotFound.
    Also used by Alembic's env.py so migrations accept the same bare URL.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        return create_engine(
            url, connect_args={"check_same_thread": False}, future=True
        )
    # Postgres / Supabase. pool_pre_ping recycles connections the Supavisor
    # pooler or idle timeouts have dropped, instead of erroring mid-request.
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.db_disable_prepared_statements:
        # Required for Supabase's transaction-mode pooler (port 6543), which
        # rejects server-side prepared statements.
        connect_args["prepare_threshold"] = None
    return create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        future=True,
    )


# Module-level engine/session factory, (re)bindable via configure().
engine: Engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def configure(url: str) -> Engine:
    """Rebind the module engine + session factory to ``url`` (used by tests)."""
    global engine, SessionLocal
    engine = make_engine(url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    return engine


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
