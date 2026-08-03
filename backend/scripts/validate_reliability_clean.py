from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

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


def validate_application_and_database() -> None:
    configure_mappers()
    paths = {route.path for route in amodb.main.app.routes}
    missing = sorted(REQUIRED_ROUTES - paths)
    if missing:
        raise RuntimeError(f"Missing Reliability routes: {missing}")
    if any("/reliability/v2" in path for path in paths):
        raise RuntimeError("Parallel Reliability v2 route detected")

    parsed = urlparse(os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://"))
    connection = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )
    cursor = connection.cursor()
    cursor.execute("SELECT count(*) FROM auth_capability_definitions WHERE module='reliability'")
    if cursor.fetchone()[0] != 21:
        raise RuntimeError("Reliability capability seed count is not 21")
    cursor.execute("SELECT count(*) FROM auth_role_definitions WHERE code LIKE 'RELIABILITY_%'")
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
    paths = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"],
        text=True,
    ).splitlines()
    unapproved = [
        path
        for path in paths
        if path not in EXACT_PATHS and not path.startswith(PATH_PREFIXES)
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
    if unapproved or artifacts:
        raise RuntimeError(f"Unapproved paths={unapproved}; generated artifacts={artifacts}")
    if not paths:
        raise RuntimeError("No permanent Reliability changes are staged")
    print(f"Approved permanent paths: {len(paths)}")


if __name__ == "__main__":
    mode = os.getenv("RELIABILITY_CLEAN_VALIDATION_MODE", "application")
    if mode == "application":
        validate_application_and_database()
    elif mode == "paths":
        validate_staged_paths()
    else:
        raise RuntimeError(f"Unsupported validation mode: {mode}")
