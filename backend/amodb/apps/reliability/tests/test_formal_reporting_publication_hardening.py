from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.orm import Session

from amodb.apps.reliability import formal_reporting as core
from amodb.apps.reliability import formal_reporting_publication_hardening as hardening
from amodb.apps.reliability import formal_reporting_render as render
from amodb.apps.reliability import formal_reporting_source_capture as source_capture
from amodb.apps.reliability.formal_reporting_models import FormalReportStatus


def test_publication_hardening_is_active_on_authoritative_paths():
    assert core._freeze_sources is hardening.freeze_sources
    assert core._freeze_report is hardening.freeze_report
    assert core._transition_report is hardening.transition_report
    assert render._render_html is hardening.render_html
    assert event.contains(Session, "before_flush", hardening._invalidate_stale_report_artifacts)


def test_section_changes_invalidate_all_retained_artifact_identity():
    report = SimpleNamespace(
        rendered_html="<html>old</html>",
        html_sha256="a" * 64,
        pdf_storage_ref="/controlled/old.pdf",
        pdf_sha256="b" * 64,
        pdf_size_bytes=1234,
        completeness_json={"passed": True},
    )

    hardening.invalidate_retained_artifacts(report)

    assert report.rendered_html is None
    assert report.html_sha256 is None
    assert report.pdf_storage_ref is None
    assert report.pdf_sha256 is None
    assert report.pdf_size_bytes is None
    assert report.completeness_json == {}


def test_all_render_affecting_section_fields_are_governed_by_freshness_hook():
    assert {
        "status",
        "computed_data",
        "commentary",
        "evidence_refs",
        "warnings",
    } <= hardening.RENDER_AFFECTING_SECTION_FIELDS


def test_configured_history_window_uses_full_profile_horizon(monkeypatch):
    profile = SimpleNamespace(historical_windows=[12, 24, 36])
    report = SimpleNamespace(
        amo_id="amo-1",
        profile_id="profile-1",
        period_end=date(2026, 6, 30),
    )
    monkeypatch.setattr(hardening.core, "_profile", lambda db, amo_id, profile_id: profile)

    start, windows = hardening._configured_history_window(None, report)

    assert windows == [12, 24, 36]
    assert start == date(2023, 7, 1)


class _EmptyQuery:
    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return []


class _FakeDb:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0

    def query(self, *args, **kwargs):
        return _EmptyQuery()

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        self.refreshes += 1


def test_source_freeze_extends_identity_through_history_and_precomputes_snapshot(monkeypatch):
    db = _FakeDb()
    report = SimpleNamespace(
        id="report-1",
        amo_id="amo-1",
        profile_id="profile-1",
        period_end=date(2026, 6, 30),
    )
    workbook_rows = [SimpleNamespace(id="wb-1")]
    event_rows = [SimpleNamespace(id="ev-1"), SimpleNamespace(id="ev-2")]
    captured: list[tuple[str, int]] = []

    monkeypatch.setattr(
        hardening,
        "_previous_freeze_sources",
        lambda db, report, selected: {
            "source_identity_sha256": "old",
            "effective_aircraft_serial_numbers": ["AC-1"],
        },
    )
    monkeypatch.setattr(
        hardening,
        "_configured_history_window",
        lambda db, report: (date(2023, 7, 1), [12, 24, 36]),
    )
    monkeypatch.setattr(hardening, "_historical_workbook_rows", lambda *args, **kwargs: workbook_rows)
    monkeypatch.setattr(hardening, "_historical_event_rows", lambda *args, **kwargs: event_rows)
    monkeypatch.setattr(
        source_capture,
        "_capture_rows",
        lambda db, report, rows, *, source_kind, seen, dataset_code=None: captured.append(
            (source_kind, len(list(rows)))
        ),
    )
    monkeypatch.setattr(
        hardening.history,
        "build_long_term_history",
        lambda db, report: {"series": [{"month": "2023-07-01"}], "max_window_months": 36},
    )
    monkeypatch.setattr(
        hardening,
        "_recompute_source_identity",
        lambda db, report: ("f" * 64, 3, {"RELIABILITY_EVENT": 2, "WORKBOOK_RECORD": 1}),
    )

    population = hardening.freeze_sources(db, report, {"AC-1"})

    assert population["source_identity_sha256"] == "f" * 64
    assert population["historical_window_start"] == "2023-07-01"
    assert population["historical_window_months"] == [12, 24, 36]
    assert population["historical_workbook_record_count"] == 1
    assert population["historical_canonical_event_count"] == 2
    assert population["evidence_scope"] == "CURRENT_COMPARISON_AND_CONFIGURED_HISTORY_INPUTS"
    assert getattr(report, "_formal_frozen_long_term_history")["max_window_months"] == 36
    assert (source_capture.SOURCE_KIND["workbook"], 1) in captured
    assert (source_capture.SOURCE_KIND["events"], 2) in captured


