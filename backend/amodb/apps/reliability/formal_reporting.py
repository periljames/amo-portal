from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from . import models as reliability_models
from . import workbook_parity as wp
from .analytics_builder import build_dashboard
from .formal_reporting_models import (
    FormalPeriodType,
    FormalReportStatus,
    FormalSectionStatus,
    RegulatoryObligation,
    RegulatoryProfileStatus,
    RequirementAssessmentStatus,
    ReliabilityFormalApproval,
    ReliabilityFormalCompletenessOverride,
    ReliabilityFormalLifecycleEvent,
    ReliabilityFormalReport,
    ReliabilityFormalReportSection,
    ReliabilityFormalReportSource,
    ReliabilityFormalRequirementAssessment,
    ReliabilityRegulatoryProfile,
    ReliabilityRegulatoryRequirement,
)
from .formal_reporting_profiles import (
    ANALYSIS_ROLES,
    APPROVAL_ROLES,
    COMMON_APPROVAL_WORKFLOW,
    COMMON_PUBLICATION_RULES,
    FORMAL_SECTIONS,
    PROFILE_ADMIN_ROLES,
    PROFILE_VERSION,
    QUALITY_REVIEW_ROLES,
    TECHNICAL_REVIEW_ROLES,
    profile_definitions,
)

UTC = timezone.utc
MAX_SOURCE_ROWS = 100_000
TERMINAL_STATUSES = {
    FormalReportStatus.PUBLISHED.value,
    FormalReportStatus.SUPERSEDED.value,
    FormalReportStatus.WITHDRAWN.value,
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    FormalReportStatus.DRAFT.value: {FormalReportStatus.DATA_REVIEW.value},
    FormalReportStatus.DATA_REVIEW.value: {
        FormalReportStatus.DRAFT.value,
        FormalReportStatus.TECHNICAL_REVIEW.value,
    },
    FormalReportStatus.TECHNICAL_REVIEW.value: {
        FormalReportStatus.DATA_REVIEW.value,
        FormalReportStatus.QUALITY_REVIEW.value,
    },
    FormalReportStatus.QUALITY_REVIEW.value: {
        FormalReportStatus.TECHNICAL_REVIEW.value,
        FormalReportStatus.APPROVAL_PENDING.value,
    },
    FormalReportStatus.APPROVAL_PENDING.value: {
        FormalReportStatus.QUALITY_REVIEW.value,
        FormalReportStatus.APPROVED.value,
    },
    FormalReportStatus.APPROVED.value: {
        FormalReportStatus.QUALITY_REVIEW.value,
        FormalReportStatus.PUBLISHED.value,
    },
    FormalReportStatus.PUBLISHED.value: {
        FormalReportStatus.SUPERSEDED.value,
        FormalReportStatus.WITHDRAWN.value,
    },
    FormalReportStatus.SUPERSEDED.value: set(),
    FormalReportStatus.WITHDRAWN.value: set(),
}


class FormalReportCreate(BaseModel):
    profile_id: str
    programme_id: str | None = None
    report_number: str = Field(min_length=2, max_length=100)
    revision: int = Field(default=0, ge=0)
    title: str = Field(min_length=2, max_length=255)
    period_type: FormalPeriodType
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Period end must be on or after period start.")
        if (self.period_end - self.period_start).days > 731:
            raise ValueError(
                "A formal report period is limited to 732 days. "
                "Long-term trend windows are retained separately by bounded aggregation."
            )
        return self


class FormalFreezeRequest(BaseModel):
    aircraft_serial_numbers: list[str] = Field(default_factory=list, max_length=1000)
    aircraft_types: list[str] = Field(default_factory=list, max_length=100)
    effectivity: dict[str, Any] = Field(default_factory=dict)


class FormalSectionUpdate(BaseModel):
    status: Literal["DRAFT", "READY", "WITHHELD", "NOT_APPLICABLE"] = "DRAFT"
    commentary: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RequirementAssessmentUpdate(BaseModel):
    applicable: bool = True
    status: RequirementAssessmentStatus
    reviewer_note: str | None = Field(default=None, max_length=4000)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    calculation_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.status == RequirementAssessmentStatus.SATISFIED:
            if not (self.reviewer_note and self.reviewer_note.strip()):
                raise ValueError("A SATISFIED requirement requires a reviewer note.")
            if not (self.evidence_refs or self.calculation_refs or self.source_refs):
                raise ValueError("A SATISFIED requirement requires retained evidence.")
        if self.status == RequirementAssessmentStatus.NOT_APPLICABLE:
            if self.applicable:
                raise ValueError("NOT_APPLICABLE requires applicable=false.")
            if not (self.reviewer_note and self.reviewer_note.strip()):
                raise ValueError("A NOT_APPLICABLE decision requires a rationale.")
        return self


class TransitionRequest(BaseModel):
    to_status: FormalReportStatus
    comment: str | None = Field(default=None, max_length=4000)


class CompletenessOverrideCreate(BaseModel):
    check_code: str = Field(min_length=2, max_length=120)
    requirement_id: str | None = None
    justification: str = Field(min_length=10, max_length=8000)
    authority_basis: str = Field(min_length=5, max_length=8000)


def _role(user: account_models.User) -> str:
    return str(getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))).upper()


