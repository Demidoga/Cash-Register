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


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


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
