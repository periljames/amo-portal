from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = Path("/tmp/reliability-completion-diagnostic")
REPORT = ROOT / "docs/reliability/COMPLETE_SCOPE_DIAGNOSTIC.md"


def run_stage(name: str, command: str, *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> int:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, **(env or {})},
        shell=True,
        executable="/bin/bash",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (LOG_ROOT / f"{name}.log").write_text(completed.stdout or "", encoding="utf-8")
    print(f"{name}={completed.returncode}", flush=True)
    return completed.returncode


def apply_model_defaults() -> None:
    env_path = ROOT / "backend/amodb/alembic/env.py"
    text = env_path.read_text(encoding="utf-8")
    text = text.replace(
        '    table = getattr(obj, "table", None) or getattr(compare_to, "table", None)\n    return table is not None and table.name in _RELIABILITY_TABLES',
        '    table = getattr(obj, "table", None)\n    if table is None:\n        table = getattr(compare_to, "table", None)\n    return table is not None and table.name in _RELIABILITY_TABLES',
    )
    env_path.write_text(text, encoding="utf-8")

    model_path = ROOT / "backend/amodb/apps/reliability/models.py"
    model = model_path.read_text(encoding="utf-8")
    replacements = {
        'validation_status = Column(String(24), nullable=False, default="VALID", index=True)':
            'validation_status = Column(String(24), nullable=False, default="VALID", server_default=text("\'VALID\'"), index=True)',
        'validation_errors = Column(JSON, nullable=False, default=list)':
            'validation_errors = Column(JSON, nullable=False, default=list, server_default=text("\'[]\'"))',
        'provenance_json = Column(JSON, nullable=False, default=dict)':
            'provenance_json = Column(JSON, nullable=False, default=dict, server_default=text("\'{}\'"))',
    }
    for old, new in replacements.items():
        if old not in model:
            raise RuntimeError(f"Missing migration-safe model anchor: {old}")
        model = model.replace(old, new, 1)
    model_path.write_text(model, encoding="utf-8")