def _amo_id(user: account_models.User) -> str:
    amo_id = user.effective_amo_id
    if not amo_id:
        raise HTTPException(status_code=403, detail="A tenant context is required.")
    return str(amo_id)


def _is_privileged(user: account_models.User, allowed: set[str]) -> bool:
    return bool(getattr(user, "is_superuser", False)) or bool(getattr(user, "is_amo_admin", False)) or _role(user) in allowed


def _require_role(user: account_models.User, allowed: set[str], message: str) -> None:
    if not _is_privileged(user, allowed):
        raise HTTPException(status_code=403, detail=message)


def _require_human(user: account_models.User) -> None:
    if bool(getattr(user, "is_system_account", False)):
        raise HTTPException(status_code=403, detail="System/AI accounts cannot review, approve or publish formal Reliability reports.")


def _profile(db: Session, amo_id: str, profile_id: str) -> ReliabilityRegulatoryProfile:
    row = db.query(ReliabilityRegulatoryProfile).filter(
        ReliabilityRegulatoryProfile.id == profile_id,
        ReliabilityRegulatoryProfile.amo_id == amo_id,
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Reliability regulatory profile not found.")
    return row


def _report(db: Session, amo_id: str, report_id: str) -> ReliabilityFormalReport:
    row = db.query(ReliabilityFormalReport).filter(
        ReliabilityFormalReport.id == report_id,
        ReliabilityFormalReport.amo_id == amo_id,
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Formal Reliability report not found.")
    return row


def _require_editable(report: ReliabilityFormalReport) -> None:
    if report.status in TERMINAL_STATUSES or report.published_at is not None:
        raise HTTPException(status_code=409, detail="Published, superseded or withdrawn report evidence is immutable.")


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _profile_dict(row: ReliabilityRegulatoryProfile) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "version": row.version,
        "name": row.name,
        "authority": row.authority,
        "jurisdiction": row.jurisdiction,
        "effective_date": row.effective_date,
        "revision": row.revision,
        "status": row.status,
        "required_sections": row.required_sections,
        "mandatory_kpis": row.mandatory_kpis,
        "historical_windows": row.historical_windows,
        "approval_workflow": row.approval_workflow,
        "publication_rules": row.publication_rules,
        "source_manifest": row.source_manifest,
    }


def _requirement_snapshot(row: ReliabilityRegulatoryRequirement) -> dict[str, Any]:
    return {
        "id": row.id,
        "requirement_key": row.requirement_key,
        "authority": row.authority,
        "jurisdiction": row.jurisdiction,
        "source_kind": row.source_kind,
        "source_reference": row.source_reference,
        "paragraph_reference": row.paragraph_reference,
        "source_url": row.source_url,
        "effective_date": _json(row.effective_date),
        "revision": row.revision,
        "controlled_summary": row.controlled_summary,
        "applicability_rule": row.applicability_rule,
        "aircraft_applicability": row.aircraft_applicability,
        "operator_applicability": row.operator_applicability,
        "obligation_status": row.obligation_status,
        "report_section_code": row.report_section_code,
        "data_source_codes": row.data_source_codes,
        "calculation_code": row.calculation_code,
        "minimum_analysis_months": row.minimum_analysis_months,
        "historical_comparison_months": row.historical_comparison_months,
        "evidence_rule": row.evidence_rule,
        "approval_role": row.approval_role,
        "completeness_rule": row.completeness_rule,
        "lifecycle_status": row.lifecycle_status,
    }


def ensure_baseline_profiles(db: Session, amo_id: str, actor_user_id: str | None) -> list[ReliabilityRegulatoryProfile]:
    created = False
    for definition in profile_definitions():
        profile = db.query(ReliabilityRegulatoryProfile).filter(
            ReliabilityRegulatoryProfile.amo_id == amo_id,
            ReliabilityRegulatoryProfile.code == definition["code"],
            ReliabilityRegulatoryProfile.version == PROFILE_VERSION,
        ).one_or_none()
        if profile:
            continue
        profile = ReliabilityRegulatoryProfile(
            amo_id=amo_id,
            code=definition["code"],
            version=PROFILE_VERSION,
            name=definition["name"],
            authority=definition["authority"],
            jurisdiction=definition["jurisdiction"],
            effective_date=definition.get("effective_date"),
            revision=definition.get("revision"),
            status=RegulatoryProfileStatus.ACTIVE.value,
            required_sections=definition["required_sections"],
            mandatory_kpis=definition["mandatory_kpis"],
            minimum_analysis_periods=definition["minimum_analysis_periods"],
            statistical_methods=definition["statistical_methods"],
            historical_windows=definition["historical_windows"],
            commentary_rules={"engineering_commentary_traceable": True},
            evidence_rules={"no_unsupported_narrative": True, "withheld_requires_reason": True},
            approval_workflow=COMMON_APPROVAL_WORKFLOW,
            publication_rules=COMMON_PUBLICATION_RULES,
            source_manifest=definition["source_manifest"],
            created_by_user_id=actor_user_id,
        )
        db.add(profile)
        db.flush()
        for item in definition["requirements"]:
            db.add(ReliabilityRegulatoryRequirement(
                amo_id=amo_id,
                profile_id=profile.id,
                requirement_key=item["requirement_key"],
                authority=item["authority"],
                jurisdiction=item["jurisdiction"],
                source_kind=item["source_kind"],
                source_reference=item["source_reference"],
                paragraph_reference=item.get("paragraph_reference"),
                source_url=item["source_url"],
                effective_date=item.get("effective_date"),
                revision=item["revision"],
                controlled_summary=item["controlled_summary"],
                applicability_rule=item["applicability_rule"],
                aircraft_applicability={},
                operator_applicability={},
                obligation_status=item["obligation_status"],
                report_section_code=item["report_section_code"],
                data_source_codes=item["data_source_codes"],
                calculation_code=item.get("calculation_code"),
                minimum_analysis_months=item.get("minimum_analysis_months"),
                historical_comparison_months=item.get("historical_comparison_months"),
                evidence_rule=item["evidence_rule"],
                approval_role=item.get("approval_role"),
                completeness_rule=item["completeness_rule"],
                reviewer_notes=item.get("reviewer_notes"),
                created_by_user_id=actor_user_id,
            ))
        created = True
    if created:
        db.commit()
    return db.query(ReliabilityRegulatoryProfile).filter(
        ReliabilityRegulatoryProfile.amo_id == amo_id,
        ReliabilityRegulatoryProfile.status == RegulatoryProfileStatus.ACTIVE.value,
    ).order_by(ReliabilityRegulatoryProfile.code, ReliabilityRegulatoryProfile.version).all()


def _event_hash(
    report: ReliabilityFormalReport,
    *,
    from_status: str | None,
    to_status: str,
    action: str,
    actor_user_id: str | None,
    role_snapshot: str,
    previous_hash: str | None,
    rationale: str | None,
    payload: dict[str, Any] | None = None,
) -> str:
    body = {
        "report_id": report.id,
        "revision": report.revision,
        "from_status": from_status,
        "to_status": to_status,
        "action": action,
        "actor_user_id": actor_user_id,
        "role": role_snapshot,
        "previous_hash": previous_hash,
        "rationale": rationale,
        "payload": payload or {},
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _append_lifecycle(
    db: Session,
    report: ReliabilityFormalReport,
    *,
    from_status: str | None,
    to_status: str,
    action: str,
    actor: account_models.User,
    rationale: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    previous = db.query(ReliabilityFormalLifecycleEvent).filter(
        ReliabilityFormalLifecycleEvent.report_id == report.id,
        ReliabilityFormalLifecycleEvent.amo_id == report.amo_id,
    ).order_by(ReliabilityFormalLifecycleEvent.created_at.desc()).first()
    previous_hash = previous.event_hash if previous else None
    role_snapshot = _role(actor)
    db.add(ReliabilityFormalLifecycleEvent(
        amo_id=report.amo_id,
        report_id=report.id,
        from_status=from_status,
        to_status=to_status,
        action=action,
        rationale=rationale,
        payload_json=payload or {},
        previous_hash=previous_hash,
        event_hash=_event_hash(
            report,
            from_status=from_status,
            to_status=to_status,
            action=action,
            actor_user_id=actor.id,
            role_snapshot=role_snapshot,
            previous_hash=previous_hash,
            rationale=rationale,
            payload=payload,
        ),
        actor_user_id=actor.id,
        role_snapshot=role_snapshot,
    ))


def _report_dict(db: Session, row: ReliabilityFormalReport, *, detail: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": row.id,
        "report_number": row.report_number,
        "revision": row.revision,
        "title": row.title,
        "period_type": row.period_type,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "status": row.status,
        "profile_id": row.profile_id,
        "profile_code": row.profile_code_snapshot,
        "profile_version": row.profile_version_snapshot,
        "data_cutoff_at": row.data_cutoff_at,
        "effectivity": row.effectivity_json,
        "effectivity_frozen_at": row.effectivity_frozen_at,
        "html_sha256": row.html_sha256,
        "pdf_sha256": row.pdf_sha256,
        "published_at": row.published_at,
        "supersedes_report_id": row.supersedes_report_id,
        "created_at": row.created_at,
    }
    if detail:
        sections = db.query(ReliabilityFormalReportSection).filter(
            ReliabilityFormalReportSection.report_id == row.id,
            ReliabilityFormalReportSection.amo_id == row.amo_id,
        ).order_by(ReliabilityFormalReportSection.sequence).all()
        assessments = db.query(ReliabilityFormalRequirementAssessment).filter(
            ReliabilityFormalRequirementAssessment.report_id == row.id,
            ReliabilityFormalRequirementAssessment.amo_id == row.amo_id,
        ).all()
        result.update({
            "regulatory_manifest": row.regulatory_manifest,
            "source_population": row.source_population_json,
            "formula_revisions": row.formula_revisions_json,
            "data_quality": row.data_quality_json,
            "completeness": row.completeness_json,
            "sections": [{
                "id": s.id,
                "code": s.section_code,
                "sequence": s.sequence,
                "title": s.title,
                "required": s.required,
                "status": s.status,
                "computed_data": s.computed_data,
                "commentary": s.commentary,
                "evidence_refs": s.evidence_refs,
                "warnings": s.warnings,
            } for s in sections],
            "requirements": [{
                "id": a.id,
                "requirement_id": a.requirement_id,
                "section_code": a.section_code,
                "applicable": a.applicable,
                "status": a.status,
                "requirement": a.requirement_snapshot,
                "evidence_refs": a.evidence_refs,
                "calculation_refs": a.calculation_refs,
                "source_refs": a.source_refs,
                "reviewer_note": a.reviewer_note,
            } for a in assessments],
        })
    return result


def _create_formal_report(
    db: Session,
    amo_id: str,
    user: account_models.User,
    payload: FormalReportCreate,
) -> ReliabilityFormalReport:
    profile = _profile(db, amo_id, payload.profile_id)
    if profile.status != RegulatoryProfileStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="Only an ACTIVE regulatory profile can be used.")
    duplicate = db.query(ReliabilityFormalReport.id).filter(
        ReliabilityFormalReport.amo_id == amo_id,
        ReliabilityFormalReport.report_number == payload.report_number,
        ReliabilityFormalReport.revision == payload.revision,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="This formal report number/revision already exists.")
    requirements = db.query(ReliabilityRegulatoryRequirement).filter(
        ReliabilityRegulatoryRequirement.amo_id == amo_id,
        ReliabilityRegulatoryRequirement.profile_id == profile.id,
        ReliabilityRegulatoryRequirement.lifecycle_status == "ACTIVE",
    ).order_by(ReliabilityRegulatoryRequirement.requirement_key).all()
    report = ReliabilityFormalReport(
        amo_id=amo_id,
        programme_id=payload.programme_id,
        profile_id=profile.id,
        report_number=payload.report_number.strip(),
        revision=payload.revision,
        title=payload.title.strip(),
        period_type=payload.period_type.value,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=FormalReportStatus.DRAFT.value,
        profile_code_snapshot=profile.code,
        profile_version_snapshot=profile.version,
        regulatory_manifest=[_requirement_snapshot(item) for item in requirements],
        created_by_user_id=user.id,
    )
    db.add(report)
    db.flush()
    configured_sections = profile.required_sections or FORMAL_SECTIONS
    for sequence, section in enumerate(configured_sections, start=1):
        db.add(ReliabilityFormalReportSection(
            amo_id=amo_id,
            report_id=report.id,
            section_code=section["code"],
            sequence=sequence,
            title=section["title"],
            required=bool(section.get("required", True)),
            status=FormalSectionStatus.DRAFT.value,
        ))
    for requirement in requirements:
        default_status = str((requirement.evidence_rule or {}).get("default_status") or "")
        if default_status not in {item.value for item in RequirementAssessmentStatus}:
            default_status = (
                RequirementAssessmentStatus.GAP.value
                if requirement.obligation_status == RegulatoryObligation.MANDATORY.value
                else RequirementAssessmentStatus.WITHHELD.value
            )
        db.add(ReliabilityFormalRequirementAssessment(
            amo_id=amo_id,
            report_id=report.id,
            requirement_id=requirement.id,
            section_code=requirement.report_section_code,
            applicable=bool((requirement.applicability_rule or {}).get("default_applicable", True)),
            status=default_status,
            requirement_snapshot=_requirement_snapshot(requirement),
        ))
    _append_lifecycle(
        db,
        report,
        from_status=None,
        to_status=FormalReportStatus.DRAFT.value,
        action="CREATE",
        actor=user,
        payload={"profile_id": profile.id, "profile_version": profile.version},
    )
    db.commit()
    db.refresh(report)
    return report


def _source_cutoff(report: ReliabilityFormalReport) -> datetime:
    if not report.data_cutoff_at:
        raise HTTPException(status_code=409, detail="The report data cutoff has not been frozen.")
    cutoff = report.data_cutoff_at
    return cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)


def _period_start_dt(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _period_end_dt(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)


def _freeze_sources(
    db: Session,
    report: ReliabilityFormalReport,
    selected_aircraft: set[str],
) -> dict[str, Any]:
    cutoff = _source_cutoff(report)
    workbook_query = db.query(wp.ReliabilityWorkbookRecord).filter(
        wp.ReliabilityWorkbookRecord.amo_id == report.amo_id,
        wp.ReliabilityWorkbookRecord.event_date >= report.period_start,
        wp.ReliabilityWorkbookRecord.event_date <= report.period_end,
        wp.ReliabilityWorkbookRecord.created_at <= cutoff,
        wp.ReliabilityWorkbookRecord.status.in_(["APPROVED", "CLOSED"]),
    )
    if selected_aircraft:
        workbook_query = workbook_query.filter(
            wp.ReliabilityWorkbookRecord.aircraft_serial_number.in_(sorted(selected_aircraft))
        )
    workbook_rows = workbook_query.order_by(
        wp.ReliabilityWorkbookRecord.event_date, wp.ReliabilityWorkbookRecord.id
    ).limit(MAX_SOURCE_ROWS + 1).all()
    if len(workbook_rows) > MAX_SOURCE_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"Controlled workbook population exceeds the {MAX_SOURCE_ROWS:,}-row formal freeze limit.",
        )

    event_query = db.query(reliability_models.ReliabilityEvent).filter(
        reliability_models.ReliabilityEvent.amo_id == report.amo_id,
        reliability_models.ReliabilityEvent.occurred_at >= _period_start_dt(report.period_start),
        reliability_models.ReliabilityEvent.occurred_at <= _period_end_dt(report.period_end),
        reliability_models.ReliabilityEvent.created_at <= cutoff,
        reliability_models.ReliabilityEvent.validation_status == "VALID",
    )
    if selected_aircraft:
        event_query = event_query.filter(
            reliability_models.ReliabilityEvent.aircraft_serial_number.in_(sorted(selected_aircraft))
        )
    event_rows = event_query.order_by(
        reliability_models.ReliabilityEvent.occurred_at, reliability_models.ReliabilityEvent.id
    ).limit(MAX_SOURCE_ROWS + 1).all()
    if len(event_rows) > MAX_SOURCE_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"Canonical event population exceeds the {MAX_SOURCE_ROWS:,}-row formal freeze limit.",
        )

    db.query(ReliabilityFormalReportSource).filter(
        ReliabilityFormalReportSource.report_id == report.id,
        ReliabilityFormalReportSource.amo_id == report.amo_id,
    ).delete(synchronize_session=False)
    identities: list[str] = []
    by_domain: dict[str, int] = {}
    for row in workbook_rows:
        identity = f"WORKBOOK:{row.id}:{row.revision}:{row.source_hash or ''}"
        identities.append(identity)
        by_domain[row.dataset_code] = by_domain.get(row.dataset_code, 0) + 1
        db.add(ReliabilityFormalReportSource(
            amo_id=report.amo_id,
            report_id=report.id,
            source_kind="WORKBOOK_RECORD",
            source_id=str(row.id),
            source_hash=row.source_hash,
            source_date=row.event_date,
            dataset_code=row.dataset_code,
            aircraft_serial_number=row.aircraft_serial_number,
            reference_code=row.reference_code or row.record_number,
        ))
    for row in event_rows:
        identity = f"EVENT:{row.id}:{row.source_payload_hash or ''}"
        identities.append(identity)
        db.add(ReliabilityFormalReportSource(
            amo_id=report.amo_id,
            report_id=report.id,
            source_kind="RELIABILITY_EVENT",
            source_id=str(row.id),
            source_hash=row.source_payload_hash,
            source_date=row.occurred_at.date() if row.occurred_at else None,
            aircraft_serial_number=row.aircraft_serial_number,
            reference_code=row.reference_code,
        ))
    population_hash = hashlib.sha256("\n".join(sorted(identities)).encode("utf-8")).hexdigest()
    return {
        "workbook_record_count": len(workbook_rows),
        "canonical_event_count": len(event_rows),
        "workbook_by_domain": dict(sorted(by_domain.items())),
        "source_identity_sha256": population_hash,
        "cutoff_at": cutoff.isoformat(),
        "bounded": True,
        "row_limit_per_source_family": MAX_SOURCE_ROWS,
    }


