# backend/amodb/alembic/env.py

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

# ---------------------------------------------------------------------------
# PYTHONPATH SETUP
# ---------------------------------------------------------------------------
# __file__  = backend/amodb/alembic/env.py
# BASE_DIR  = backend/
# package   = amodb
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import app and database AFTER adjusting sys.path
from amodb.database import Base, write_engine  # type: ignore

# Import model modules so all tables are registered on Base.metadata.
# IMPORTANT: we do NOT import `amodb.models` here to avoid any legacy tables.
from amodb.apps.accounts import models as accounts_models  # noqa: F401
from amodb.apps.fleet import models as fleet_models        # noqa: F401
from amodb.apps.work import models as work_models          # noqa: F401
from amodb.apps.crs import models as crs_models            # noqa: F401
from amodb.apps.maintenance_program import models as maintenance_program_models  # noqa: F401

# Alembic Config object (provides access to alembic.ini values)
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate'
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# OFFLINE MIGRATIONS
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this mode Alembic generates SQL without connecting to the DB.
    """

    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "No database URL found. Set sqlalchemy.url in alembic.ini or "
            "DATABASE_URL / DATABASE_WRITE_URL environment variable."
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


# ---------------------------------------------------------------------------
# ONLINE MIGRATIONS
# ---------------------------------------------------------------------------


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
            # You can add include_object / process_revision_directives here
            # later if you need finer control.
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
