from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from . import advanced_models
from .formal_reporting import (
    ANALYSIS_ROLES,
    APPROVAL_ROLES,
    FormalReportCreate,
    _amo_id,
    _create_formal_report,
    _profile,
    _report,
    _report_dict,
    _require_human,
    _require_role,
)
from .formal_reporting_models import (
    AmpRecommendationStatus,
    FormalPeriodType,
    FormalReportStatus,
    ReliabilityAmpRecommendation,
    ReliabilityFormalDistribution,
    ReliabilityFormalReport,
    ReliabilityReportingSchedule,
    ReportingScheduleStatus,
)

UTC = timezone.utc

AMP_CHANGE_TYPES = {
    "TASK_ESCALATION",
    "TASK_DE_ESCALATION",
    "INTERVAL_CHANGE",
    "INSPECTION_CHANGE",
    "ADDITIONAL_TASK",
    "REMOVE_INEFFECTIVE_TASK",
    "ENHANCED_INSPECTION",
    "REPETITIVE_MONITORING",
    "COMPONENT_PROGRAMME_CHANGE",
    "ENGINEERING_INVESTIGATION",
}
AMP_FLOW = [item.value for item in AmpRecommendationStatus]
DISTRIBUTABLE_STATUSES = {
    FormalReportStatus.PUBLISHED.value,
    FormalReportStatus.SUPERSEDED.value,
}


class SupersedingRevisionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    report_number: str | None = Field(default=None, max_length=100)


class ReportingScheduleCreate(BaseModel):
    profile_id: str | None = None
    programme_id: str | None = None
    obligation_code: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=255)
    period_type: FormalPeriodType
    period_start: date
    period_end: date
    due_date: date
    owner_user_id: str | None = None
    cycle_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Schedule period end must be on or after period start.")
        return self


class ReportingScheduleStatusUpdate(BaseModel):
    status: ReportingScheduleStatus
    report_id: str | None = None


class AmpRecommendationCreate(BaseModel):
    report_id: str | None = None
    programme_id: str | None = None
    programme_item_id: int | None = None
    title: str = Field(min_length=3, max_length=255)
    summary: str = Field(min_length=10, max_length=8000)
    change_type: str = Field(min_length=3, max_length=48)
    source_evidence: list[dict[str, Any]] = Field(min_length=1)
    current_requirement: dict[str, Any] = Field(default_factory=dict)
    proposed_change: dict[str, Any] = Field(default_factory=dict)
    technical_basis: dict[str, Any] = Field(default_factory=dict)
    authority_approval_required: bool = False
    owner_user_id: str | None = None
    target_date: date | None = None
    effectiveness_due_date: date | None = None

    @model_validator(mode="after")
    def validate_change_type(self):
        self.change_type = self.change_type.strip().upper()
        if self.change_type not in AMP_CHANGE_TYPES:
            raise ValueError(f"Unsupported AMP recommendation type: {self.change_type}")
        if not self.proposed_change:
            raise ValueError("A governed AMP recommendation requires a proposed_change payload.")
        return self


class AmpRecommendationTransition(BaseModel):
    to_status: AmpRecommendationStatus
    comment: str = Field(min_length=3, max_length=4000)


class FormalDistributionCreate(BaseModel):
    recipient_user_id: str | None = None
    recipient_role: str | None = Field(default=None, max_length=64)
    external_recipient_ref: str | None = Field(default=None, max_length=255)
    channel: Literal["PORTAL"] = "PORTAL"

    @model_validator(mode="after")
    def require_recipient(self):
        if not (self.recipient_user_id or self.recipient_role or self.external_recipient_ref):
            raise ValueError("A controlled distribution recipient or role is required.")
        return self