def _freeze_report(
    db: Session,
    report: ReliabilityFormalReport,
    user: account_models.User,
    payload: FormalFreezeRequest,
) -> ReliabilityFormalReport:
    _require_editable(report)
    if report.status not in {FormalReportStatus.DRAFT.value, FormalReportStatus.DATA_REVIEW.value}:
        raise HTTPException(status_code=409, detail="Report freeze is only available during draft/data review.")
    if report.effectivity_frozen_at or report.data_cutoff_at:
        raise HTTPException(status_code=409, detail="Report effectivity/data cutoff is already frozen.")

    now = datetime.now(UTC)
    selected_aircraft = {item.strip() for item in payload.aircraft_serial_numbers if item.strip()}
    report.data_cutoff_at = now
    report.effectivity_frozen_at = now
    report.effectivity_json = {
        **payload.effectivity,
        "aircraft_serial_numbers": sorted(selected_aircraft),
        "aircraft_types": sorted({item.strip() for item in payload.aircraft_types if item.strip()}),
        "scope": "SELECTED_AIRCRAFT" if selected_aircraft else "TENANT_FLEET",
        "frozen_at": now.isoformat(),
    }
    source_population = _freeze_sources(db, report, selected_aircraft)

    dashboard = build_dashboard(
        db,
        amo_id=report.amo_id,
        period_start=report.period_start,
        period_end=report.period_end,
        bucket_requested="AUTO",
        aircraft=sorted(selected_aircraft),
        aircraft_types=payload.aircraft_types,
        ata_chapters=[],
        stations=[],
        event_types=[],
        severities=[],
        source_systems=[],
    )
    dashboard_data = dashboard.model_dump(mode="json")
    formula_manifest = [{
        "code": item.code,
        "version": item.version,
        "origin": item.origin,
        "methodology": item.methodology,
        "denominator_policy": item.denominator_policy,
        "source_fields": item.source_fields,
    } for item in dashboard.formulae]
    report.source_population_json = source_population
    report.formula_revisions_json = formula_manifest
    report.calculation_snapshots_json = {"dashboard": dashboard_data}
    report.chart_data_json = {
        key: dashboard_data.get(key, [])
        for key in (
            "time_series", "event_mix", "ata_pareto", "aircraft_performance",
            "station_delay", "route_delay", "component_reliability",
            "component_removal_age", "shop_visit_trend", "oil_consumption",
            "deferral_status", "deferral_expiry", "deferral_categories",
            "deferral_extensions", "deferral_repeats", "deferral_closure",
            "fracas_stages", "fracas_ageing", "root_causes", "effectiveness",
            "fracas_actions", "fracas_action_trend", "fracas_reopened",
            "engine_status", "source_health", "data_quality",
        )
    }
    report.data_quality_json = {
        "warnings": dashboard_data.get("warnings", []),
        "data_quality": dashboard_data.get("data_quality", []),
        "source_health": dashboard_data.get("source_health", []),
    }
    previous = report.status
    report.status = FormalReportStatus.DATA_REVIEW.value
    _append_lifecycle(
        db,
        report,
        from_status=previous,
        to_status=report.status,
        action="FREEZE_DATA",
        actor=user,
        payload={
            "data_cutoff_at": now.isoformat(),
            "effectivity": report.effectivity_json,
            "source_identity_sha256": source_population["source_identity_sha256"],
        },
    )
    db.commit()
    db.refresh(report)
    return report


