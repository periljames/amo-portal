from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from amodb.database import get_write_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models

from . import advanced_schemas as schemas
from . import advanced_services as services


router = APIRouter()


def _context(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> tuple[account_models.User, Session, str]:
    return current_user, db, services.tenant_id(current_user)


@router.get("/capabilities", response_model=schemas.CapabilitySnapshot)
def capability_snapshot(context=Depends(_context)):
    current_user, db, _ = context
    return schemas.CapabilitySnapshot(
        capabilities=services.capabilities_for_user(db, current_user),
        superuser=bool(getattr(current_user, "is_superuser", False)),
    )


@router.post("/bootstrap", response_model=schemas.BootstrapResult)
def bootstrap(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.programme.manage")
    return services.bootstrap_reliability(db, amo_id=amo_id, actor_user_id=str(current_user.id))


@router.get("/sources", response_model=List[schemas.ReliabilitySourceRead])
def sources(context=Depends(_context)):
    _, db, amo_id = context
    return services.list_sources(db, amo_id=amo_id)


@router.post("/sources", response_model=schemas.ReliabilitySourceRead, status_code=201)
def create_source(payload: schemas.ReliabilitySourceCreate, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.source.manage")
    return services.create_source(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/sources/{source_id}/ingest", response_model=schemas.ReliabilityIngestionResult)
def ingest_source(source_id: str, payload: schemas.ReliabilityBatchIngest, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    source = services.get_source(db, amo_id=amo_id, source_id=source_id)
    return services.ingest_batch(
        db,
        amo_id=amo_id,
        source=source,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/sources/harvest-internal", response_model=List[schemas.ReliabilityIngestionResult])
def harvest_internal(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ingest")
    return services.harvest_internal_sources(
        db,
        amo_id=amo_id,
        actor_user_id=str(current_user.id),
    )


@router.get("/ingestion-batches", response_model=List[schemas.ReliabilityIngestionBatchRead])
def ingestion_batches(
    source_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_batches(db, amo_id=amo_id, source_id=source_id, limit=limit)


@router.get("/data-quality/issues", response_model=List[schemas.ReliabilityDataQualityIssueRead])
def data_quality_issues(
    status: Optional[str] = None,
    source_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_data_quality_issues(
        db,
        amo_id=amo_id,
        issue_status=status,
        source_id=source_id,
        limit=limit,
    )


@router.post("/data-quality/issues/{issue_id}/resolve", response_model=schemas.ReliabilityDataQualityIssueRead)
def resolve_data_quality_issue(
    issue_id: str,
    payload: schemas.DataQualityResolution,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.data_quality.resolve")
    return services.resolve_data_quality_issue(
        db,
        amo_id=amo_id,
        issue_id=issue_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/events/{event_id:int}/provenance", response_model=schemas.OccurrenceProvenance)
def occurrence_provenance(event_id: int, context=Depends(_context)):
    _, db, amo_id = context
    return services.event_provenance(db, amo_id=amo_id, event_id=event_id)


@router.get("/fracas/cases/{case_id:int}/lifecycle", response_model=schemas.FracasLifecycleRead)
def fracas_lifecycle(case_id: int, context=Depends(_context)):
    current_user, db, amo_id = context
    return services.ensure_fracas_lifecycle(
        db,
        amo_id=amo_id,
        case_id=case_id,
        actor_user_id=str(current_user.id),
    )


@router.put("/fracas/cases/{case_id:int}/lifecycle", response_model=schemas.FracasLifecycleRead)
def update_fracas_lifecycle(
    case_id: int,
    payload: schemas.FracasLifecycleUpdate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.fracas.investigate")
    return services.update_fracas_lifecycle(
        db,
        amo_id=amo_id,
        case_id=case_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/fracas/cases/{case_id:int}/transition", response_model=schemas.FracasLifecycleRead)
def transition_fracas(
    case_id: int,
    payload: schemas.FracasTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    if payload.to_stage in {"TRIAGE", "ACCEPTED", "REJECTED", "MERGED", "CONTAINMENT"}:
        capability = "reliability.fracas.triage"
    elif payload.to_stage in {"INVESTIGATION", "ROOT_CAUSE_REVIEW"}:
        capability = "reliability.fracas.investigate"
    elif payload.to_stage in {"ACTION_APPROVAL", "IMPLEMENTATION"}:
        capability = "reliability.fracas.action"
    else:
        capability = "reliability.fracas.verify"
    services.require_capability(db, current_user, capability)
    return services.transition_fracas(
        db,
        amo_id=amo_id,
        case_id=case_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/fracas/cases/{case_id:int}/evidence", response_model=List[schemas.FracasEvidenceRead])
def fracas_evidence(case_id: int, context=Depends(_context)):
    _, db, amo_id = context
    return services.list_fracas_evidence(db, amo_id=amo_id, case_id=case_id)


@router.post("/fracas/cases/{case_id:int}/evidence", response_model=schemas.FracasEvidenceRead, status_code=201)
def add_fracas_evidence(
    case_id: int,
    payload: schemas.FracasEvidenceCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.fracas.investigate")
    return services.add_fracas_evidence(
        db,
        amo_id=amo_id,
        case_id=case_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/fracas/cases/{case_id:int}/stage-events", response_model=List[schemas.FracasStageEventRead])
def fracas_stage_events(case_id: int, context=Depends(_context)):
    _, db, amo_id = context
    return services.list_fracas_stage_events(db, amo_id=amo_id, case_id=case_id)


@router.get("/fracas/cases/{case_id:int}/effectiveness", response_model=List[schemas.EffectivenessReviewRead])
def effectiveness_reviews(case_id: int, context=Depends(_context)):
    _, db, amo_id = context
    return services.list_effectiveness_reviews(db, amo_id=amo_id, case_id=case_id)


@router.post("/fracas/cases/{case_id:int}/effectiveness", response_model=schemas.EffectivenessReviewRead, status_code=201)
def add_effectiveness_review(
    case_id: int,
    payload: schemas.EffectivenessReviewCreate,
    approve: bool = False,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.fracas.verify")
    return services.create_effectiveness_review(
        db,
        amo_id=amo_id,
        case_id=case_id,
        payload=payload,
        actor_user_id=str(current_user.id),
        approve=approve,
    )


@router.get("/programmes", response_model=List[schemas.ProgrammeRead])
def programmes(context=Depends(_context)):
    _, db, amo_id = context
    return services.list_programmes(db, amo_id=amo_id)


@router.post("/programmes", response_model=schemas.ProgrammeRead, status_code=201)
def create_programme(payload: schemas.ProgrammeCreate, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.programme.manage")
    return services.create_programme(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/programme-versions", response_model=List[schemas.ProgrammeVersionRead])
def programme_versions(
    programme_id: Optional[str] = None,
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_programme_versions(db, amo_id=amo_id, programme_id=programme_id)


@router.post("/programmes/{programme_id}/versions", response_model=schemas.ProgrammeVersionRead, status_code=201)
def create_programme_version(
    programme_id: str,
    payload: schemas.ProgrammeVersionCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.programme.manage")
    return services.create_programme_version(
        db,
        amo_id=amo_id,
        programme_id=programme_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/programme-versions/{version_id}/transition", response_model=schemas.ProgrammeVersionRead)
def transition_programme_version(
    version_id: str,
    payload: schemas.ProgrammeTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    capability = "reliability.programme.approve" if payload.to_status in {"APPROVED", "EFFECTIVE", "SUPERSEDED"} else "reliability.programme.manage"
    services.require_capability(db, current_user, capability)
    return services.transition_programme_version(
        db,
        amo_id=amo_id,
        version_id=version_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/metric-definitions", response_model=List[schemas.MetricDefinitionRead])
def metric_definitions(
    programme_version_id: Optional[str] = None,
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_metrics(db, amo_id=amo_id, programme_version_id=programme_version_id)


@router.post("/programme-versions/{version_id}/metrics", response_model=schemas.MetricDefinitionRead, status_code=201)
def create_metric(
    version_id: str,
    payload: schemas.MetricDefinitionCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.metric.manage")
    return services.create_metric_definition(
        db,
        amo_id=amo_id,
        version_id=version_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/threshold-versions", response_model=List[schemas.ThresholdRead])
def threshold_versions(metric_id: Optional[str] = None, context=Depends(_context)):
    _, db, amo_id = context
    return services.list_thresholds(db, amo_id=amo_id, metric_id=metric_id)


@router.post("/metric-definitions/{metric_id}/thresholds", response_model=schemas.ThresholdRead, status_code=201)
def create_threshold(
    metric_id: str,
    payload: schemas.ThresholdCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.metric.manage")
    return services.create_threshold(
        db,
        amo_id=amo_id,
        metric_id=metric_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/threshold-versions/{threshold_id}/transition", response_model=schemas.ThresholdRead)
def transition_threshold(
    threshold_id: str,
    payload: schemas.ThresholdTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    capability = "reliability.programme.approve" if payload.to_status in {"APPROVED", "EFFECTIVE", "SUPERSEDED"} else "reliability.metric.manage"
    services.require_capability(db, current_user, capability)
    return services.transition_threshold(
        db,
        amo_id=amo_id,
        threshold_id=threshold_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/calculation-runs/execute", response_model=schemas.CalculationRunRead)
def execute_calculation(payload: schemas.CalculationExecuteRequest, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.metric.execute")
    return services.execute_metric_by_id(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/calculation-runs/run-due", response_model=List[schemas.CalculationRunRead])
def execute_due_calculations(context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.metric.execute")
    return services.run_due_metrics(db, amo_id=amo_id, actor_user_id=str(current_user.id))


@router.get("/calculation-runs", response_model=List[schemas.CalculationRunRead])
def calculation_runs(
    metric_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_calculation_runs(
        db,
        amo_id=amo_id,
        metric_id=metric_id,
        scope_type=scope_type,
        limit=limit,
    )


@router.get("/analytics", response_model=schemas.AnalyticsResponse)
def analytics(
    scope_type: str = Query(pattern="^(FLEET|AIRCRAFT|ATA|COMPONENT|ENGINE)$"),
    period_start: date = Query(),
    period_end: date = Query(),
    denominator_type: str = Query(default="FH", pattern="^(FH|FC|FLIGHTS|DAYS|POPULATION)$"),
    multiplier: Decimal = Query(default=Decimal("100"), gt=0),
    event_types: Optional[List[str]] = Query(default=None),
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.analytics(
        db,
        amo_id=amo_id,
        scope_type=scope_type,
        period_start=period_start,
        period_end=period_end,
        denominator_type=denominator_type,
        multiplier=multiplier,
        event_types=event_types,
    )


@router.get("/meetings", response_model=List[schemas.MeetingRead])
def meetings(context=Depends(_context)):
    _, db, amo_id = context
    return services.list_meetings(db, amo_id=amo_id)


@router.post("/meetings", response_model=schemas.MeetingRead, status_code=201)
def create_meeting(payload: schemas.MeetingCreate, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.meeting.manage")
    return services.create_meeting(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/meetings/{meeting_id}/transition", response_model=schemas.MeetingRead)
def transition_meeting(
    meeting_id: str,
    payload: schemas.MeetingTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.meeting.manage")
    return services.transition_meeting(
        db,
        amo_id=amo_id,
        meeting_id=meeting_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/meetings/{meeting_id}/decisions", response_model=List[schemas.MeetingDecisionRead])
def meeting_decisions(meeting_id: str, context=Depends(_context)):
    _, db, amo_id = context
    return services.list_meeting_decisions(db, amo_id=amo_id, meeting_id=meeting_id)


@router.post("/meetings/{meeting_id}/decisions", response_model=schemas.MeetingDecisionRead, status_code=201)
def add_meeting_decision(
    meeting_id: str,
    payload: schemas.MeetingDecisionCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.meeting.manage")
    return services.add_meeting_decision(
        db,
        amo_id=amo_id,
        meeting_id=meeting_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/changes", response_model=List[schemas.ChangeProposalRead])
def changes(status: Optional[str] = None, context=Depends(_context)):
    _, db, amo_id = context
    return services.list_changes(db, amo_id=amo_id, change_status=status)


@router.post("/changes", response_model=schemas.ChangeProposalRead, status_code=201)
def create_change(payload: schemas.ChangeProposalCreate, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.change.manage")
    return services.create_change(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/changes/{change_id}/simulate", response_model=schemas.ChangeProposalRead)
def simulate_change(
    change_id: str,
    payload: schemas.ChangeSimulationRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.change.manage")
    return services.simulate_change(
        db,
        amo_id=amo_id,
        change_id=change_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/changes/{change_id}/transition", response_model=schemas.ChangeProposalRead)
def transition_change(
    change_id: str,
    payload: schemas.ChangeTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    capability = "reliability.change.approve" if payload.to_status in {"APPROVED", "AUTHORITY_REVIEW", "IMPLEMENTED", "CLOSED"} else "reliability.change.manage"
    services.require_capability(db, current_user, capability)
    return services.transition_change(
        db,
        amo_id=amo_id,
        change_id=change_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/handoffs", response_model=List[schemas.HandoffRead])
def handoffs(
    target_module: Optional[str] = None,
    status: Optional[str] = None,
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_handoffs(
        db,
        amo_id=amo_id,
        target_module=target_module,
        handoff_status=status,
    )


@router.post("/handoffs", response_model=schemas.HandoffRead, status_code=201)
def create_handoff(payload: schemas.HandoffCreate, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.handoff.manage")
    return services.create_handoff(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/handoffs/{handoff_id}/transition", response_model=schemas.HandoffRead)
def transition_handoff(
    handoff_id: str,
    payload: schemas.HandoffTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.handoff.manage")
    return services.transition_handoff(
        db,
        amo_id=amo_id,
        handoff_id=handoff_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/authority-submissions", response_model=List[schemas.AuthoritySubmissionRead])
def authority_submissions(context=Depends(_context)):
    _, db, amo_id = context
    return services.list_authority_submissions(db, amo_id=amo_id)


@router.post("/authority-submissions", response_model=schemas.AuthoritySubmissionRead, status_code=201)
def create_authority_submission(
    payload: schemas.AuthoritySubmissionCreate,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.authority.prepare")
    return services.create_authority_submission(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/authority-submissions/{submission_id}/transition", response_model=schemas.AuthoritySubmissionRead)
def transition_authority_submission(
    submission_id: str,
    payload: schemas.AuthorityTransitionRequest,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    capability = "reliability.authority.submit" if payload.to_status in {"SUBMITTED", "ACCEPTED", "REJECTED", "WITHDRAWN"} else "reliability.authority.prepare"
    services.require_capability(db, current_user, capability)
    return services.transition_authority_submission(
        db,
        amo_id=amo_id,
        submission_id=submission_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/ai-reviews", response_model=List[schemas.AiReviewRead])
def ai_reviews(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    context=Depends(_context),
):
    _, db, amo_id = context
    return services.list_ai_reviews(
        db,
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@router.post("/ai-reviews", response_model=schemas.AiReviewRead, status_code=201)
def create_ai_review(payload: schemas.AiReviewRequest, context=Depends(_context)):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ai.use")
    return services.create_ai_review(
        db,
        amo_id=amo_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.post("/ai-reviews/{review_id}/decision", response_model=schemas.AiReviewRead)
def decide_ai_review(
    review_id: str,
    payload: schemas.AiReviewDecision,
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.ai.review")
    return services.decide_ai_review(
        db,
        amo_id=amo_id,
        review_id=review_id,
        payload=payload,
        actor_user_id=str(current_user.id),
    )


@router.get("/audit-events", response_model=List[schemas.AuditEventRead])
def audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    context=Depends(_context),
):
    current_user, db, amo_id = context
    services.require_capability(db, current_user, "reliability.audit.read")
    return services.list_audit_events(
        db,
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )


@router.get("/compliance", response_model=schemas.ComplianceOverview)
def compliance(context=Depends(_context)):
    _, db, amo_id = context
    return services.compliance_overview(db, amo_id=amo_id)