def tail(path: Path, lines: int = 100) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def write_report(codes: dict[str, int], ordered: Iterable[str]) -> None:
    run_id = os.getenv("GITHUB_RUN_ID", "local")
    source = os.getenv("GITHUB_SHA", "unknown")
    output = [
        "# Complete Reliability Full-Stack Diagnostic",
        "",
        f"- Run: `{run_id}`",
        f"- Source: `{source}`",
        "",
        "| Stage | Exit code |",
        "|---|---:|",
    ]
    for name in ordered:
        output.append(f"| {name} | {codes.get(name, 999)} |")
    output.extend(["", "## Output tails"])
    for name in ordered:
        output.extend(["", f"### {name}", "```text", tail(LOG_ROOT / f"{name}.log"), "```"])
    REPORT.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> int:
    codes: dict[str, int] = {}
    stages: list[str] = []

    def stage(name: str, command: str, *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
        stages.append(name)
        codes[name] = run_stage(name, command, cwd=cwd, env=env)

    stage("backend_patch", "python backend/scripts/complete_reliability_backend.py")
    stage("sod_patch", "python backend/scripts/strengthen_reliability_sod.py")
    stage("sod_escape", "python backend/scripts/fix_reliability_sod_escape.py")
    try:
        apply_model_defaults()
        codes["model_defaults"] = 0
        (LOG_ROOT / "model_defaults.log").write_text("Applied migration-safe defaults.\n", encoding="utf-8")
    except Exception as exc:
        codes["model_defaults"] = 1
        (LOG_ROOT / "model_defaults.log").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
    stages.append("model_defaults")

    stage("frontend_service", "node scripts/complete-reliability-service.mjs", cwd=ROOT / "frontend")
    stage("frontend_workspace", "node scripts/complete-reliability-workspace.mjs", cwd=ROOT / "frontend")
    stage("frontend_sod", "node scripts/strengthen-reliability-sod.mjs", cwd=ROOT / "frontend")
    stage("frontend_css", "node scripts/complete-reliability-css.mjs", cwd=ROOT / "frontend")
    stage("py_compile", "python -m py_compile backend/amodb/apps/reliability/*.py backend/amodb/apps/reliability/tests/test_complete_scope.py")
    stage("existing_upgrade", "alembic -c amodb/alembic.ini upgrade heads", cwd=ROOT / "backend")
    stage(
        "legacy_probe",
        "psql -h 127.0.0.1 -U postgres -d amo_reliability_diagnostic -v ON_ERROR_STOP=1 "
        "-c \"SET session_replication_role=replica; "
        "INSERT INTO reliability_events (amo_id,event_type,occurred_at,created_at,description) "
        "VALUES ('legacy-reliability-migration-probe','DEFECT',now(),now(),'probe'); "
        "SET session_replication_role=origin;\"",
    )
    stage(
        "migration_generate",
        "mapfile -t HEADS < <(alembic -c amodb/alembic.ini heads | awk '{print $1}'); "
        "if [ ${#HEADS[@]} -gt 1 ]; then "
        "alembic -c amodb/alembic.ini merge --rev-id rel_20260803_merge_heads_diag "
        "-m 'merge heads for Reliability diagnostic' ${HEADS[@]} && alembic -c amodb/alembic.ini upgrade head; fi; "
        "RELIABILITY_AUTOGENERATE_ONLY=true alembic -c amodb/alembic.ini revision --autogenerate "
        "--rev-id rel_20260803_complete_scope -m 'complete Reliability full stack scope' && "
        "python scripts/finalize_reliability_migration.py && "
        "python -m py_compile amodb/alembic/versions/*rel_20260803_complete_scope*.py",
        cwd=ROOT / "backend",
    )
    migration_env = {"RELIABILITY_AUTOGENERATE_ONLY": "true"}
    stage("migration_upgrade", "alembic -c amodb/alembic.ini upgrade head", cwd=ROOT / "backend", env=migration_env)
    stage("migration_check", "alembic -c amodb/alembic.ini check", cwd=ROOT / "backend", env=migration_env)
    stage(
        "legacy_verify",
        "psql -h 127.0.0.1 -U postgres -d amo_reliability_diagnostic -v ON_ERROR_STOP=1 "
        "-c \"SELECT validation_status, validation_errors, provenance_json FROM reliability_events "
        "WHERE amo_id='legacy-reliability-migration-probe';\"",
    )
    stage("migration_downgrade", "alembic -c amodb/alembic.ini downgrade -1", cwd=ROOT / "backend")
    stage("migration_reupgrade", "alembic -c amodb/alembic.ini upgrade head", cwd=ROOT / "backend")
    stage("migration_recheck", "alembic -c amodb/alembic.ini check", cwd=ROOT / "backend", env=migration_env)
    stage(
        "app_import",
        "python -c \"from sqlalchemy.orm import configure_mappers; import amodb.main; "
        "configure_mappers(); print(len(amodb.main.app.routes))\"",
        cwd=ROOT / "backend",
    )
    stage("backend_tests", "pytest -q amodb/apps/reliability/tests", cwd=ROOT / "backend")
    stage(
        "governance",
        "psql -h 127.0.0.1 -U postgres -d amo_reliability_diagnostic -Atc "
        "\"SELECT (SELECT count(*) FROM auth_capability_definitions WHERE module='reliability'), "
        "(SELECT count(*) FROM auth_role_definitions WHERE code LIKE 'RELIABILITY_%'), "
        "(SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_reliability_%_append_only' AND NOT tgisinternal);\"",
    )
    stage("navigation", "npm run test:tenant-shell", cwd=ROOT / "frontend")
    stage(
        "lint",
        "npx eslint src/services/reliability.ts src/pages/reliability/ReliabilityWorkspacePage.tsx "
        "src/pages/reliability/ReliabilityAdvancedViews.tsx src/pages/reliability/ReliabilityReportsView.tsx "
        "src/app/PortalRouteSurface.tsx src/app/portalRouteManifest.ts "
        "src/app/portalRouteManifest.test.ts src/app/routePreload.ts",
        cwd=ROOT / "frontend",
    )
    stage("build", "npm run build", cwd=ROOT / "frontend")

    write_report(codes, stages)
    return 0 if all(code == 0 for code in codes.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
