from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"

REQUIRED_CHECKS = {
    "backend_schema_workflow_models": (
        BACKEND_ROOT / "amodb/apps/quality/schemas.py",
        [
            "class QMSAuditWorkflowStageOut",
            "class QMSAuditWorkflowSummaryOut",
            "class QMSAuditWorkspaceOut",
            "class QMSAuditNoticeDispatchOut",
            "dispatched: bool",
            "message: str",
        ],
    ),
    "backend_router_workspace_endpoints": (
        BACKEND_ROOT / "amodb/apps/quality/router.py",
        [
            '@router.get("/audits/{audit_id}/workspace"',
            '@router.get("/audits/{audit_id}/workflow-check"',
            "return QMSAuditWorkspaceOut(audit=_serialize_audit(audit, db), workflow=workflow)",
            '@router.post("/audits/{audit_id}/issue-notice"',
            '@router.get("/audits/{audit_id}/report"',
            '@router.post("/audits/{audit_id}/report/share"',
            '@router.get("/cars/{car_id}/actions"',
            '@router.post("/cars/{car_id}/actions"',
        ],
    ),
    "backend_router_amo_scoping_helpers": (
        BACKEND_ROOT / "amodb/apps/quality/router.py",
        [
            "def _schedule_query_for_amo(",
            "def _car_query_for_amo(",
            "def _get_schedule_for_amo(",
            "def _get_car_for_amo(",
            "def _get_audit_for_amo(",
            "def _get_finding_for_amo(",
        ],
    ),
    "backend_quality_route_collision_guard": (
        BACKEND_ROOT / "amodb/apps/quality/__init__.py",
        [
            "from .route_ordering import assert_unique_routes",
            'assert_unique_routes(router, label="QMS base API")',
            'assert_unique_routes(public_router, label="QMS public API")',
            "dashboard_v2 as _dashboard_v2",
        ],
    ),
    "backend_service_dashboard_scoped": (
        BACKEND_ROOT / "amodb/apps/quality/service.py",
        [
            "def get_dashboard(db: Session, domain: Optional[QMSDomain] = None, *, amo_id: str)",
            "models.QMSAudit.amo_id == amo_id",
        ],
    ),
    "backend_operational_dashboard_contract": (
        BACKEND_ROOT / "amodb/apps/quality/dashboard_v2.py",
        [
            'DASHBOARD_V2_CONTRACT = "qms-operational-dashboard.v2"',
            '@canonical_router.get("/dashboard-v2")',
            '"action_queue": action_queue',
            '"my_work": my_work',
            '"upcoming_obligations": upcoming',
            '"performance_kpis": kpis',
            '"aging_buckets":',
            '"unassigned_counts":',
            '"severity_breakdown":',
            '"period_comparisons":',
            '"data_freshness":',
            '"source_health":',
        ],
    ),
    "backend_operational_dashboard_tests": (
        BACKEND_ROOT / "amodb/apps/quality/tests/test_dashboard_v2_contract.py",
        [
            "test_operational_dashboard_route_is_registered",
            "test_action_queue_is_ranked_and_bounded",
            "test_action_queue_omits_zero_count_items",
        ],
    ),
    "backend_schema_integrity_migration": (
        BACKEND_ROOT / "amodb/alembic/versions/quality_20260722_schema_integrity.py",
        [
            'revision = "quality_20260722_schema_integrity"',
            'down_revision = "workforce_20260721_complete"',
            "def _foreign_key_exists(",
            "def _unique_columns_exist(",
            "pk_quality_car_responses",
            "fk_quality_car_responses_car",
            "pk_quality_car_attachments",
            "fk_quality_car_attachments_car",
            "pk_quality_finding_attachments",
            "fk_quality_finding_attachments_finding",
            "pk_quality_corrective_actions",
            "fk_quality_corrective_actions_finding",
            "uq_quality_corrective_actions_finding",
        ],
    ),
    "backend_postgres_integrity_probe": (
        BACKEND_ROOT / "amodb/apps/quality/tests/postgres_schema_integrity_probe.py",
        [
            'TARGET_REVISION = "quality_20260722_schema_integrity"',
            "_create_runtime_fallback_baseline",
            "_assert_foreign_key_rejects_orphan",
            "Orphaned CAR response insertion unexpectedly succeeded",
        ],
    ),
    "backend_quality_delivery_profile": (
        BACKEND_ROOT / "amodb/quality_main.py",
        [
            'PROFILE_NAME: Final = "quality"',
            "PROFILE_MODULES:",
            "OMITTED_OPERATIONAL_MODULES:",
            "def _enforce_schema_head_sync()",
            'app.include_router(quality_router)',
            'app.include_router(canonical_quality_router)',
            'app.include_router(training_router)',
            'app.include_router(audit_events_router)',
            'app.include_router(notifications_router)',
            'app.include_router(tasks_router)',
            'app.include_router(doc_control_router)',
        ],
    ),
    "backend_quality_delivery_profile_tests": (
        BACKEND_ROOT / "amodb/apps/quality/tests/test_quality_delivery_profile.py",
        [
            "test_quality_delivery_profile_exposes_required_route_families",
            "test_quality_delivery_profile_omits_unrelated_operational_routes",
            "test_quality_direct_router_has_no_exact_duplicate_registrations",
            "test_quality_delivery_manifest_is_explicit",
        ],
    ),
    "backend_quality_container_profile": (
        ROOT / "backend/Dockerfile",
        [
            "ASGI_APP=amodb.main:app",
            'exec uvicorn \\"${ASGI_APP}\\"',
            '${PORT:-8080}',
        ],
    ),
    "frontend_qms_route_registry": (
        FRONTEND_ROOT / "src/pages/qms/routes/qmsRouteRegistry.ts",
        [
            "export const QMS_ROUTE_REGISTRY",
            "export function qmsBasePath(",
            "export function qmsModulePath(",
            "export function qmsNavigationItems(",
            "export function classifyQmsPath(",
            'kind: "unknown"',
            "validViews",
            "componentType",
        ],
    ),
    "frontend_qms_router_ownership": (
        FRONTEND_ROOT / "src/router.tsx",
        [
            'import { classifyQmsPath, type QmsPathClassification }',
            "function isQmsRegisterWorkspace(",
            'qmsRoute.kind === "overview"',
            'qmsRoute.kind === "unknown"',
            "<QmsNotFoundPage />",
            "<QmsRegisterPage />",
        ],
    ),
    "frontend_qms_route_regressions": (
        FRONTEND_ROOT / "src/pages/qms/routes/qmsRouteRegistry.test.ts",
        [
            'describe("QMS route registry"',
            "does not silently accept misspelled modules or views",
            "rejects removed aliases and pre-stage audit occurrence URLs",
        ],
    ),
    "frontend_qms_operational_overview": (
        FRONTEND_ROOT / "src/pages/qms/QmsOverviewPage.tsx",
        [
            "getQmsOperationalDashboard",
            "<QmsActionQueue",
            "<QmsMyWork",
            "<QmsUpcomingObligations",
            "<QmsPerformanceSummary",
            "<QmsDiagnosticsDrawer",
        ],
    ),
    "frontend_qms_compact_register": (
        FRONTEND_ROOT / "src/pages/qms/QmsRegisterPage.tsx",
        [
            "Generic quick creation is disabled",
            "Module navigation remains in the sidebar",
            "qms-register-table",
            "Support diagnostics",
        ],
    ),
    "frontend_qms_dashboard_service": (
        FRONTEND_ROOT / "src/services/qmsDashboard.ts",
        [
            'qmsPath(amoCode, "/dashboard-lite")',
            'qmsPath(amoCode, "/dashboard-v2")',
            "getQmsOperationalDashboard",
        ],
    ),
    "frontend_qms_dashboard_service_tests": (
        FRONTEND_ROOT / "src/services/qmsDashboard.test.ts",
        [
            "keeps the bounded legacy counter endpoint",
            "loads the server-ranked operational dashboard contract",
        ],
    ),
    "frontend_active_audit_workflow_contract": (
        FRONTEND_ROOT / "src/services/qms.ts",
        [
            "export interface QMSAuditWorkflowStageOut {",
            "export interface QMSAuditWorkflowSummaryOut {",
            "export interface QMSAuditWorkflowOut {",
            "audit: QMSAuditOut;",
            "workflow: QMSAuditWorkflowSummaryOut;",
            "export async function qmsGetAuditWorkflow(auditId: string",
            "Promise<QMSAuditWorkflowOut>",
            "export async function qmsIssueAuditNotice(",
        ],
    ),
    "frontend_hub_action_service": (
        FRONTEND_ROOT / "src/services/qmsAuditHubActions.ts",
        [
            "async function hubRequest<T>(",
            "globalThis.clearTimeout(timeout)",
            "Quality API request timed out after",
            "readApiError",
            "export async function qmsAddCarAction",
            "export async function qmsShareAuditReport",
        ],
    ),
    "frontend_hub_action_regressions": (
        FRONTEND_ROOT / "src/services/qmsAuditHubActions.test.ts",
        [
            'describe("Quality audit hub API helpers"',
            "surfaces backend validation detail",
            "returns a deterministic timeout error",
        ],
    ),
    "quality_ci_workflow": (
        ROOT / ".github/workflows/quality-module-ci.yml",
        [
            "name: Quality Module CI",
            "python -m amodb.scripts.quality_module_internal_check",
            "test_dashboard_v2_contract.py",
            "npm run test:quality",
            "npm run build",
        ],
    ),
}

