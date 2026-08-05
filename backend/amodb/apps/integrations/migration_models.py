"""Removed Phase 4 migration domain.

Aircraft onboarding is owned by ``amodb.apps.aircraft_induction``. These two
symbols remain only so the pre-refactor rollout module can import before the
induction bridge replaces its affected functions. No legacy tables are mapped
or created.
"""

from __future__ import annotations

import enum


class MigrationBatchStatus(str, enum.Enum):
    COMMITTED = "COMMITTED"


class MigrationBatch:
    pass