def _override_codes(db: Session, report: ReliabilityFormalReport) -> set[str]:
    return {
        row.check_code
        for row in db.query(ReliabilityFormalCompletenessOverride).filter(
            ReliabilityFormalCompletenessOverride.report_id == report.id,
            ReliabilityFormalCompletenessOverride.amo_id == report.amo_id,
        ).all()
    }


def completeness_result(db: Session, report: ReliabilityFormalReport, *, persist: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    overrides = _override_codes(db, report)

    def check(code: str, ok: bool, message: str, blocking: bool = True) -> None:
        override = code in overrides
        checks.append({
            "code": code,
            "passed": bool(ok or override),
            "raw_passed": bool(ok),
            "overridden": override,
            "blocking": blocking,
            "message": message,
        })

    check("PROFILE", bool(report.profile_id and report.profile_code_snapshot and report.profile_version_snapshot), "Regulatory profile/version is frozen.")
    check("EFFECTIVITY", bool(report.effectivity_frozen_at and report.effectivity_json), "Fleet/effectivity is frozen.")
    check("DATA_CUTOFF", bool(report.data_cutoff_at), "Data cutoff is frozen.")
    check("SOURCE_POPULATION", bool((report.source_population_json or {}).get("source_identity_sha256")), "Controlled source population identity is retained.")
    check("CALCULATION_SNAPSHOT", bool((report.calculation_snapshots_json or {}).get("dashboard")), "Governed Reliability calculation snapshot is retained.")
    check("FORMULA_REVISIONS", bool(report.formula_revisions_json), "Formula revision manifest is retained.")

    sections = db.query(ReliabilityFormalReportSection).filter(
        ReliabilityFormalReportSection.report_id == report.id,
        ReliabilityFormalReportSection.amo_id == report.amo_id,
    ).all()
    required_sections = [row for row in sections if row.required]
    incomplete_sections = [
        row.section_code for row in required_sections
        if row.status not in {
            FormalSectionStatus.READY.value,
            FormalSectionStatus.NOT_APPLICABLE.value,
        }
    ]
    check(
        "MANDATORY_SECTIONS",
        not incomplete_sections,
        "All required report sections are ready or governed not-applicable.",
    )

    assessments = db.query(ReliabilityFormalRequirementAssessment).filter(
        ReliabilityFormalRequirementAssessment.report_id == report.id,
        ReliabilityFormalRequirementAssessment.amo_id == report.amo_id,
    ).all()
    for assessment in assessments:
        snapshot = assessment.requirement_snapshot or {}
        mandatory = snapshot.get("obligation_status") == RegulatoryObligation.MANDATORY.value
        publication_blocking = bool((snapshot.get("completeness_rule") or {}).get("publication_blocking", mandatory))
        if not assessment.applicable or assessment.status in {
            RequirementAssessmentStatus.NOT_APPLICABLE.value,
            RequirementAssessmentStatus.SUPERSEDED.value,
        }:
            continue
        if assessment.status == RequirementAssessmentStatus.GAP.value:
            check(
                f"REQUIREMENT:{assessment.requirement_id}",
                False,
                f"Applicable requirement {snapshot.get('requirement_key') or assessment.requirement_id} remains GAP.",
                publication_blocking,
            )
        elif assessment.status == RequirementAssessmentStatus.WITHHELD.value:
            explained = bool((assessment.reviewer_note or "").strip())
            check(
                f"WITHHELD:{assessment.requirement_id}",
                explained and not mandatory,
                f"Applicable requirement {snapshot.get('requirement_key') or assessment.requirement_id} is WITHHELD.",
                publication_blocking,
            )
    check("HTML_HASH", bool(report.rendered_html and report.html_sha256), "Retained formal HTML and SHA-256 are present.")
    check("PDF_HASH", bool(report.pdf_storage_ref and report.pdf_sha256), "Retained formal PDF and SHA-256 are present.")

    blocking_failures = [row for row in checks if row["blocking"] and not row["passed"]]
    result = {
        "passed": not blocking_failures,
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "blocking_failures": [row["code"] for row in blocking_failures],
        "override_count": len(overrides),
    }
    if persist:
        report.completeness_json = result
        db.flush()
    return result


def _roles_for_transition(profile: ReliabilityRegulatoryProfile, to_status: str) -> set[str]:
    workflow = profile.approval_workflow or {}
    if to_status == FormalReportStatus.TECHNICAL_REVIEW.value:
        return set(workflow.get("technical_review_roles") or TECHNICAL_REVIEW_ROLES)
    if to_status == FormalReportStatus.QUALITY_REVIEW.value:
        return set(workflow.get("quality_review_roles") or QUALITY_REVIEW_ROLES)
    if to_status in {
        FormalReportStatus.APPROVAL_PENDING.value,
        FormalReportStatus.APPROVED.value,
        FormalReportStatus.PUBLISHED.value,
        FormalReportStatus.SUPERSEDED.value,
        FormalReportStatus.WITHDRAWN.value,
    }:
        return set(workflow.get("approval_roles") or APPROVAL_ROLES)
    return ANALYSIS_ROLES


def _transition_report(
    db: Session,
    report: ReliabilityFormalReport,
    user: account_models.User,
    payload: TransitionRequest,
) -> ReliabilityFormalReport:
    _require_human(user)
    target = payload.to_status.value
    allowed = ALLOWED_TRANSITIONS.get(report.status, set())
    if target not in allowed:
        raise HTTPException(status_code=409, detail=f"Transition {report.status} -> {target} is not allowed.")
    profile = _profile(db, report.amo_id, report.profile_id)
    _require_role(user, _roles_for_transition(profile, target), "Your role cannot perform this formal Reliability transition.")

    if (
        bool((profile.approval_workflow or {}).get("separation_of_duties", True))
        and target in {FormalReportStatus.APPROVED.value, FormalReportStatus.PUBLISHED.value}
        and report.created_by_user_id == user.id
        and not bool(getattr(user, "is_superuser", False))
    ):
        raise HTTPException(status_code=409, detail="Separation of duties prevents the preparer approving/publishing the same report revision.")

    if target in {
        FormalReportStatus.APPROVAL_PENDING.value,
        FormalReportStatus.APPROVED.value,
        FormalReportStatus.PUBLISHED.value,
    }:
        result = completeness_result(db, report, persist=True)
        if not result["passed"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Formal Reliability report completeness gate failed.",
                    "blocking_failures": result["blocking_failures"],
                },
            )

    previous = report.status
    report.status = target
    if target == FormalReportStatus.PUBLISHED.value:
        report.published_at = datetime.now(UTC)
        report.published_by_user_id = user.id
    elif target == FormalReportStatus.SUPERSEDED.value:
        report.superseded_at = datetime.now(UTC)
        report.superseded_by_user_id = user.id
    elif target == FormalReportStatus.WITHDRAWN.value:
        report.withdrawn_at = datetime.now(UTC)
        report.withdrawn_by_user_id = user.id

    db.add(ReliabilityFormalApproval(
        amo_id=report.amo_id,
        report_id=report.id,
        stage=previous,
        decision=target,
        actor_user_id=user.id,
        role_snapshot=_role(user),
        comment=payload.comment,
        report_revision=report.revision,
        report_hash=report.pdf_sha256 or report.html_sha256,
    ))
    _append_lifecycle(
        db,
        report,
        from_status=previous,
        to_status=target,
        action="TRANSITION",
        actor=user,
        rationale=payload.comment,
        payload={"report_hash": report.pdf_sha256 or report.html_sha256},
    )
    db.commit()
    db.refresh(report)
    return report


