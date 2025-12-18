# backend/amodb/alembic/env.py

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool  # kept for compatibility with typical alembic templates

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

# Alembic Config object (provides access to alembic.ini values)
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import app and database AFTER adjusting sys.path
from amodb.database import Base, write_engine  # type: ignore  # noqa: E402

# Import model modules so all tables are registered on Base.metadata.
# IMPORTANT: we do NOT import `amodb.models` here to avoid any legacy tables.
from amodb.apps.accounts import models as accounts_models  # noqa: F401, E402
from amodb.apps.fleet import models as fleet_models  # noqa: F401, E402
from amodb.apps.work import models as work_models  # noqa: F401, E402
from amodb.apps.crs import models as crs_models  # noqa: F401, E402
from amodb.apps.maintenance_program import models as maintenance_program_models  # noqa: F401, E402

# ADD: Training models so Alembic can create/update training tables
from amodb.apps.training import models as training_models  # noqa: F401, E402

# Target metadata for 'autogenerate'
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# URL RESOLUTION (offline safety)
# ---------------------------------------------------------------------------

_DUMMY_URLS = {
    "driver://user:pass@localhost/dbname",
    "driver://user:pass@localhost/dbname/",
}


def _is_placeholder_url(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return True
    if u in _DUMMY_URLS:
        return True
    # Common placeholder pattern people leave in alembic.ini
    if u.startswith("driver://"):
        return True
    return False


def _resolve_offline_url() -> str:
    """
    Offline mode needs a URL to render SQL.
    Prefer sqlalchemy.url unless it is the placeholder, then fall back to env vars.
    """
    url = (config.get_main_option("sqlalchemy.url") or "").strip()

    if _is_placeholder_url(url):
        url = (os.getenv("DATABASE_WRITE_URL") or os.getenv("DATABASE_URL") or "").strip()

    if not url:
        raise RuntimeError(
            "No database URL found.\n"
            "Set sqlalchemy.url in alembic.ini OR set DATABASE_WRITE_URL / DATABASE_URL."
        )

    # Ensure the resolved URL is what Alembic sees for offline generation
    config.set_main_option("sqlalchemy.url", url)
    return url


# ---------------------------------------------------------------------------
# OFFLINE MIGRATIONS
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this mode Alembic generates SQL without connecting to the DB.
    """
    url = _resolve_offline_url()

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
            # You can add include_object / process_revision_directives here later if needed.
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
