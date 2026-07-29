# backend/amodb/alembic/env.py

from __future__ import annotations

import os
import sys
from collections import defaultdict
from logging.config import fileConfig

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, pool, text  # kept for compatibility with typical alembic templates

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
from amodb.apps.foundations import models as foundations_models  # noqa: F401, E402
from amodb.apps.rostering import models as rostering_models  # noqa: F401, E402

# ADD: Training models so Alembic can create/update training tables
from amodb.apps.training import models as training_models  # noqa: F401, E402

# ADD: Quality models so Alembic can create/update QMS tables
from amodb.apps.quality import models as quality_models  # noqa: F401, E402
from amodb.apps.reliability import models as reliability_models  # noqa: F401, E402
from amodb.apps.inventory import models as inventory_models  # noqa: F401, E402
from amodb.apps.finance import models as finance_models  # noqa: F401, E402
import amodb.apps.realtime.models as realtime_models  # noqa: F401, E402
from amodb.apps.doc_control import domain_models as document_control_domain_models  # noqa: F401, E402
from amodb.apps.doc_control import knowledge_models as document_control_knowledge_models  # noqa: F401, E402

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

def _configured_script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(config)


def _database_revision_rows(connection) -> set[str]:
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        return set()
    return {
        str(row[0])
        for row in connection.execute(text("SELECT version_num FROM alembic_version"))
        if row and row[0]
    }


def _unknown_database_revisions(connection) -> set[str]:
    script = _configured_script_directory()
    known = {revision.revision for revision in script.walk_revisions()}
    return _database_revision_rows(connection) - known


def _database_revision_leaf_heads(connection) -> set[str]:
    rows = _database_revision_rows(connection)
    if not rows:
        return set()
    script = _configured_script_directory()
    ancestors: set[str] = set()
    for revision_id in rows:
        revision = script.get_revision(revision_id)
        if not revision:
            continue
        ancestors.update(parent.revision for parent in revision._all_down_revisions)
    return rows - ancestors


def _connected_revision_components(connection) -> list[set[str]]:
    heads = _database_revision_leaf_heads(connection)
    if len(heads) <= 1:
        return [heads] if heads else []
    script = _configured_script_directory()
    head_ancestors: dict[str, set[str]] = {}
    for head in heads:
        revision = script.get_revision(head)
        if revision:
            head_ancestors[head] = {revision.revision, *(ancestor.revision for ancestor in revision._all_down_revisions)}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for left, left_ancestors in head_ancestors.items():
        for right, right_ancestors in head_ancestors.items():
            if left != right and left_ancestors.intersection(right_ancestors):
                adjacency[left].add(right)
    components: list[set[str]] = []
    remaining = set(heads)
    while remaining:
        start = remaining.pop()
        component = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency[current]:
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    component.add(neighbour)
                    frontier.append(neighbour)
        components.append(component)
    return components


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = write_engine

    with connectable.connect() as connection:
        unknown = _unknown_database_revisions(connection)
        if unknown:
            raise RuntimeError(
                "Database references Alembic revision(s) not present in this checkout: "
                f"{sorted(unknown)}. Refusing to guess or stamp over unknown history."
            )
        components = _connected_revision_components(connection)
        if len(components) > 1:
            raise RuntimeError(
                "Database contains disconnected Alembic revision components: "
                f"{[sorted(component) for component in components]}. Repair the overlap before upgrading."
            )
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