FORBIDDEN_CHECKS = {
    "frontend_hub_service_browser_timer_dependency": (
        FRONTEND_ROOT / "src/services/qmsAuditHubActions.ts",
        ["window.setTimeout", "window.clearTimeout"],
    ),
    "backend_quality_profile_operational_routers": (
        BACKEND_ROOT / "amodb/quality_main.py",
        [
            "fleet_router",
            "work_router",
            "crs_router",
            "reliability_router",
            "inventory_router",
            "finance_router",
            "rostering_router",
            "workforce_router",
        ],
    ),
}

FORBIDDEN_FILES = [
    FRONTEND_ROOT / "src/layouts/QmsShell.tsx",
    FRONTEND_ROOT / "src/pages/QMSHomePage.tsx",
    FRONTEND_ROOT / "src/components/dashboard/QualityCockpitCanvas.tsx",
    FRONTEND_ROOT / "src/components/dashboard/charts/QualityCockpitCharts.tsx",
    FRONTEND_ROOT / "src/dashboards/DashboardCockpit.tsx",
]

COMPILE_TARGETS = [
    BACKEND_ROOT / "amodb/quality_main.py",
    BACKEND_ROOT / "amodb/apps/quality/__init__.py",
    BACKEND_ROOT / "amodb/apps/quality/router.py",
    BACKEND_ROOT / "amodb/apps/quality/service.py",
    BACKEND_ROOT / "amodb/apps/quality/schemas.py",
    BACKEND_ROOT / "amodb/apps/quality/dashboard_v2.py",
    BACKEND_ROOT / "amodb/alembic/versions/quality_20260722_schema_integrity.py",
    BACKEND_ROOT / "amodb/apps/quality/tests/postgres_schema_integrity_probe.py",
    BACKEND_ROOT / "amodb/apps/quality/tests/test_quality_delivery_profile.py",
    BACKEND_ROOT / "amodb/apps/quality/tests/test_dashboard_v2_contract.py",
    Path(__file__),
]