def test_locked_history_snapshot_is_persisted_into_calculation_snapshot(monkeypatch):
    db = _FakeDb()
    frozen_history = {"series": [{"month": "2023-07-01"}], "max_window_months": 36}
    report = SimpleNamespace(
        calculation_snapshots_json={"dashboard": {"summary": []}},
        chart_data_json={},
        _formal_frozen_long_term_history=frozen_history,
    )
    monkeypatch.setattr(hardening, "_previous_freeze_report", lambda db, report, user, payload: report)

    result = hardening.freeze_report(db, report, object(), object())

    assert result.calculation_snapshots_json["long_term_history"] == frozen_history
    assert result.chart_data_json["long_term_history"] == frozen_history["series"]
    assert not hasattr(result, "_formal_frozen_long_term_history")
    assert db.commits == 1
    assert db.refreshes == 1


def _controlled_report(*, report_id: str, revision: int, status: str, supersedes: str | None = None):
    return SimpleNamespace(
        id=report_id,
        revision=revision,
        report_number="REL-2026-H1",
        status=status,
        supersedes_report_id=supersedes,
        published_at=(
            datetime(2026, 7, 10, tzinfo=timezone.utc)
            if status == FormalReportStatus.PUBLISHED.value
            else None
        ),
    )


def test_unlinked_revision_cannot_publish_beside_current_controlled_copy():
    replacement = _controlled_report(
        report_id="replacement",
        revision=1,
        status=FormalReportStatus.APPROVED.value,
    )
    current = _controlled_report(
        report_id="current",
        revision=0,
        status=FormalReportStatus.PUBLISHED.value,
    )

    with pytest.raises(HTTPException) as error:
        hardening._validate_publication_chain(replacement, [current, replacement])

    assert error.value.status_code == 409
    assert "superseding revision" in str(error.value.detail)


def test_linked_revision_must_point_to_current_published_copy():
    replacement = _controlled_report(
        report_id="replacement",
        revision=2,
        status=FormalReportStatus.APPROVED.value,
        supersedes="old-non-current",
    )
    current = _controlled_report(
        report_id="current",
        revision=1,
        status=FormalReportStatus.PUBLISHED.value,
    )

    with pytest.raises(HTTPException) as error:
        hardening._validate_publication_chain(replacement, [current, replacement])

    assert error.value.status_code == 409
    assert "current published revision" in str(error.value.detail)


def test_retained_html_identifies_lifecycle_value_as_render_stage_status(monkeypatch):
    monkeypatch.setattr(
        hardening,
        "_previous_render_html",
        lambda report, sections: "<div><span>Status</span><strong>QUALITY_REVIEW</strong></div>",
    )

    output = hardening.render_html(SimpleNamespace(), [])

    assert "Lifecycle status at render" in output
    assert "<span>Status</span>" not in output
    assert "QUALITY_REVIEW" in output
