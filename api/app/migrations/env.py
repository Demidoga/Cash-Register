"""Alembic environment — wired to the app's settings and declarative Base."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (import so all tables register on Base.metadata)
from app.config import get_settings
from app.db import Base, normalize_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Keep the DB URL OUT of the Alembic config (ConfigParser): a percent-encoded
# password (e.g. Supabase's, %40/%2F/%24) trips its % interpolation. We hand the
# URL straight to the engine instead. normalize_url forces the psycopg driver for
# a bare postgresql:// URL (as Supabase hands out).
db_url = normalize_url(get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        # Batch mode is a SQLite workaround (table-copy ALTERs); on Postgres it
        # produces needlessly destructive migrations.
        render_as_batch=db_url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(db_url, poolclass=pool.NullPool, future=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite-only (see run_migrations_offline).
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
