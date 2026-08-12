from __future__ import annotations

import hashlib
import io
from pathlib import Path

from openpyxl import load_workbook

from amodb.apps.platform.saas_secrets import encrypt_secret
from amodb.apps.rostering import calendar_subscriptions, controlled_exports, roster_control
from amodb.apps.rostering.application_router import router
from amodb.apps.rostering.code_registry_models import (
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)
from amodb.apps.rostering.roster_control_models import (
    RosterAssignmentLineage,
    RosterCalendarSubscription,
    RosterControlledDocumentSettings,
    RosterPublicationSnapshot,
    RosterShiftAlias,
)


def _routes():
    return [
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    ]


def _snapshot(status: str = "DRAFT") -> dict:
    return {
        "schema_version": 1,
        "legacy_reconstructed": False,
        "amo_id": "amo-1",
        "version_id": "version-1",
        "version_no": 3,
        "status": status,
        "period": {
            "id": "period-1",
            "code": "AUG-26",
            "name": "August 2026",
            "starts_on": "2026-08-01",
            "ends_on": "2026-08-31",
            "timezone_name": "Africa/Nairobi",
        },
        "document": {
            "form_number": "SL/MCM/27",
            "revision_label": "0",
            "revision_date": "2026-05-29",
            "footer_note": "All stated shift times include the applicable unpaid break shown in the legend.",
            "prepared_by_label": "Prepared by",
            "approved_by_label": "Approved by",
            "page_size": "A3",
            "prepared_by": "Planner",
            "prepared_date": "2026-07-28",
            "approved_by": "Head of Quality",
            "approved_date": "2026-07-31",
            "published_by": "Head of Quality" if status == "PUBLISHED" else None,
            "published_at": "2026-07-31T10:00:00+03:00" if status == "PUBLISHED" else None,
        },
        "legend": [
            {
                "code": "F1",
                "label": "Flight Duty - Early",
                "default_start_time": "06:00",
                "default_end_time": "15:00",
                "unpaid_break_minutes": 60,
                "duty_semantic": "DUTY",
                "verification_status": "CONFIRMED",
                "description": "Early Flight Engineering coverage.",
            },
            {
                "code": "RD",
                "label": "Rest Day",
                "default_start_time": None,
                "default_end_time": None,
                "unpaid_break_minutes": 0,
                "duty_semantic": "REST",
                "verification_status": "CONFIRMED",
                "description": "Protected rostered rest day.",
            },
        ],
        "rows": [
            {
                "assignment_id": "a-1",
                "calendar_lineage": "lineage-flight-engineer-1",
                "staff_code": "FE001",
                "full_name": "Flight Engineer One",
                "department_code": "ENG",
                "base_code": "JKIA",
                "shift_code": "F1",
                "status": "DUTY",
                "starts_at": "2026-08-01T06:00:00+03:00",
                "ends_at": "2026-08-01T15:00:00+03:00",
                "planned_minutes": 540,
                "role_label": "Flight Engineer",
                "team_code": None,
                "location_label": "JKIA",
                "aircraft_registrations": "5Y-SLC",
                "aircraft_display_codes": "SLC",
            },
            {
                "assignment_id": "a-2",
                "calendar_lineage": "lineage-flight-engineer-1",
                "staff_code": "FE001",
                "full_name": "Flight Engineer One",
                "department_code": "ENG",
                "base_code": "JKIA",
                "shift_code": "RD",
                "status": "OFF",
                "starts_at": "2026-08-02T00:00:00+03:00",
                "ends_at": "2026-08-03T00:00:00+03:00",
                "planned_minutes": 0,
                "role_label": None,
                "team_code": None,
                "location_label": "JKIA",
                "aircraft_registrations": "",
                "aircraft_display_codes": "",
            },
        ],
    }


