from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"

REQUIRED_CHECKS = {
    "backend_schema_workspace_models": (
        BACKEND_ROOT / "amodb/apps/quality/schemas.py",
        [
            "class QMSAuditWorkspaceSummaryOut",
            "class QMSAuditWorkspaceReadinessOut",
            "class QMSAuditWorkspaceActionOut",
            "class QMSAuditNoticeStateOut",
            "class QMSAuditWorkspaceOut",
            "class QMSAuditWorkflowCheckOut",
            "class QMSAuditNoticeDispatchOut",
        ],
    ),
    "backend_router_workspace_endpoints": (
        BACKEND_ROOT / "amodb/apps/quality/router.py",
        [
            '@router.get("/audits/{audit_id}/workspace"',
            '@router.get("/audits/{audit_id}/workflow-check"',
            '@router.post("/audits/{audit_id}/issue-notice"',
        ],
    ),
    "backend_router_amo_scoping_helpers": (
        BACKEND_ROOT / "amodb/apps/quality/router.py",
        [
            "def _schedule_query_for_amo(",
            "def _car_query_for_amo(",
            "def _get_schedule_for_amo(",
            "def _get_car_for_amo(",
        ],
    ),
    "backend_service_dashboard_scoped": (
        BACKEND_ROOT / "amodb/apps/quality/service.py",
        [
            "def get_dashboard(db: Session, domain: Optional[QMSDomain] = None, amo_id: Optional[str] = None)",
            "if amo_id:\n        a_q = a_q.filter(models.QMSAudit.amo_id == amo_id)",
            "if amo_id:\n            f_q = f_q.filter(models.QMSAudit.amo_id == amo_id)",
        ],
    ),
    "backend_router_reminder_and_stats_scoped": (
        BACKEND_ROOT / "amodb/apps/quality/router.py",
        [
            "amo_id = _current_amo_id(current_user)",
            "if amo_id:\n        audits_q = audits_q.filter(models.QMSAudit.amo_id == amo_id)",
            "def get_auditor_stats(\n    user_id: str,\n    db: Session = Depends(get_db),\n    current_user: account_models.User = Depends(get_current_active_user),\n):",
        ],
    ),
    "frontend_quality_root_redirect": (
        FRONTEND_ROOT / "src/router.tsx",
        [
            'path="/maintenance/:amoCode/quality"',
            "const QualityRootRedirect: React.FC = () => {",
            "return <Navigate to={`/maintenance/${amoCode}/quality/qms${location.search}`} replace />;",
        ],
    ),
    "frontend_qms_overview_target": (
        FRONTEND_ROOT / "src/components/Layout/DepartmentLayout.tsx",
        [
            "QMS Overview",
            "navigateWithSidebarClose(`/maintenance/${amoCode}/${activeDepartment}/qms`)",
        ],
    ),
    "frontend_quality_landing": (
        FRONTEND_ROOT / "src/utils/roleAccess.ts",
        [
            'return `/maintenance/${amoCode}/quality/qms`;',
        ],
    ),
    "frontend_car_deeplink": (
        FRONTEND_ROOT / "src/pages/QualityCarsPage.tsx",
        [
            'pathname: `/maintenance/${amoSlug}/${department}/qms/cars`,',
        ],
    ),
    "frontend_qms_service_orchestration": (
        FRONTEND_ROOT / "src/services/qms.ts",
        [
            "export interface QMSAuditWorkspaceOut {",
            "export interface QMSAuditWorkflowCheckOut {",
            "export interface QMSAuditNoticeDispatchOut {",
            "export async function qmsGetAuditWorkspace(auditId: string)",
            "export async function qmsGetAuditWorkflowCheck(auditId: string)",
            "export async function qmsIssueAuditNotice(",
        ],
    ),
}

COMPILE_TARGETS = [
    BACKEND_ROOT / "amodb/apps/quality/router.py",
    BACKEND_ROOT / "amodb/apps/quality/service.py",
    BACKEND_ROOT / "amodb/apps/quality/schemas.py",
    Path(__file__),
]


def ensure_contains(text: str, needles: Iterable[str]) -> list[str]:
    missing = []
    for needle in needles:
        if needle not in text:
            missing.append(needle)
    return missing


def main() -> int:
    results: dict[str, dict[str, object]] = {}
    ok = True

    for check_name, (path, needles) in REQUIRED_CHECKS.items():
        text = path.read_text(encoding="utf-8")
        missing = ensure_contains(text, needles)
        passed = not missing
        ok = ok and passed
        results[check_name] = {
            "passed": passed,
            "path": str(path.relative_to(ROOT.parent)),
            "missing": missing,
        }

    compile_results = []
    for target in COMPILE_TARGETS:
        try:
            py_compile.compile(str(target), doraise=True)
            compile_results.append({"path": str(target.relative_to(ROOT.parent)), "passed": True})
        except Exception as exc:  # pragma: no cover
            ok = False
            compile_results.append({"path": str(target.relative_to(ROOT.parent)), "passed": False, "error": str(exc)})

    summary = {
        "passed": ok,
        "checks": results,
        "compile": compile_results,
    }
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
