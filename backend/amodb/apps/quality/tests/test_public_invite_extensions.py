from pathlib import Path
from types import SimpleNamespace

from amodb.apps.quality import public_router
from amodb.apps.quality.public_invite_extensions import (
    CARInviteWithAuditReportOut,
    _safe_report_filename,
)


def _get_routes(path: str):
    return [
        route
        for route in public_router.routes
        if str(getattr(route, "path", "")) == path
        and "GET" in (getattr(route, "methods", None) or set())
    ]


def test_public_car_invite_read_route_is_unique_and_enriched():
    routes = _get_routes("/quality/cars/invite/{invite_token}")
    assert len(routes) == 1
    assert getattr(routes[0], "response_model", None) is CARInviteWithAuditReportOut
    assert "audit_report_download_url" in CARInviteWithAuditReportOut.model_fields


def test_public_car_invite_report_download_route_is_registered_once():
    routes = _get_routes("/quality/cars/invite/{invite_token}/audit-report")
    assert len(routes) == 1


def test_public_report_filename_never_exposes_path_or_reference_separators():
    audit = SimpleNamespace(audit_ref="QAR/MO/26/001")
    filename = _safe_report_filename(audit, Path("/generated/quality/audit_reports/uuid_report.pdf"))
    assert filename == "QAR-MO-26-001_issued-audit-report.pdf"
    assert "/" not in filename
    assert "generated" not in filename