def ensure_contains(text: str, needles: Iterable[str]) -> list[str]:
    return [needle for needle in needles if needle not in text]


def ensure_absent(text: str, needles: Iterable[str]) -> list[str]:
    return [needle for needle in needles if needle in text]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT.parent))
    except ValueError:
        return str(path)


def main() -> int:
    results: dict[str, dict[str, object]] = {}
    ok = True

    for check_name, (path, needles) in REQUIRED_CHECKS.items():
        if not path.exists():
            ok = False
            results[check_name] = {
                "passed": False,
                "path": _display_path(path),
                "missing": list(needles),
                "reason": "Required Quality contract file is missing.",
            }
            continue
        text = path.read_text(encoding="utf-8")
        missing = ensure_contains(text, needles)
        passed = not missing
        ok = ok and passed
        results[check_name] = {
            "passed": passed,
            "path": _display_path(path),
            "missing": missing,
        }

    for check_name, (path, needles) in FORBIDDEN_CHECKS.items():
        if not path.exists():
            ok = False
            results[check_name] = {
                "passed": False,
                "path": _display_path(path),
                "present": [],
                "reason": "File required for forbidden-pattern validation is missing.",
            }
            continue
        text = path.read_text(encoding="utf-8")
        present = ensure_absent(text, needles)
        passed = not present
        ok = ok and passed
        results[check_name] = {
            "passed": passed,
            "path": _display_path(path),
            "present": present,
        }

    retired = []
    for path in FORBIDDEN_FILES:
        exists = path.exists()
        retired.append({"path": _display_path(path), "passed": not exists})
        ok = ok and not exists
    results["frontend_retired_qms_surfaces"] = {
        "passed": all(item["passed"] for item in retired),
        "files": retired,
    }

    package_json = FRONTEND_ROOT / "package.json"
    package_result: dict[str, object]
    if package_json.exists():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
            quality_command = str(payload.get("scripts", {}).get("test:quality") or "")
            required_tests = [
                "qmsAuditHubActions.test.ts",
                "qmsDashboard.test.ts",
                "qmsOverviewModel.test.ts",
                "qmsRouteRegistry.test.ts",
            ]
            missing_tests = [name for name in required_tests if name not in quality_command]
            passed = not missing_tests
            ok = ok and passed
            package_result = {
                "passed": passed,
                "path": _display_path(package_json),
                "command": quality_command,
                "missing_tests": missing_tests,
            }
        except Exception as exc:
            ok = False
            package_result = {
                "passed": False,
                "path": _display_path(package_json),
                "error": str(exc),
            }
    else:
        ok = False
        package_result = {
            "passed": False,
            "path": _display_path(package_json),
            "error": "frontend/package.json is missing",
        }
    results["frontend_quality_test_script"] = package_result

    compile_results = []
    for target in COMPILE_TARGETS:
        try:
            py_compile.compile(str(target), doraise=True)
            compile_results.append({"path": _display_path(target), "passed": True})
        except Exception as exc:  # pragma: no cover
            ok = False
            compile_results.append({"path": _display_path(target), "passed": False, "error": str(exc)})

    summary = {
        "passed": ok,
        "checks": results,
        "compile": compile_results,
    }
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
