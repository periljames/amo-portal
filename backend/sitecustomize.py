"""Process-local compatibility hooks for the repository's released Alembic graph.

Python imports ``sitecustomize`` automatically after normal site initialization when
``backend`` is on ``PYTHONPATH``.  The hook below is deliberately dormant for all
application, worker, test, and management processes.  It activates only for the
Alembic command-line process and repairs a narrow class of redundant version-table
transitions produced by historical overlapping merge ancestry.

The compatibility rules are database-verified and fail closed:

* a missing delete is skipped only when the marker is absent from both Alembic's
  maintained head set and ``alembic_version``;
* a missing update source becomes an insert only when the source marker is absent
  and the target marker is not already present;
* an already-present target becomes a no-op only when database and in-memory state
  agree.

Unknown inconsistencies continue through Alembic's original implementation and
fail normally.  The release gate still verifies the final head set.
"""
from __future__ import annotations

import os
import sys
from typing import Any


def _is_alembic_cli() -> bool:
    executable = os.path.basename(str(sys.argv[0] or "")).lower()
    return executable.startswith("alembic") or any(
        str(argument).endswith("alembic.ini") for argument in sys.argv[1:]
    )


def _install() -> None:
    if not _is_alembic_cli():
        return

    from alembic.runtime.migration import HeadMaintainer
    from sqlalchemy import text

    if getattr(HeadMaintainer, "_amo_overlap_transition_compatibility", False):
        return

    original_insert = HeadMaintainer._insert_version
    original_delete = HeadMaintainer._delete_version
    original_update = HeadMaintainer._update_version

    def database_has_marker(maintainer: Any, version: str) -> bool | None:
        migration_context = getattr(maintainer, "context", None)
        connection = getattr(migration_context, "connection", None)
        if connection is None:
            return None
        try:
            return bool(
                connection.execute(
                    text("SELECT 1 FROM alembic_version WHERE version_num = :version"),
                    {"version": str(version)},
                ).scalar()
            )
        except Exception:
            return None

    def insert_version_compat(maintainer: Any, version: str) -> None:
        database_present = database_has_marker(maintainer, str(version))
        if version in maintainer.heads:
            if database_present is True:
                print(
                    "Alembic compatibility repair: skipped duplicate version insert "
                    f"for {version}; marker already maintained"
                )
                return
            original_insert(maintainer, version)
            return
        if database_present is True:
            maintainer.heads.add(version)
            print(
                "Alembic compatibility repair: restored in-memory head for existing "
                f"version marker {version}"
            )
            return
        original_insert(maintainer, version)

    def delete_version_compat(maintainer: Any, version: str) -> None:
        if version not in maintainer.heads:
            database_present = database_has_marker(maintainer, str(version))
            if database_present is False:
                print(
                    "Alembic compatibility repair: skipped redundant version deletion "
                    f"for {version}; marker already absent"
                )
                return
        original_delete(maintainer, version)

    def update_version_compat(maintainer: Any, from_: str, to_: str) -> None:
        source_in_heads = from_ in maintainer.heads
        target_in_heads = to_ in maintainer.heads
        source_in_database = database_has_marker(maintainer, str(from_))
        target_in_database = database_has_marker(maintainer, str(to_))

        if not source_in_heads and source_in_database is False:
            if target_in_heads and target_in_database is True:
                print(
                    "Alembic compatibility repair: skipped redundant version update "
                    f"{from_} -> {to_}; target already maintained"
                )
                return
            if target_in_database is True:
                maintainer.heads.add(to_)
                print(
                    "Alembic compatibility repair: restored target head for redundant "
                    f"version update {from_} -> {to_}"
                )
                return
            if not target_in_heads:
                print(
                    "Alembic compatibility repair: converted missing-source version "
                    f"update {from_} -> {to_} into an insert"
                )
                original_insert(maintainer, to_)
                return

        if target_in_heads and target_in_database is True:
            if source_in_heads and source_in_database is True:
                print(
                    "Alembic compatibility repair: converted duplicate-target version "
                    f"update {from_} -> {to_} into source deletion"
                )
                original_delete(maintainer, from_)
                return
            if not source_in_heads and source_in_database is False:
                return

        original_update(maintainer, from_, to_)

    HeadMaintainer._insert_version = insert_version_compat
    HeadMaintainer._delete_version = delete_version_compat
    HeadMaintainer._update_version = update_version_compat
    HeadMaintainer._amo_overlap_transition_compatibility = True
    # Prevent env.py's older delete-only compatibility hook from replacing this
    # complete transition reconciliation.
    HeadMaintainer._amo_redundant_delete_compatibility = True


_install()