def _schedule_dict(row: ReliabilityReportingSchedule) -> dict[str, Any]:
    today = date.today()
    overdue = row.due_date < today and row.status not in {
        ReportingScheduleStatus.COMPLETE.value,
        ReportingScheduleStatus.CANCELLED.value,
    }
    return {
        "id": row.id,
        "profile_id": row.profile_id,
        "programme_id": row.programme_id,
        "report_id": row.report_id,
        "obligation_code": row.obligation_code,
        "name": row.name,
        "period_type": row.period_type,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "due_date": row.due_date,
        "cycle_config": row.cycle_config,
        "status": row.status,
        "effective_status": ReportingScheduleStatus.OVERDUE.value if overdue else row.status,
        "overdue": overdue,
        "owner_user_id": row.owner_user_id,
        "completeness": row.completeness_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _amp_dict(row: ReliabilityAmpRecommendation) -> dict[str, Any]:
    return {
        "id": row.id,
        "report_id": row.report_id,
        "programme_id": row.programme_id,
        "programme_item_id": row.programme_item_id,
        "title": row.title,
        "summary": row.summary,
        "change_type": row.change_type,
        "status": row.status,
        "source_evidence": row.source_evidence,
        "current_requirement": row.current_requirement,
        "proposed_change": row.proposed_change,
        "technical_basis": row.technical_basis,
        "authority_approval_required": row.authority_approval_required,
        "owner_user_id": row.owner_user_id,
        "target_date": row.target_date,
        "approved_at": row.approved_at,
        "implemented_at": row.implemented_at,
        "effectiveness_due_date": row.effectiveness_due_date,
        "closed_at": row.closed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _change_proposal_id(row: ReliabilityAmpRecommendation) -> str | None:
    for item in row.source_evidence or []:
        if item.get("kind") == "RELIABILITY_CHANGE_PROPOSAL" and item.get("id"):
            return str(item["id"])
    return None


def _create_change_proposal(
    db: Session,
    row: ReliabilityAmpRecommendation,
    actor_user_id: str | None,
) -> advanced_models.ReliabilityChangeProposal:
    proposal = advanced_models.ReliabilityChangeProposal(
        amo_id=row.amo_id,
        source_type="FORMAL_AMP_RECOMMENDATION",
        source_id=row.id,
        proposal_type=row.change_type,
        title=row.title,
        problem_statement=row.summary,
        proposed_change_json=row.proposed_change,
        impact_assessment_json={
            "technical_basis": row.technical_basis,
            "current_requirement": row.current_requirement,
            "authority_approval_required": row.authority_approval_required,
        },
        simulation_json={},
        status=row.status,
        effectiveness_due_date=row.effectiveness_due_date,
        owner_user_id=row.owner_user_id,
        created_by_user_id=actor_user_id,
    )
    db.add(proposal)
    db.flush()
    return proposal


def _clone_revision(
    db: Session,
    source: ReliabilityFormalReport,
    actor: account_models.User,
    payload: SupersedingRevisionCreate,
) -> ReliabilityFormalReport:
    if source.status not in DISTRIBUTABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Only a published/superseded formal report can start a superseding revision.")
    latest_revision = db.query(func.max(ReliabilityFormalReport.revision)).filter(
        ReliabilityFormalReport.amo_id == source.amo_id,
        ReliabilityFormalReport.report_number == (payload.report_number or source.report_number),
    ).scalar()
    next_revision = max(int(latest_revision or 0) + 1, source.revision + 1)
    request = FormalReportCreate(
        profile_id=source.profile_id,
        programme_id=source.programme_id,
        report_number=(payload.report_number or source.report_number),
        revision=next_revision,
        title=(payload.title or source.title),
        period_type=FormalPeriodType(source.period_type),
        period_start=source.period_start,
        period_end=source.period_end,
    )
    row = _create_formal_report(db, source.amo_id, actor, request)
    row.supersedes_report_id = source.id
    db.commit()
    db.refresh(row)
    return row


def register(router: APIRouter) -> None:
    @router.post("/formal-reporting/reports/{report_id}/superseding-revision", status_code=status.HTTP_201_CREATED)
    def create_superseding_revision(
        report_id: str,
        payload: SupersedingRevisionCreate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_human(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability report preparation permission is required.")
        source = _report(db, amo_id, report_id)
        return _report_dict(db, _clone_revision(db, source, current_user, payload), detail=True)

    @router.post("/formal-reporting/schedule", status_code=status.HTTP_201_CREATED)
    def create_schedule(
        payload: ReportingScheduleCreate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability reporting schedule permission is required.")
        if payload.profile_id:
            _profile(db, amo_id, payload.profile_id)
        duplicate = db.query(ReliabilityReportingSchedule.id).filter(
            ReliabilityReportingSchedule.amo_id == amo_id,
            ReliabilityReportingSchedule.obligation_code == payload.obligation_code.strip(),
            ReliabilityReportingSchedule.period_start == payload.period_start,
            ReliabilityReportingSchedule.period_end == payload.period_end,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="This Reliability reporting obligation already exists for the period.")
        row = ReliabilityReportingSchedule(
            amo_id=amo_id,
            profile_id=payload.profile_id,
            programme_id=payload.programme_id,
            obligation_code=payload.obligation_code.strip(),
            name=payload.name.strip(),
            period_type=payload.period_type.value,
            period_start=payload.period_start,
            period_end=payload.period_end,
            due_date=payload.due_date,
            cycle_config=payload.cycle_config,
            status=ReportingScheduleStatus.PLANNED.value,
            owner_user_id=payload.owner_user_id,
            created_by_user_id=current_user.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _schedule_dict(row)

    @router.get("/formal-reporting/schedule")
    def list_schedule(
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability reporting schedule permission is required.")
        query = db.query(ReliabilityReportingSchedule).filter(ReliabilityReportingSchedule.amo_id == amo_id)
        total = query.with_entities(func.count(ReliabilityReportingSchedule.id)).scalar() or 0
        rows = query.order_by(ReliabilityReportingSchedule.due_date, ReliabilityReportingSchedule.period_start).offset(offset).limit(limit).all()
        return {"total": total, "limit": limit, "offset": offset, "items": [_schedule_dict(row) for row in rows]}

    @router.put("/formal-reporting/schedule/{schedule_id}/status")
    def update_schedule_status(
        schedule_id: str,
        payload: ReportingScheduleStatusUpdate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability reporting schedule permission is required.")
        row = db.query(ReliabilityReportingSchedule).filter(
            ReliabilityReportingSchedule.id == schedule_id,
            ReliabilityReportingSchedule.amo_id == amo_id,
        ).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Reliability reporting obligation not found.")
        if payload.report_id:
            linked = _report(db, amo_id, payload.report_id)
            if linked.period_start != row.period_start or linked.period_end != row.period_end:
                raise HTTPException(status_code=409, detail="Linked report period does not match the reporting obligation period.")
            row.report_id = linked.id
        row.status = payload.status.value
        db.commit()
        db.refresh(row)
        return _schedule_dict(row)

    @router.post("/formal-reporting/amp-recommendations", status_code=status.HTTP_201_CREATED)
    def create_amp_recommendation(
        payload: AmpRecommendationCreate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_human(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability engineering recommendation permission is required.")
        if payload.report_id:
            _report(db, amo_id, payload.report_id)
        row = ReliabilityAmpRecommendation(
            amo_id=amo_id,
            report_id=payload.report_id,
            programme_id=payload.programme_id,
            programme_item_id=payload.programme_item_id,
            title=payload.title.strip(),
            summary=payload.summary.strip(),
            change_type=payload.change_type,
            status=AmpRecommendationStatus.IDENTIFIED.value,
            source_evidence=payload.source_evidence,
            current_requirement=payload.current_requirement,
            proposed_change=payload.proposed_change,
            technical_basis=payload.technical_basis,
            authority_approval_required=payload.authority_approval_required,
            owner_user_id=payload.owner_user_id,
            target_date=payload.target_date,
            effectiveness_due_date=payload.effectiveness_due_date,
            created_by_user_id=current_user.id,
        )
        db.add(row)
        db.flush()
        proposal = _create_change_proposal(db, row, current_user.id)
        row.source_evidence = [
            *row.source_evidence,
            {"kind": "RELIABILITY_CHANGE_PROPOSAL", "id": proposal.id},
        ]
        db.commit()
        db.refresh(row)
        return _amp_dict(row)

    @router.get("/formal-reporting/amp-recommendations")
    def list_amp_recommendations(
        report_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        query = db.query(ReliabilityAmpRecommendation).filter(ReliabilityAmpRecommendation.amo_id == amo_id)
        if report_id:
            query = query.filter(ReliabilityAmpRecommendation.report_id == report_id)
        total = query.with_entities(func.count(ReliabilityAmpRecommendation.id)).scalar() or 0
        rows = query.order_by(ReliabilityAmpRecommendation.created_at.desc()).offset(offset).limit(limit).all()
        return {"total": total, "limit": limit, "offset": offset, "items": [_amp_dict(row) for row in rows]}

    @router.post("/formal-reporting/amp-recommendations/{recommendation_id}/transition")
    def transition_amp_recommendation(
        recommendation_id: str,
        payload: AmpRecommendationTransition,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_human(current_user)
        row = db.query(ReliabilityAmpRecommendation).filter(
            ReliabilityAmpRecommendation.id == recommendation_id,
            ReliabilityAmpRecommendation.amo_id == amo_id,
        ).one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Reliability AMP recommendation not found.")
        current_index = AMP_FLOW.index(row.status)
        target = payload.to_status.value
        if current_index >= len(AMP_FLOW) - 1 or AMP_FLOW[current_index + 1] != target:
            raise HTTPException(status_code=409, detail=f"AMP recommendation must advance from {row.status} to the next governed stage.")
        if target in {
            AmpRecommendationStatus.QUALITY_REVIEW.value,
            AmpRecommendationStatus.AUTHORITY_APPROVAL_REQUIRED.value,
            AmpRecommendationStatus.APPROVED.value,
        }:
            _require_role(current_user, APPROVAL_ROLES, "Quality/approval permission is required for this AMP recommendation stage.")
        else:
            _require_role(current_user, ANALYSIS_ROLES, "Reliability engineering recommendation permission is required.")
        row.status = target
        if target == AmpRecommendationStatus.APPROVED.value:
            row.approved_at = datetime.now(UTC)
            row.approved_by_user_id = current_user.id
        elif target == AmpRecommendationStatus.IMPLEMENTED.value:
            row.implemented_at = datetime.now(UTC)
        elif target == AmpRecommendationStatus.CLOSED.value:
            row.closed_at = datetime.now(UTC)
        proposal_id = _change_proposal_id(row)
        if proposal_id:
            proposal = db.query(advanced_models.ReliabilityChangeProposal).filter(
                advanced_models.ReliabilityChangeProposal.id == proposal_id,
                advanced_models.ReliabilityChangeProposal.amo_id == amo_id,
            ).one_or_none()
            if proposal:
                proposal.status = target
                approval = dict(proposal.approval_json or {})
                history = list(approval.get("formal_status_history") or [])
                history.append({
                    "status": target,
                    "actor_user_id": current_user.id,
                    "role": str(getattr(getattr(current_user, "role", None), "value", getattr(current_user, "role", ""))),
                    "comment": payload.comment,
                    "at": datetime.now(UTC).isoformat(),
                })
                approval["formal_status_history"] = history
                proposal.approval_json = approval
        db.commit()
        db.refresh(row)
        return _amp_dict(row)

    @router.post("/formal-reporting/reports/{report_id}/distribution", status_code=status.HTTP_201_CREATED)
    def distribute_report(
        report_id: str,
        payload: FormalDistributionCreate,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_human(current_user)
        _require_role(current_user, APPROVAL_ROLES, "Controlled Reliability distribution permission is required.")
        report = _report(db, amo_id, report_id)
        if report.status != FormalReportStatus.PUBLISHED.value:
            raise HTTPException(status_code=409, detail="Only the current published formal Reliability revision can be newly distributed.")
        report_hash = report.pdf_sha256 or report.html_sha256
        if not report_hash:
            raise HTTPException(status_code=409, detail="The published formal report has no retained artifact hash.")
        row = ReliabilityFormalDistribution(
            amo_id=amo_id,
            report_id=report.id,
            recipient_user_id=payload.recipient_user_id,
            recipient_role=payload.recipient_role,
            external_recipient_ref=payload.external_recipient_ref,
            channel=payload.channel,
            revision_snapshot=report.revision,
            report_hash=report_hash,
            distributed_by_user_id=current_user.id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "report_id": row.report_id,
            "recipient_user_id": row.recipient_user_id,
            "recipient_role": row.recipient_role,
            "external_recipient_ref": row.external_recipient_ref,
            "channel": row.channel,
            "revision": row.revision_snapshot,
            "report_hash": row.report_hash,
            "distributed_at": row.distributed_at,
        }

    @router.get("/formal-reporting/reports/{report_id}/distribution")
    def list_distribution(
        report_id: str,
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ):
        amo_id = _amo_id(current_user)
        _require_role(current_user, ANALYSIS_ROLES, "Reliability analysis permission is required.")
        report = _report(db, amo_id, report_id)
        rows = db.query(ReliabilityFormalDistribution).filter(
            ReliabilityFormalDistribution.amo_id == amo_id,
            ReliabilityFormalDistribution.report_id == report.id,
        ).order_by(ReliabilityFormalDistribution.distributed_at.desc()).all()
        return {"items": [{
            "id": row.id,
            "recipient_user_id": row.recipient_user_id,
            "recipient_role": row.recipient_role,
            "external_recipient_ref": row.external_recipient_ref,
            "channel": row.channel,
            "revision": row.revision_snapshot,
            "report_hash": row.report_hash,
            "distributed_at": row.distributed_at,
            "acknowledged_at": row.acknowledged_at,
        } for row in rows]}