def test_control_tables_and_registry_governance_are_distinct():
    policy_columns = set(RosterShiftTemplatePolicy.__table__.columns.keys())
    assert {"duty_semantic", "verification_status", "unpaid_break_minutes", "calendar_mode"}.issubset(policy_columns)
    assert RosterDutySemantic.REST.value == "REST"
    assert RosterCodeVerificationStatus.CONFIRMED.value == "CONFIRMED"

    assert {"alias", "shift_template_id", "context_label", "aircraft_registration"}.issubset(RosterShiftAlias.__table__.columns.keys())
    assert {"form_number", "revision_label", "revision_date", "footer_note", "page_size"}.issubset(RosterControlledDocumentSettings.__table__.columns.keys())
    assert {"version_id", "snapshot_json", "snapshot_hash"}.issubset(RosterPublicationSnapshot.__table__.columns.keys())
    assert {"assignment_id", "source_assignment_id", "lineage_key"}.issubset(RosterAssignmentLineage.__table__.columns.keys())


def test_calendar_subscription_stores_hash_and_encrypted_bearer_not_plaintext(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    raw = "test-roster-calendar-token-123"
    encrypted, _ = encrypt_secret({"token": raw})
    row = RosterCalendarSubscription(
        amo_id="amo-1",
        user_id="user-1",
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        token_encrypted=encrypted,
    )
    assert row.token_hash != raw
    assert row.token_encrypted != raw
    assert calendar_subscriptions.raw_token(row) == raw


def test_controlled_roster_routes_and_revocable_calendar_routes_are_mounted_once():
    routes = _routes()
    required = {
        ("GET", "/rostering/shift-templates/aliases"),
        ("POST", "/rostering/shift-templates/{template_id}/aliases"),
        ("DELETE", "/rostering/shift-templates/aliases/{alias_id}"),
        ("GET", "/rostering/controlled-document/settings"),
        ("PATCH", "/rostering/controlled-document/settings"),
        ("GET", "/rostering/versions/{version_id}/controlled-roster.pdf"),
        ("GET", "/rostering/versions/{version_id}/controlled-roster.xlsx"),
        ("GET", "/rostering/calendar/subscription"),
        ("POST", "/rostering/calendar/subscription"),
        ("POST", "/rostering/calendar/subscription/rotate"),
        ("DELETE", "/rostering/calendar/subscription"),
        ("GET", "/rostering/calendar/feed/{token}.ics"),
    }
    assert required.issubset(set(routes))
    assert routes.count(("GET", "/rostering/calendar/subscription")) == 1
    assert routes.count(("GET", "/rostering/calendar/feed/{token}.ics")) == 1


def test_controlled_xlsx_is_monthly_matrix_with_document_control_and_aircraft_badge():
    payload = controlled_exports.controlled_roster_xlsx(_snapshot("DRAFT"))
    workbook = load_workbook(io.BytesIO(payload), data_only=False)
    sheet = workbook["Controlled Roster"]
    assert sheet["A1"].value == "Duty Roster — August 2026"
    assert "SL/MCM/27" in str(sheet["A2"].value)
    assert "Roster v3" in str(sheet["A2"].value)
    assert "DRAFT — NOT A CONTROLLED PUBLISHED ROSTER" in str(sheet["A4"].value)
    assert sheet["E5"].value == "Sat"
    assert sheet["E6"].value == 1
    assert sheet["E7"].value == "F1\nSLC"
    assert sheet["F7"].value == "RD"
    assert workbook["Assignment Detail"]["M2"].value == "lineage-flight-engineer-1"


def test_controlled_pdf_renders_a_real_pdf_and_draft_watermark_contract():
    payload = controlled_exports.controlled_roster_pdf(_snapshot("DRAFT"))
    assert payload.startswith(b"%PDF")
    assert len(payload) > 1500


def test_stable_report_ics_uses_lineage_instead_of_transient_assignment_id():
    content = roster_control._stable_assignment_ics(_snapshot("PUBLISHED")["rows"], calendar_name="August 2026")
    assert "UID:roster:lineage-flight-engineer-1@amo-portal" in content
    assert "UID:a-1@amo-portal" not in content
    assert "5Y-SLC" in content


def test_publication_policy_installs_registry_gate_snapshot_and_stable_ics_contract():
    source = Path(roster_control.__file__).read_text(encoding="utf-8")
    assert "assert_registry_ready(db, version=version)" in source
    assert "capture_publication_snapshot(db, version=row, actor_user_id=actor_user_id)" in source
    assert "calendar_lineage" in source
    assert "exports.assignment_ics = _stable_assignment_ics" in source
