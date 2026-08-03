from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg2
from sqlalchemy.orm import configure_mappers

import amodb.main


REQUIRED_ROUTES = {
    "/reliability/compliance",
    "/reliability/analytics",
    "/reliability/sources",
    "/reliability/calculation-runs/execute",
    "/reliability/programmes",
    "/reliability/changes",
    "/reliability/handoffs",
    "/reliability/authority-submissions",
    "/reliability/ai-reviews",
}

EXACT_PATHS = {
    ".gitignore",
    ".github/workflows/reliability.yml",
    "backend/amodb/alembic/env.py",
    "backend/amodb/main.py",
    "frontend/src/app/PortalRouteSurface.tsx",
    "frontend/src/app/portalRouteManifest.ts",
    "frontend/src/app/portalRouteManifest.test.ts",
    "frontend/src/app/routePreload.ts",
    "frontend/src/portalRoutes.tsx",
    "frontend/src/services/reliability.ts",
    "frontend/src/styles/reliability-v2.css",
    "frontend/src/pages/ReliabilityReportsPage.tsx",
}

PATH_PREFIXES = (
    "backend/amodb/apps/reliability/",
    "backend/amodb/alembic/versions/rel_20260803_",
    "docs/reliability/RELIABILITY_",
    "frontend/src/pages/reliability/",
)

TEMPORARY_DELETIONS = {
    ".github/workflows/reliability-clean-rebuild.yml",
    ".github/workflows/reliability-clean-diagnostic-v2.yml",
    ".github/workflows/reliability-clean-publish-v4.yml",
    ".github/workflows/reliability-clean-publish-v5.yml",
    ".github/workflows/reliability-clean-publish-v6.yml",
    "docs/reliability/.clean-rebuild-trigger",
    "docs/reliability/.clean-diagnostic-v2-trigger",
    "docs/reliability/.clean-publish-v4-trigger",
    "docs/reliability/.clean-publish-v5-trigger",
    "docs/reliability/.clean-publish-v6-trigger",
    "docs/reliability/CLEAN_REBUILD_DIAGNOSTIC.md",
    "backend/scripts/prepare_reliability_clean_tree.py",
    "backend/scripts/validate_reliability_clean.py",
}


def validate_application_and_database() -> None:
    configure_mappers()
    paths = {route.path for route in amodb.main.app.routes}
    missing = sorted(REQUIRED_ROUTES - paths)
    if missing:
        raise RuntimeError(f"Missing Reliability routes: {missing}")
    if any("/reliability/v2" in path for path in paths):
        raise RuntimeError("Parallel Reliability v2 route detected")

    parsed = urlparse(
        os.environ["DATABASE_URL"].replace(
            "postgresql+psycopg2://",
            "postgresql://",
        )
    )
    connection = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )
    cursor = connection.cursor()
    cursor.execute(
        "SELECT count(*) FROM auth_capability_definitions WHERE module='reliability'"
    )
    if cursor.fetchone()[0] != 21:
        raise RuntimeError("Reliability capability seed count is not 21")
    cursor.execute(
        "SELECT count(*) FROM auth_role_definitions WHERE code LIKE 'RELIABILITY_%'"
    )
    if cursor.fetchone()[0] != 4:
        raise RuntimeError("Reliability controlled role count is not four")
    cursor.execute(
        """
        SELECT count(*) FROM pg_trigger
        WHERE tgname IN (
          'trg_reliability_audit_events_append_only',
          'trg_reliability_fracas_evidence_append_only',
          'trg_reliability_fracas_stage_events_append_only',
          'trg_reliability_calculation_runs_append_only'
        ) AND NOT tgisinternal
        """
    )
    if cursor.fetchone()[0] != 4:
        raise RuntimeError("Reliability append-only trigger count is not four")
    cursor.close()
    connection.close()


def validate_staged_paths() -> None:
    status_lines = subprocess.check_output(
        ["git", "diff", "--cached", "--name-status"],
        text=True,
    ).splitlines()
    status_by_path: dict[str, str] = {}
    for line in status_lines:
        parts = line.split("\t")
        if len(parts) >= 2:
            status_by_path[parts[-1]] = parts[0]
    paths = list(status_by_path)
    unapproved = [
        path
        for path in paths
        if path not in EXACT_PATHS
        and path not in TEMPORARY_DELETIONS
        and not path.startswith(PATH_PREFIXES)
    ]
    wrong_temp_status = [
        path
        for path in TEMPORARY_DELETIONS
        if path in status_by_path and status_by_path[path] != "D"
    ]
    artifacts = [
        path
        for path in paths
        if path.startswith(".venv/")
        or "/__pycache__/" in path
        or path.endswith(".pyc")
        or path.endswith(".db")
        or "node_modules/" in path
    ]
    if unapproved or wrong_temp_status or artifacts:
        raise RuntimeError(
            f"Unapproved={unapproved}; "
            f"temporary-not-deleted={wrong_temp_status}; "
            f"artifacts={artifacts}"
        )
    if not paths:
        raise RuntimeError("No permanent Reliability changes are staged")
    print(f"Approved staged paths: {len(paths)}")


if __name__ == "__main__":
    mode = os.getenv("RELIABILITY_CLEAN_VALIDATION_MODE", "application")
    if mode == "application":
        validate_application_and_database()
    elif mode == "paths":
        validate_staged_paths()
    else:
        raise RuntimeError(f"Unsupported validation mode: {mode}")
