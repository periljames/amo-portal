from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

from . import formal_reporting as core
from . import formal_reporting_history as history
from . import formal_reporting_render as render
from . import formal_reporting_source_capture as source_capture
from .formal_reporting_models import (
    FormalReportStatus,
    ReliabilityFormalReport,
    ReliabilityFormalReportSection,
    ReliabilityFormalReportSource,
)


RENDER_AFFECTING_SECTION_FIELDS = frozenset(
    {
        "section_code",
        "sequence",
        "title",
        "required",
        "status",
        "computed_data",
        "commentary",
        "evidence_refs",
        "warnings",
    }
)


_previous_freeze_sources = None
_previous_freeze_report = None
_previous_transition_report = None
_previous_render_html = None
_applied = False


def invalidate_retained_artifacts(report: ReliabilityFormalReport) -> None:
    """Make a changed review payload require a fresh controlled render.

    Formal section content is part of the retained HTML/PDF artifact. Any change
    to that content invalidates the artifact identities and the last completeness
    result. Publication therefore cannot pass until a new render regenerates the
    artifacts and hashes from the changed section state.
    """

    report.rendered_html = None
    report.html_sha256 = None
    report.pdf_storage_ref = None
    report.pdf_sha256 = None
    report.pdf_size_bytes = None
    report.completeness_json = {}


def _section_render_state_changed(section: ReliabilityFormalReportSection) -> bool:
    state = sa_inspect(section)
    return any(
        state.attrs[field].history.has_changes()
        for field in RENDER_AFFECTING_SECTION_FIELDS
    )


def _invalidate_stale_report_artifacts(
    session: Session,
    flush_context: Any,
    instances: Any,
) -> None:
    """Invalidate retained artifacts whenever render-affecting section data changes."""

    del flush_context, instances
    for obj in tuple(session.dirty):
        if not isinstance(obj, ReliabilityFormalReportSection):
            continue
        if not _section_render_state_changed(obj):
            continue
        report = obj.report
        if report is None:
            report = session.get(ReliabilityFormalReport, obj.report_id)
        if report is not None:
            invalidate_retained_artifacts(report)


def _configured_history_window(db: Session, report: ReliabilityFormalReport) -> tuple[date, list[int]]:
    profile = core._profile(db, report.amo_id, report.profile_id)
    configured = sorted(
        {
            int(item)
            for item in (profile.historical_windows or [12])
            if int(item) > 0
        }
    )
    windows = [item for item in configured if item <= history.MAX_HISTORY_MONTHS]
    if not windows:
        windows = [12]
    return history.history_start(report.period_end, max(windows)), windows


def _historical_workbook_rows(
    db: Session,
    report: ReliabilityFormalReport,
    *,
    historical_start: date,
    effective_aircraft: set[str],
):
    cutoff = core._source_cutoff(report)
    query = db.query(source_capture.wp.ReliabilityWorkbookRecord).filter(
        source_capture.wp.ReliabilityWorkbookRecord.amo_id == report.amo_id,
        source_capture.wp.ReliabilityWorkbookRecord.event_date >= historical_start,
        source_capture.wp.ReliabilityWorkbookRecord.event_date <= report.period_end,
        source_capture.wp.ReliabilityWorkbookRecord.created_at <= cutoff,
        source_capture.wp.ReliabilityWorkbookRecord.status.in_(["APPROVED", "CLOSED"]),
    )
    if effective_aircraft:
        query = query.filter(
            source_capture.wp.ReliabilityWorkbookRecord.aircraft_serial_number.in_(
                sorted(effective_aircraft)
            )
        )
    return source_capture._bounded_query(
        query.order_by(
            source_capture.wp.ReliabilityWorkbookRecord.event_date,
            source_capture.wp.ReliabilityWorkbookRecord.id,
        ),
        "workbook historical",
    )


def _historical_event_rows(
    db: Session,
    report: ReliabilityFormalReport,
    *,
    historical_start: date,
    effective_aircraft: set[str],
):
    cutoff = core._source_cutoff(report)
    event_model = source_capture.models.ReliabilityEvent
    query = db.query(event_model).filter(
        event_model.amo_id == report.amo_id,
        event_model.occurred_at >= source_capture._start(historical_start),
        event_model.occurred_at <= source_capture._end(report.period_end),
        event_model.created_at <= cutoff,
        event_model.validation_status == "VALID",
    )
    if effective_aircraft:
        query = query.filter(event_model.aircraft_serial_number.in_(sorted(effective_aircraft)))
    return source_capture._bounded_query(
        query.order_by(event_model.occurred_at, event_model.id),
        "canonical event historical",
    )


def _recompute_source_identity(
    db: Session,
    report: ReliabilityFormalReport,
) -> tuple[str, int, dict[str, int]]:
    identity_rows = db.query(
        ReliabilityFormalReportSource.source_kind,
        ReliabilityFormalReportSource.source_id,
        ReliabilityFormalReportSource.source_hash,
    ).filter(
        ReliabilityFormalReportSource.report_id == report.id,
        ReliabilityFormalReportSource.amo_id == report.amo_id,
    ).all()
    identities = [
        f"{row.source_kind}:{row.source_id}:{row.source_hash or ''}"
        for row in identity_rows
    ]
    population_hash = hashlib.sha256(
        "\n".join(sorted(identities)).encode("utf-8")
    ).hexdigest()

    family_counts: dict[str, int] = {}
    for row in identity_rows:
        family_counts[row.source_kind] = family_counts.get(row.source_kind, 0) + 1
    return population_hash, len(identity_rows), dict(sorted(family_counts.items()))


