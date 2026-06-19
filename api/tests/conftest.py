"""Test harness for the HTTP seam (ADR-0001 primary seam).

Each test runs against a fresh in-memory SQLite DB (production uses Postgres);
the ``get_session`` dependency is overridden to the test session factory.
"""

from __future__ import annotations

import os

# Pin auth + DB settings *before* the app (and its cached settings) import.
os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long-xxxx")
os.environ.setdefault("JWT_AUDIENCE", "authenticated")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables on Base.metadata)
from app.db import Base, get_session
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection -> in-memory DB persists
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    def _override_get_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()
