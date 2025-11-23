# backend/amodb/alembic/env.py

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

# -----------------------------------------------------------------------------
# Make the project package importable (so "import amodb" works)
# -----------------------------------------------------------------------------
#
# __file__ = backend/amodb/alembic/env.py
# project root = backend/
# package root  = backend/amodb
# We add backend/ to sys.path.
# -----------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Now we can import the app
from amodb.database import Base, write_engine  # type: ignore
from amodb import core_models, fleet_models, work_models, crs_models  # noqa: F401

# This grabs the Alembic Config object (gives us access to alembic.ini)
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate'
target_metadata = Base.metadata


# -----------------------------------------------------------------------------
# OFFLINE MIGRATIONS
# -----------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this mode we just generate SQL; no actual DB connection is opened.
    """

    # Prefer alembic.ini sqlalchemy.url, fall back to env vars.
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "No database URL found. Set sqlalchemy.url in alembic.ini or "
            "DATABASE_URL / DATABASE_WRITE_URL env var."
        )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# -----------------------------------------------------------------------------
# ONLINE MIGRATIONS
# -----------------------------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Here we use the same write_engine as the application.
    """

    connectable = write_engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# -----------------------------------------------------------------------------
# ENTRYPOINT
# -----------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
