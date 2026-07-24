from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"

REQUIRED_CHECKS = {
    "backend_quality_route_deduplication": (
        BACKEND_ROOT / "amodb/apps/quality/__init__.py",
        [
            "def _deduplicate_exact_routes(",
            "audit_lifecycle_models",
            "audit_lifecycle as _audit_lifecycle",
            "audit_lifecycle_queries",
            "_deduplicate_exact_routes(router)",
            "_deduplicate_exact_routes(public_router)",
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
    "backend_lifecycle_models": (
        BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle_models.py",
        [
            "class QualityAuditChecklistDocument",
            "class QualityAuditReportDocument",
            "class QualityAuditStageRecord",
            "class QualityAuditEvidenceReview",
            "WORKING_DRAFT",
            "SUPERSEDED",
            "RETAINED",
            "PENDING','ACCEPTED','REJECTED",
        ],
    ),
    "backend_lifecycle_schemas": (
        BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle_schemas.py",
        [
            "AuditStageState = Literal",
            "class QualityAuditWorkflowV2Out",
            "class QualityAuditWarRoomContextOut",
            "class QualityAuditChecklistMetadataOut",
            "class QualityAuditReportMetadataOut",
            "class QualityAuditPreviousAuditOut",
            "class QualityAuditEvidenceReviewIn",
        ],
    ),
    "backend_authoritative_lifecycle": (
        BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle.py",
        [
            'STAGE_ORDER = ("war-room", "checklist", "findings", "cars", "evidence", "report", "closeout")',
            "def build_workflow_v2(",
            "Uploading a blank source document does not",
            "Evidence completion is based on explicit acceptance",
            '@_extension_router.get("/audits/{audit_id}/war-room-context"',
            '@_extension_router.post("/audits/{audit_id}/documents/checklist/draft"',
            '@_extension_router.post("/audits/{audit_id}/documents/checklist/commit"',
            '@_extension_router.post("/audits/{audit_id}/lifecycle/checklist/complete"',
            '@_extension_router.post("/audits/{audit_id}/lifecycle/fieldwork/complete"',
            '@_extension_router.post("/audits/{audit_id}/documents/report/issue"',
            '@_extension_router.post("/audits/{audit_id}/lifecycle/closeout"',
            "_previous_audits",
            "storage_key",
        ],
    ),
    "backend_lifecycle_queries": (
        BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle_queries.py",
        [
            '@_extension_router.get(\n    "/audits/{audit_id}/evidence/reviews"',
            '"/audits/{audit_id}/documents/report/distribution"',
            "update_report_distribution",
        ],
    ),
    "backend_lifecycle_migration": (
        BACKEND_ROOT / "amodb/alembic/versions/quality_20260724_audit_lifecycle.py",
        [
            'revision = "quality_20260724_audit_lifecycle"',
            "quality_audit_checklist_documents",
            "quality_audit_report_documents",
            "quality_audit_stage_records",
            "quality_audit_evidence_reviews",
            "ix_qms_audits_amo_scope_actual_end",
            "ix_qms_audits_amo_auditee_actual_end",
            "ix_qms_audits_amo_status_actual_end",
        ],
    ),
    "backend_lifecycle_tests": (
        BACKEND_ROOT / "amodb/apps/quality/tests/test_audit_lifecycle_v2.py",
        [
            "test_planned_future_audit_never_inherits_false_completion_from_files",
            "test_navigation_has_no_lifecycle_side_effect",
            "test_checklist_source_is_readiness_not_completion",
            "test_evidence_requires_explicit_acceptance",
            "test_document_dto_never_exposes_storage_key",
            "test_retained_checklist_versions_are_distinct",
            "test_previous_audit_intelligence_requires_comparable_issued_report",
        ],
    ),
    "backend_schema_integrity_migration": (
        BACKEND_ROOT / "amodb/alembic/versions/quality_20260722_schema_integrity.py",
        [
            'revision = "quality_20260722_schema_integrity"',
            "pk_quality_car_responses",
            "fk_quality_car_responses_car",
            "pk_quality_car_attachments",
            "fk_quality_car_attachments_car",
            "pk_quality_finding_attachments",
            "fk_quality_finding_attachments_finding",
        ],
    ),
    "backend_quality_delivery_profile": (
        BACKEND_ROOT / "amodb/quality_main.py",
        [
            'PROFILE_NAME: Final = "quality"',
            "def _enforce_schema_head_sync()",
            "app.include_router(quality_router)",
            "app.include_router(training_router)",
            "app.include_router(audit_events_router)",
        ],
    ),
    "frontend_lifecycle_service": (
        FRONTEND_ROOT / "src/services/qmsAuditLifecycle.ts",
        [
            "export type QualityAuditStageState",
            "export interface QualityAuditWarRoomContext",
            "qmsGetAuditWarRoomContext",
            "qmsStartAuditLifecycle",
            "qmsCompleteAuditChecklist",
            "qmsCompleteAuditFieldwork",
            "qmsUploadChecklistSource",
            "qmsSaveChecklistDraft",
            "qmsCommitChecklistVersion",
            "qmsIssueReportVersion",
            "qmsReviewAuditEvidence",
            "qmsCloseAuditLifecycle",
        ],
    ),
    "frontend_lifecycle_queries": (
        FRONTEND_ROOT / "src/services/qmsAuditLifecycleQueries.ts",
        [
            "qmsListAuditEvidenceReviews",
            "qmsRecordReportDistribution",
            "qmsOpenAuthenticatedQualityPath",
            "qmsOpenLifecycleDocument",
        ],
    ),
    "frontend_integrated_pdf_editor": (
        FRONTEND_ROOT / "src/components/QMS/QualityChecklistPdfEditor.tsx",
        [
            "renderForms",
            "getFieldObjects",
            "saveDocument",
            "qmsSaveChecklistDraft",
            "qmsCommitChecklistVersion",
            "The controlled source remains retained",
        ],
    ),
    "frontend_auditor_workbench": (
        FRONTEND_ROOT / "src/pages/QualityAuditRunHubPage.tsx",
        [
            "qmsGetAuditWarRoomContext",
            "Previous audit intelligence",
            "View previous report",
            "Auditor action queue",
            "Mark checklist complete",
            "Complete fieldwork",
            "Evidence completion",
            "Issue controlled report",
            "Approve and close audit",
            "workflow!.stages.map",
        ],
    ),
    "frontend_auditor_workbench_styles": (
        FRONTEND_ROOT / "src/pages/qualityAudits/quality-audit-workbench-v2.css",
        [
            "grid-template-columns: minmax(250px, 276px) minmax(0, 1fr)",
            ".qa2-stepper",
            ".qa2-command-strip",
            ".qa2-pdf-shell",
            "height: min(94dvh, 1080px)",
            "@media (max-width: 640px)",
        ],
    ),
    "frontend_no_floating_pdf_launcher": (
        FRONTEND_ROOT / "src/components/QMS/QualityEnhancementsHost.tsx",
        [
            "Fillable PDF controls now live inside the Checklist toolbar",
            "WorkflowIntegrityGuard",
            "qms-audit-lifecycle",
        ],
    ),
    "reference_contract": (
        BACKEND_ROOT / "docs/quality/QUALITY_AUDIT_WAR_ROOM_CHECKLIST_LIFECYCLE_20260724.md",
        [
            "source of truth",
            "Previous audit intelligence",
            "Uploading a blank source document does not complete",
            "Saving a filled PDF creates a new retained version",
            "No API response may expose a local filesystem path",
            "Acceptance criteria",
        ],
    ),
    "quality_ci_workflow": (
        ROOT / ".github/workflows/quality-module-ci.yml",
        [
            "name: Quality Module CI",
            "python -m amodb.scripts.quality_module_internal_check",
            "npm run test:quality",
            "npm run build",
        ],
    ),
}

FORBIDDEN_CHECKS = {
    "frontend_page_no_navigation_completion_heuristic": (
        FRONTEND_ROOT / "src/pages/QualityAuditRunHubPage.tsx",
        [
            "index < currentTabIndex",
            "buildFallbackWorkflow",
            "Commit overwrite",
            "checklist_file_ref ? \"Uploaded\"",
        ],
    ),
    "frontend_page_no_raw_storage_path_render": (
        FRONTEND_ROOT / "src/pages/QualityAuditRunHubPage.tsx",
        ["checklist_file_ref", "report_file_ref", "D:\\\\XLK-Assets"],
    ),
    "frontend_enhancements_no_floating_editor": (
        FRONTEND_ROOT / "src/components/QMS/QualityEnhancementsHost.tsx",
        ["QualityChecklistPdfFormEditorHost", "route.activeTab === \"checklist\""],
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

COMPILE_TARGETS = [
    BACKEND_ROOT / "amodb/quality_main.py",
    BACKEND_ROOT / "amodb/apps/quality/__init__.py",
    BACKEND_ROOT / "amodb/apps/quality/router.py",
    BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle_models.py",
    BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle_schemas.py",
    BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle.py",
    BACKEND_ROOT / "amodb/apps/quality/audit_lifecycle_queries.py",
    BACKEND_ROOT / "amodb/alembic/versions/quality_20260724_audit_lifecycle.py",
    BACKEND_ROOT / "amodb/apps/quality/tests/test_audit_lifecycle_v2.py",
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
        results[check_name] = {"passed": passed, "path": _display_path(path), "missing": missing}

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
        results[check_name] = {"passed": passed, "path": _display_path(path), "present": present}

    package_json = FRONTEND_ROOT / "package.json"
    if package_json.exists():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
            quality_command = str(payload.get("scripts", {}).get("test:quality") or "")
            required_tests = ["qmsAuditHubActions.test.ts", "qmsAuditLifecycle.test.ts"]
            passed = all(test_name in quality_command for test_name in required_tests)
            ok = ok and passed
            results["frontend_quality_test_script"] = {
                "passed": passed,
                "path": _display_path(package_json),
                "command": quality_command,
                "required": required_tests,
            }
        except Exception as exc:
            ok = False
            results["frontend_quality_test_script"] = {"passed": False, "path": _display_path(package_json), "error": str(exc)}
    else:
        ok = False
        results["frontend_quality_test_script"] = {"passed": False, "path": _display_path(package_json), "error": "frontend/package.json is missing"}

    compile_results = []
    for target in COMPILE_TARGETS:
        try:
            py_compile.compile(str(target), doraise=True)
            compile_results.append({"path": _display_path(target), "passed": True})
        except Exception as exc:  # pragma: no cover
            ok = False
            compile_results.append({"path": _display_path(target), "passed": False, "error": str(exc)})

    summary = {"passed": ok, "checks": results, "compile": compile_results}
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