def freeze_sources(
    db: Session,
    report: ReliabilityFormalReport,
    selected_aircraft: set[str],
) -> dict[str, Any]:
    """Extend the governed source freeze through the full configured history window."""

    if _previous_freeze_sources is None:  # pragma: no cover - defensive import guard
        raise RuntimeError("Formal publication hardening has not been applied.")

    population = _previous_freeze_sources(db, report, selected_aircraft)
    effective_aircraft = {
        str(item)
        for item in population.get("effective_aircraft_serial_numbers", [])
        if str(item).strip()
    }
    historical_start, windows = _configured_history_window(db, report)

    existing = db.query(ReliabilityFormalReportSource).filter(
        ReliabilityFormalReportSource.report_id == report.id,
        ReliabilityFormalReportSource.amo_id == report.amo_id,
    ).all()
    seen = {(row.source_kind, row.source_id) for row in existing}

    workbook_rows = _historical_workbook_rows(
        db,
        report,
        historical_start=historical_start,
        effective_aircraft=effective_aircraft,
    )
    source_capture._capture_rows(
        db,
        report,
        workbook_rows,
        source_kind=source_capture.SOURCE_KIND["workbook"],
        seen=seen,
    )

    event_rows = _historical_event_rows(
        db,
        report,
        historical_start=historical_start,
        effective_aircraft=effective_aircraft,
    )
    source_capture._capture_rows(
        db,
        report,
        event_rows,
        source_kind=source_capture.SOURCE_KIND["events"],
        seen=seen,
        dataset_code="EVENT",
    )
    db.flush()

    # Build the long-term calculation while the snapshot guard still holds SHARE
    # locks on authoritative Reliability tables. This prevents a later render
    # from consulting mutable live history after the controlled cutoff.
    frozen_history = history.build_long_term_history(db, report)
    report._formal_frozen_long_term_history = frozen_history

    population_hash, source_count, family_counts = _recompute_source_identity(db, report)
    return {
        **population,
        "source_identity_sha256": population_hash,
        "source_record_count": source_count,
        "source_family_counts": family_counts,
        "historical_window_start": historical_start.isoformat(),
        "historical_window_months": windows,
        "historical_workbook_record_count": len(workbook_rows),
        "historical_canonical_event_count": len(event_rows),
        "evidence_scope": "CURRENT_COMPARISON_AND_CONFIGURED_HISTORY_INPUTS",
    }


def freeze_report(db: Session, report, user, payload):
    """Persist the long-term calculation captured inside the locked freeze transaction."""

    if _previous_freeze_report is None:  # pragma: no cover - defensive import guard
        raise RuntimeError("Formal publication hardening has not been applied.")
    frozen = _previous_freeze_report(db, report, user, payload)
    frozen_history = getattr(frozen, "_formal_frozen_long_term_history", None)
    if frozen_history is None:
        return frozen

    calculations = dict(frozen.calculation_snapshots_json or {})
    calculations["long_term_history"] = frozen_history
    frozen.calculation_snapshots_json = calculations
    charts = dict(frozen.chart_data_json or {})
    charts["long_term_history"] = frozen_history.get("series", [])
    frozen.chart_data_json = charts
    delattr(frozen, "_formal_frozen_long_term_history")
    db.commit()
    db.refresh(frozen)
    return frozen


def _validate_publication_chain(
    replacement: ReliabilityFormalReport,
    chain: Iterable[ReliabilityFormalReport],
) -> None:
    current = [
        row
        for row in chain
        if row.id != replacement.id
        and row.status == FormalReportStatus.PUBLISHED.value
        and row.published_at is not None
    ]
    if current and not replacement.supersedes_report_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "A published revision already exists for this controlled report number. "
                "Create a linked superseding revision before publication."
            ),
        )
    if replacement.supersedes_report_id and current:
        matching = [row for row in current if row.id == replacement.supersedes_report_id]
        if not matching:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The declared superseded revision is not the current published revision "
                    "for this controlled report number."
                ),
            )


def transition_report(db: Session, report, user, payload):
    """Serialize publication by controlled report number before lifecycle mutation."""

    if _previous_transition_report is None:  # pragma: no cover - defensive import guard
        raise RuntimeError("Formal publication hardening has not been applied.")
    if payload.to_status.value == FormalReportStatus.PUBLISHED.value:
        chain = (
            db.query(ReliabilityFormalReport)
            .filter(
                ReliabilityFormalReport.amo_id == report.amo_id,
                ReliabilityFormalReport.report_number == report.report_number,
            )
            .order_by(ReliabilityFormalReport.revision.asc(), ReliabilityFormalReport.id.asc())
            .with_for_update()
            .all()
        )
        _validate_publication_chain(report, chain)
    return _previous_transition_report(db, report, user, payload)


def render_html(report, sections) -> str:
    """Label the retained lifecycle value as the immutable render-stage status."""

    if _previous_render_html is None:  # pragma: no cover - defensive import guard
        raise RuntimeError("Formal publication hardening has not been applied.")
    output = _previous_render_html(report, sections)
    return output.replace(
        "<span>Status</span><strong>",
        "<span>Lifecycle status at render</span><strong>",
        1,
    )


def apply() -> None:
    global _previous_freeze_sources
    global _previous_freeze_report
    global _previous_transition_report
    global _previous_render_html
    global _applied

    if _applied:
        return

    _previous_freeze_sources = core._freeze_sources
    _previous_freeze_report = core._freeze_report
    _previous_transition_report = core._transition_report
    _previous_render_html = render._render_html

    core._freeze_sources = freeze_sources
    core._freeze_report = freeze_report
    core._transition_report = transition_report
    render._render_html = render_html

    if not event.contains(Session, "before_flush", _invalidate_stale_report_artifacts):
        event.listen(Session, "before_flush", _invalidate_stale_report_artifacts)

    _applied = True