def register(router: APIRouter) -> None:
    @router.post("/formal-reporting/profiles/bootstrap")
    def bootstrap_profiles(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, PROFILE_ADMIN_ROLES, "Regulatory profile administration permission is required.")
        rows = ensure_baseline_profiles(db, amo_id, current_user.id)
        return {"profiles": [_profile_dict(row) for row in rows]}

    @router.get("/formal-reporting/profiles")
    def list_profiles(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        rows = ensure_baseline_profiles(db, amo_id, current_user.id)
        return {"profiles": [_profile_dict(row) for row in rows]}

    @router.get("/formal-reporting/profiles/{profile_id}/requirements")
    def list_profile_requirements(
        profile_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        row = _profile(db, amo_id, profile_id)
        requirements = db.query(ReliabilityRegulatoryRequirement).filter(
            ReliabilityRegulatoryRequirement.amo_id == amo_id,
            ReliabilityRegulatoryRequirement.profile_id == row.id,
        ).order_by(ReliabilityRegulatoryRequirement.requirement_key).all()
        return {"profile": _profile_dict(row), "requirements": [_requirement_snapshot(item) for item in requirements]}

    @router.post("/formal-reporting/reports", status_code=status.HTTP_201_CREATED)
    def create_report(
        payload: FormalReportCreate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability report preparation permission is required.")
        ensure_baseline_profiles(db, amo_id, current_user.id)
        row = _create_formal_report(db, amo_id, current_user, payload)
        return _report_dict(db, row, detail=True)

    @router.get("/formal-reporting/reports")
    def list_reports(
        limit: int = Query(default=50, ge=1, le=250),
        offset: int = Query(default=0, ge=0),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        query = db.query(ReliabilityFormalReport).filter(ReliabilityFormalReport.amo_id == amo_id)
        total = query.with_entities(func.count(ReliabilityFormalReport.id)).scalar() or 0
        rows = query.order_by(ReliabilityFormalReport.period_end.desc(), ReliabilityFormalReport.created_at.desc()).offset(offset).limit(limit).all()
        return {"total": total, "limit": limit, "offset": offset, "reports": [_report_dict(db, row) for row in rows]}

    @router.get("/formal-reporting/reports/{report_id}")
    def get_report(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        return _report_dict(db, _report(db, amo_id, report_id), detail=True)

    @router.post("/formal-reporting/reports/{report_id}/freeze")
    def freeze_report(
        report_id: str,
        payload: FormalFreezeRequest,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability report preparation permission is required.")
        row = _freeze_report(db, _report(db, amo_id, report_id), current_user, payload)
        return _report_dict(db, row, detail=True)

    @router.put("/formal-reporting/reports/{report_id}/sections/{section_code}")
    def update_section(
        report_id: str,
        section_code: str,
        payload: FormalSectionUpdate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability report preparation permission is required.")
        report = _report(db, amo_id, report_id)
        _require_editable(report)
        row = db.query(ReliabilityFormalReportSection).filter(
            ReliabilityFormalReportSection.report_id == report.id,
            ReliabilityFormalReportSection.amo_id == amo_id,
            ReliabilityFormalReportSection.section_code == section_code,
        ).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Formal report section not found.")
        row.status = payload.status
        row.commentary = payload.commentary
        row.evidence_refs = payload.evidence_refs
        row.warnings = payload.warnings
        row.updated_by_user_id = current_user.id
        db.commit()
        return _report_dict(db, report, detail=True)

    @router.put("/formal-reporting/reports/{report_id}/requirements/{assessment_id}")
    def update_requirement_assessment(
        report_id: str,
        assessment_id: str,
        payload: RequirementAssessmentUpdate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_human(current_user)
        _require_role(current_user, TECHNICAL_REVIEW_ROLES | QUALITY_REVIEW_ROLES, "Reliability review permission is required.")
        report = _report(db, amo_id, report_id)
        _require_editable(report)
        row = db.query(ReliabilityFormalRequirementAssessment).filter(
            ReliabilityFormalRequirementAssessment.id == assessment_id,
            ReliabilityFormalRequirementAssessment.report_id == report.id,
            ReliabilityFormalRequirementAssessment.amo_id == amo_id,
        ).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Formal requirement assessment not found.")
        row.applicable = payload.applicable
        row.status = payload.status.value
        row.reviewer_note = payload.reviewer_note
        row.evidence_refs = payload.evidence_refs
        row.calculation_refs = payload.calculation_refs
        row.source_refs = payload.source_refs
        row.resolved_at = datetime.now(UTC) if payload.status in {
            RequirementAssessmentStatus.SATISFIED,
            RequirementAssessmentStatus.NOT_APPLICABLE,
            RequirementAssessmentStatus.SUPERSEDED,
        } else None
        row.resolved_by_user_id = current_user.id if row.resolved_at else None
        db.commit()
        return _report_dict(db, report, detail=True)

    @router.post("/formal-reporting/reports/{report_id}/completeness")
    def run_completeness(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        report = _report(db, amo_id, report_id)
        result = completeness_result(db, report, persist=report.status not in TERMINAL_STATUSES)
        if report.status not in TERMINAL_STATUSES:
            db.commit()
        return result

    @router.post("/formal-reporting/reports/{report_id}/completeness-overrides", status_code=status.HTTP_201_CREATED)
    def create_completeness_override(
        report_id: str,
        payload: CompletenessOverrideCreate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_human(current_user)
        _require_role(current_user, APPROVAL_ROLES, "Formal Reliability override approval permission is required.")
        report = _report(db, amo_id, report_id)
        _require_editable(report)
        if payload.requirement_id:
            requirement = db.query(ReliabilityRegulatoryRequirement).filter(
                ReliabilityRegulatoryRequirement.id == payload.requirement_id,
                ReliabilityRegulatoryRequirement.amo_id == amo_id,
                ReliabilityRegulatoryRequirement.profile_id == report.profile_id,
            ).one_or_none()
            if not requirement:
                raise HTTPException(status_code=404, detail="Regulatory requirement not found for this report profile.")
            permitted = {
                f"REQUIREMENT:{requirement.id}",
                f"WITHHELD:{requirement.id}",
            }
            if payload.check_code not in permitted:
                raise HTTPException(status_code=422, detail="Requirement override check_code does not match the requirement.")
        row = ReliabilityFormalCompletenessOverride(
            amo_id=amo_id,
            report_id=report.id,
            check_code=payload.check_code,
            requirement_id=payload.requirement_id,
            justification=payload.justification,
            authority_basis=payload.authority_basis,
            approved_by_user_id=current_user.id,
            approved_role=_role(current_user),
            report_hash=report.pdf_sha256 or report.html_sha256,
        )
        db.add(row)
        db.commit()
        return {"id": row.id, "check_code": row.check_code, "created_at": row.created_at}

    @router.post("/formal-reporting/reports/{report_id}/transition")
    def transition_report(
        report_id: str,
        payload: TransitionRequest,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        row = _transition_report(db, _report(db, amo_id, report_id), current_user, payload)
        return _report_dict(db, row, detail=True)
