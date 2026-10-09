from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.apps.doc_control import domain_models as document_control_models
from amodb.apps.doc_control.knowledge_assistant_router import search_authorised_controlled_sources
from amodb.apps.manuals import models as manual_models
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_checklist_execution_models import (
    QualityAuditChecklistExecutionEvent,
    QualityAuditChecklistExecutionGovernance,
    QualityAuditFieldworkMutationReceipt,
    QualityAuditApplicabilityFact,
)
from .audit_checklist_response_policy import resolve_response_value
from .compliance_intelligence_service import (
    detect_requirement_conflicts,
    evaluate_applicability,
    evidence_priority,
    normalise_evidence_context,
    normalise_evidence_role,
    precedence_policy,
)
from .audit_evidence_models import QualityAuditEvidenceArtifact
from .audit_checklist_template_models import QualityAuditChecklistBinding
from .audit_preparation_models import QualityAuditPreparationRevision
from .enums import FindingLevel, QMSAuditStatus, QMSFindingSeverity, QMSFindingType
from .service import compute_target_close_date, normalize_finding_level
from .tenant_security import TenantContext, assert_quality_permission_any, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit checklist execution governance"])

CanonicalResponse = Literal["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"]
FindingResponse = Literal["NONCOMPLIANT", "OBSERVATION"]
AssessmentApplicability = Literal["APPLICABLE", "NOT_APPLICABLE", "UNVERIFIED"]
DocumentaryStatus = Literal["DOCUMENTED", "NOT_DOCUMENTED", "PARTIALLY_DOCUMENTED", "CONFLICT", "NOT_EVIDENCED", "UNVERIFIED"]
ImplementationStatus = Literal["OBJECTIVE_EVIDENCE_AVAILABLE", "VERIFIED", "NOT_VERIFIED", "NOT_EVIDENCED", "UNVERIFIED"]
FieldVerificationStatus = Literal["FIELD_VERIFICATION_REQUIRED", "VERIFIED", "NOT_VERIFIED", "NOT_APPLICABLE", "UNVERIFIED"]


class StructuredAIAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: str | None = Field(default=None, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=200)
    missing_evidence: list[str] = Field(default_factory=list, max_length=200)
    conflicts: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    verification_required: list[str] = Field(default_factory=list, max_length=200)
    confidence_basis: str | None = Field(default=None, max_length=4000)


class ChecklistAssessmentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicability: AssessmentApplicability = "UNVERIFIED"
    applicability_reason: str | None = Field(default=None, max_length=4000)
    applicability_basis: list[dict[str, Any] | str] = Field(default_factory=list, max_length=100)
    documentary_status: DocumentaryStatus = "UNVERIFIED"
    implementation_status: ImplementationStatus = "UNVERIFIED"
    field_verification_status: FieldVerificationStatus = "UNVERIFIED"
    evidence_ids: list[str] = Field(default_factory=list, max_length=200)
    document_revision_ids: list[str] = Field(default_factory=list, max_length=100)
    regulation_refs: list[str] = Field(default_factory=list, max_length=200)
    procedure_refs: list[str] = Field(default_factory=list, max_length=200)
    conflicts: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    missing_evidence: list[str] = Field(default_factory=list, max_length=200)
    fieldwork_requirements: list[str] = Field(default_factory=list, max_length=200)
    ai_analysis: StructuredAIAnalysis | None = None
    human_decision: CanonicalResponse | None = None
    human_override_reason: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_structured_state(self):
        if self.applicability == "NOT_APPLICABLE" and (
            not str(self.applicability_reason or "").strip() or not self.applicability_basis
        ):
            raise ValueError("NOT_APPLICABLE requires an explicit applicability reason and preserved applicability basis.")
        if self.documentary_status == "CONFLICT" and not self.conflicts:
            raise ValueError("A CONFLICT documentary status requires at least one preserved conflict reference.")
        if self.field_verification_status == "FIELD_VERIFICATION_REQUIRED" and not self.fieldwork_requirements:
            raise ValueError("FIELD_VERIFICATION_REQUIRED requires explicit fieldwork requirements.")
        return self


class AuditApplicabilityFactCreate(BaseModel):
    applicability_rule_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=8, max_length=4000)


class ChecklistExecutionUpdate(BaseModel):
    canonical_response_status: CanonicalResponse
    response_value: str | None = Field(default=None, max_length=64)
    auditor_notes: str | None = Field(default=None, max_length=12000)
    sampled_item_information: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    assessment: ChecklistAssessmentState | None = None
    reason: str = Field(min_length=8, max_length=4000)


class FieldworkMutation(BaseModel):
    client_mutation_id: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=128)
    device_sequence: int = Field(ge=0)
    client_timestamp: datetime
    base_version: int = Field(ge=0)
    operation: Literal["CHECKLIST_UPDATE"] = "CHECKLIST_UPDATE"
    canonical_response_status: CanonicalResponse
    response_value: str | None = Field(default=None, max_length=64)
    auditor_notes: str | None = Field(default=None, max_length=12000)
    sampled_item_information: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    assessment: ChecklistAssessmentState | None = None
    reason: str = Field(min_length=8, max_length=4000)


class FieldworkFindingMutation(BaseModel):
    client_mutation_id: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=128)
    device_sequence: int = Field(ge=0)
    client_timestamp: datetime
    base_version: int = Field(ge=0)
    operation: Literal["CREATE_FINDING"] = "CREATE_FINDING"
    canonical_response_status: FindingResponse
    response_value: str | None = Field(default=None, max_length=64)
    severity: QMSFindingSeverity
    level: FindingLevel
    requirement_ref: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=8, max_length=12000)
    objective_evidence: str | None = Field(default=None, max_length=12000)
    safety_sensitive: bool = False
    target_close_date: date | None = None
    auditor_notes: str | None = Field(default=None, max_length=12000)
    sampled_item_information: str | None = Field(default=None, max_length=12000)
    evidence_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=200)
    assessment: ChecklistAssessmentState | None = None
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_client_timestamp(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _canonical_from_legacy(value: str | None) -> CanonicalResponse:
    normalized = str(value or "PENDING").upper()
    if normalized == "NON_CONFORMING":
        return "NONCOMPLIANT"
    if normalized in {"COMPLIANT", "OBSERVATION", "NOT_APPLICABLE"}:
        return normalized  # type: ignore[return-value]
    return "NOT_VERIFIED"


def _legacy_from_canonical(value: CanonicalResponse) -> str:
    if value == "NONCOMPLIANT":
        return "NON_CONFORMING"
    if value == "NOT_VERIFIED":
        return "PENDING"
    return value


def _item(db: Session, *, amo_id: str, audit_id: uuid.UUID, item_id: uuid.UUID, lock: bool = False) -> models.QualityAuditChecklistItem:
    query = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
        models.QualityAuditChecklistItem.id == item_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit checklist item not found.")
    return row


def _assessment_dict(row: QualityAuditChecklistExecutionGovernance) -> dict[str, Any]:
    return {
        "applicability": row.assessment_applicability,
        "applicability_reason": row.applicability_reason,
        "applicability_basis": list(row.applicability_basis or []),
        "documentary_status": row.documentary_status,
        "implementation_status": row.implementation_status,
        "field_verification_status": row.field_verification_status,
        "evidence_ids": list(row.evidence_ids or []),
        "document_revision_ids": list(row.document_revision_ids or []),
        "regulation_refs": list(row.regulation_refs or []),
        "procedure_refs": list(row.procedure_refs or []),
        "conflicts": list(row.conflicts or []),
        "missing_evidence": list(row.missing_evidence or []),
        "fieldwork_requirements": list(row.fieldwork_requirements or []),
        "ai_analysis": dict(row.ai_analysis or {}) if row.ai_analysis else None,
        "human_decision": row.human_decision,
        "human_override_reason": row.human_override_reason,
    }


def _validate_assessment_links(
    db: Session,
    *,
    ctx: TenantContext,
    item: models.QualityAuditChecklistItem,
    assessment: ChecklistAssessmentState | None,
    canonical_response_status: CanonicalResponse,
) -> None:
    if assessment is None:
        return

    if assessment.human_decision is not None and assessment.human_decision != canonical_response_status:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_HUMAN_DECISION_MISMATCH",
                "message": "The structured human decision must match the authoritative checklist response.",
            },
        )
    if assessment.applicability == "NOT_APPLICABLE" and canonical_response_status != "NOT_APPLICABLE":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_APPLICABILITY_MISMATCH",
                "message": "A not-applicable assessment must use the NOT_APPLICABLE checklist response.",
            },
        )

    evidence_ids = {str(value).strip() for value in assessment.evidence_ids if str(value).strip()}
    if assessment.ai_analysis:
        ai_evidence_ids = {
            str(value).strip()
            for value in assessment.ai_analysis.evidence_ids
            if str(value).strip()
        }
        if not ai_evidence_ids.issubset(evidence_ids):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CHECKLIST_AI_EVIDENCE_NOT_LINKED",
                    "message": "AI analysis may cite only evidence IDs explicitly linked to this checklist item.",
                },
            )
    if evidence_ids:
        resolved = {
            str(value)
            for (value,) in db.query(QualityAuditEvidenceArtifact.id).filter(
                QualityAuditEvidenceArtifact.amo_id == ctx.amo_id,
                QualityAuditEvidenceArtifact.audit_id == item.audit_id,
                QualityAuditEvidenceArtifact.checklist_item_id == item.id,
                QualityAuditEvidenceArtifact.id.in_(sorted(evidence_ids)),
            ).all()
        }
        source_ids = evidence_ids - resolved
        # Current audit assessment is fail-closed: documentary evidence must
        # resolve to the tenant's current published revision. Historical audit
        # reconstruction is served from the immutable bound assessment/archive
        # state; callers may not introduce a superseded/archived revision into
        # a current checklist decision merely because that revision still exists.
        allowed_states = {
            manual_models.ManualRevisionStatus.PUBLISHED,
        }
        for source_id in sorted(source_ids):
            parts = source_id.split(":")
            valid = False
            if len(parts) == 3 and parts[0] == "section":
                revision_id, section_id = parts[1], parts[2]
                valid = db.query(manual_models.ManualSection.id).join(
                    manual_models.ManualRevision,
                    manual_models.ManualRevision.id == manual_models.ManualSection.revision_id,
                ).join(
                    manual_models.Manual,
                    manual_models.Manual.id == manual_models.ManualRevision.manual_id,
                ).join(
                    manual_models.Tenant,
                    manual_models.Tenant.id == manual_models.Manual.tenant_id,
                ).filter(
                    manual_models.Tenant.amo_id == ctx.amo_id,
                    manual_models.ManualSection.id == section_id,
                    manual_models.ManualSection.revision_id == revision_id,
                    manual_models.ManualRevision.status_enum.in_(allowed_states),
                ).first() is not None
            elif len(parts) == 3 and parts[0] == "document":
                manual_id, revision_id = parts[1], parts[2]
                valid = db.query(manual_models.ManualRevision.id).join(
                    manual_models.Manual,
                    manual_models.Manual.id == manual_models.ManualRevision.manual_id,
                ).join(
                    manual_models.Tenant,
                    manual_models.Tenant.id == manual_models.Manual.tenant_id,
                ).filter(
                    manual_models.Tenant.amo_id == ctx.amo_id,
                    manual_models.Manual.id == manual_id,
                    manual_models.ManualRevision.id == revision_id,
                    manual_models.ManualRevision.status_enum.in_(allowed_states),
                ).first() is not None
            if valid:
                resolved.add(source_id)

        missing = sorted(evidence_ids - resolved)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CHECKLIST_EVIDENCE_ID_INVALID",
                    "message": "Assessment evidence IDs must resolve to this checklist's immutable evidence or a controlled tenant document source.",
                    "invalid_evidence_ids": missing,
                },
            )

    revision_ids = {str(value).strip() for value in assessment.document_revision_ids if str(value).strip()}
    if revision_ids:
        revisions = (
            db.query(manual_models.ManualRevision)
            .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
            .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
            .filter(
                manual_models.Tenant.amo_id == ctx.amo_id,
                manual_models.ManualRevision.id.in_(sorted(revision_ids)),
            )
            .all()
        )
        resolved_ids = {str(row.id) for row in revisions}
        missing = sorted(revision_ids - resolved_ids)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CHECKLIST_DOCUMENT_REVISION_INVALID",
                    "message": "Assessment document revisions must belong to the current tenant.",
                    "invalid_document_revision_ids": missing,
                },
            )
        # Current audit assessment is fail-closed: documentary evidence must
        # resolve to the tenant's current published revision. Historical audit
        # reconstruction is served from the immutable bound assessment/archive
        # state; callers may not introduce a superseded/archived revision into
        # a current checklist decision merely because that revision still exists.
        allowed_states = {
            manual_models.ManualRevisionStatus.PUBLISHED,
        }
        invalid_states = [
            {"revision_id": str(row.id), "status": str(getattr(row.status_enum, "value", row.status_enum))}
            for row in revisions
            if row.status_enum not in allowed_states
        ]
        if invalid_states:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CHECKLIST_DOCUMENT_REVISION_NOT_CONTROLLED",
                    "message": "Draft or unapproved revisions cannot be used as compliance evidence.",
                    "revisions": invalid_states,
                },
            )

    _validate_detected_document_conflicts(
        db,
        ctx=ctx,
        assessment=assessment,
        canonical_response_status=canonical_response_status,
    )
    _validate_assessment_citations(
        db,
        ctx=ctx,
        item=item,
        assessment=assessment,
    )


def _selected_documentary_conflicts(
    db: Session,
    *,
    ctx: TenantContext,
    evidence_ids: set[str],
) -> list[dict[str, Any]]:
    section_pairs: list[tuple[str, str]] = []
    document_pairs: list[tuple[str, str]] = []
    for evidence_id in evidence_ids:
        parts = evidence_id.split(":")
        if len(parts) != 3:
            continue
        if parts[0] == "section":
            section_pairs.append((parts[1], parts[2]))
        elif parts[0] == "document":
            document_pairs.append((parts[1], parts[2]))

    candidates: list[dict[str, Any]] = []
    if section_pairs:
        section_ids = [section_id for _revision_id, section_id in section_pairs]
        rows = (
            db.query(manual_models.ManualSection, manual_models.Manual, manual_models.ManualRevision)
            .join(manual_models.ManualRevision, manual_models.ManualRevision.id == manual_models.ManualSection.revision_id)
            .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
            .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
            .filter(
                manual_models.Tenant.amo_id == ctx.amo_id,
                manual_models.ManualSection.id.in_(section_ids),
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
            )
            .all()
        )
        valid = {
            (str(revision.id), str(section.id)): (section, manual, revision)
            for section, manual, revision in rows
        }
        blocks_by_section: dict[str, list[str]] = {}
        if valid:
            for block in (
                db.query(manual_models.ManualBlock)
                .filter(manual_models.ManualBlock.section_id.in_([key[1] for key in valid]))
                .order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc())
                .all()
            ):
                text_value = str(block.text_plain or "").strip()
                if text_value:
                    blocks_by_section.setdefault(str(block.section_id), []).append(text_value)
        for revision_id, section_id in section_pairs:
            resolved = valid.get((revision_id, section_id))
            if resolved is None:
                continue
            section, manual, _revision = resolved
            candidates.append({
                "evidence_id": f"section:{revision_id}:{section_id}",
                "reference": " · ".join(value for value in (manual.code, section.heading) if value),
                "source_text": "\n".join(blocks_by_section.get(section_id, [])),
            })

    for manual_id, revision_id in document_pairs:
        resolved = (
            db.query(manual_models.Manual, manual_models.ManualRevision)
            .join(manual_models.ManualRevision, manual_models.ManualRevision.manual_id == manual_models.Manual.id)
            .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
            .filter(
                manual_models.Tenant.amo_id == ctx.amo_id,
                manual_models.Manual.id == manual_id,
                manual_models.ManualRevision.id == revision_id,
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
            )
            .first()
        )
        if resolved is None:
            continue
        manual, revision = resolved
        blocks = (
            db.query(manual_models.ManualBlock.text_plain)
            .join(manual_models.ManualSection, manual_models.ManualSection.id == manual_models.ManualBlock.section_id)
            .filter(manual_models.ManualSection.revision_id == revision.id)
            .order_by(manual_models.ManualSection.order_index.asc(), manual_models.ManualBlock.order_index.asc())
            .limit(2000)
            .all()
        )
        candidates.append({
            "evidence_id": f"document:{manual_id}:{revision_id}",
            "reference": " · ".join(value for value in (manual.code, manual.title) if value),
            "source_text": "\n".join(str(value or "") for (value,) in blocks if str(value or "").strip()),
        })

    return detect_requirement_conflicts(candidates)


def _validate_detected_document_conflicts(
    db: Session,
    *,
    ctx: TenantContext,
    assessment: ChecklistAssessmentState,
    canonical_response_status: CanonicalResponse,
) -> None:
    evidence_ids = {str(value).strip() for value in assessment.evidence_ids if str(value).strip()}
    detected = _selected_documentary_conflicts(db, ctx=ctx, evidence_ids=evidence_ids)
    if not detected:
        return
    if assessment.documentary_status != "CONFLICT":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_DOCUMENT_CONFLICT_UNRESOLVED",
                "message": "Selected controlled evidence contains a deterministic document conflict. Preserve it as CONFLICT before recording the checklist decision.",
                "conflicts": detected,
            },
        )

    preserved = json.dumps(assessment.conflicts, sort_keys=True, default=str)
    unpreserved = [
        conflict
        for conflict in detected
        if any(
            str(source.get("evidence_id") or "") not in preserved
            for source in conflict.get("sources", [])
        )
    ]
    if unpreserved:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_DOCUMENT_CONFLICT_NOT_PRESERVED",
                "message": "Every detected competing controlled statement must remain traceable in the stored assessment.",
                "conflicts": unpreserved,
            },
        )
    if canonical_response_status == "COMPLIANT" and not str(assessment.human_override_reason or "").strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_CONFLICT_COMPLIANT_REASON_REQUIRED",
                "message": "A compliant human decision against preserved conflicting controlled evidence requires an explicit auditor resolution/override rationale.",
            },
        )


def _normalise_citation_token(value: Any) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _validate_assessment_citations(
    db: Session,
    *,
    ctx: TenantContext,
    item: models.QualityAuditChecklistItem,
    assessment: ChecklistAssessmentState,
) -> None:
    citations = [
        ("procedure_ref", str(value).strip())
        for value in assessment.procedure_refs
        if str(value).strip()
    ] + [
        ("regulation_ref", str(value).strip())
        for value in assessment.regulation_refs
        if str(value).strip()
    ]
    if not citations:
        return

    evidence_ids = {str(value).strip() for value in assessment.evidence_ids if str(value).strip()}
    section_pairs: list[tuple[str, str]] = []
    document_pairs: list[tuple[str, str]] = []
    for evidence_id in evidence_ids:
        parts = evidence_id.split(":")
        if len(parts) != 3:
            continue
        if parts[0] == "section":
            section_pairs.append((parts[1], parts[2]))
        elif parts[0] == "document":
            document_pairs.append((parts[1], parts[2]))

    corpus_parts: list[str] = []
    definition = _frozen_item_definition_map(
        db,
        amo_id=ctx.amo_id,
        audit_id=item.audit_id,
    ).get(str(item.id), {})
    corpus_parts.extend(
        str(value or "")
        for value in (
            item.requirement_ref,
            item.checklist_ref,
            definition.get("regulatory_source_ref"),
            definition.get("manual_source_ref"),
        )
        if str(value or "").strip()
    )

    section_ids = [section_id for _revision_id, section_id in section_pairs]
    if section_ids:
        sections = (
            db.query(manual_models.ManualSection, manual_models.Manual, manual_models.ManualRevision)
            .join(manual_models.ManualRevision, manual_models.ManualRevision.id == manual_models.ManualSection.revision_id)
            .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
            .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
            .filter(
                manual_models.Tenant.amo_id == ctx.amo_id,
                manual_models.ManualSection.id.in_(section_ids),
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
            )
            .all()
        )
        valid_pairs = {(str(revision.id), str(section.id)) for section, _manual, revision in sections}
        allowed_pairs = set(section_pairs)
        for section, manual, revision in sections:
            if (str(revision.id), str(section.id)) not in allowed_pairs:
                continue
            metadata = dict(section.metadata_json or {})
            section_number = str(metadata.get("section_number") or "").strip()
            corpus_parts.extend([
                manual.code or "",
                manual.title or "",
                section.heading or "",
                f"{manual.code or ''} {section.heading or ''}".strip(),
                f"{manual.code or ''} {section_number}".strip() if section_number else "",
            ])
        blocks = (
            db.query(manual_models.ManualBlock)
            .filter(manual_models.ManualBlock.section_id.in_([pair[1] for pair in valid_pairs]))
            .order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc())
            .all()
        )
        corpus_parts.extend(str(block.text_plain or "") for block in blocks if str(block.text_plain or "").strip())

    for manual_id, revision_id in document_pairs:
        row = (
            db.query(manual_models.Manual, manual_models.ManualRevision)
            .join(manual_models.ManualRevision, manual_models.ManualRevision.manual_id == manual_models.Manual.id)
            .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
            .filter(
                manual_models.Tenant.amo_id == ctx.amo_id,
                manual_models.Manual.id == manual_id,
                manual_models.ManualRevision.id == revision_id,
                manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
            )
            .first()
        )
        if row is None:
            continue
        manual, revision = row
        corpus_parts.extend([manual.code or "", manual.title or "", revision.rev_number or ""])
        headings = db.query(
            manual_models.ManualSection.heading,
            manual_models.ManualSection.metadata_json,
        ).filter(
            manual_models.ManualSection.revision_id == revision.id
        ).limit(500).all()
        for heading, metadata_json in headings:
            heading_value = str(heading or "").strip()
            section_number = str(dict(metadata_json or {}).get("section_number") or "").strip()
            if heading_value:
                corpus_parts.extend([
                    heading_value,
                    f"{manual.code or ''} {heading_value}".strip(),
                ])
            if section_number:
                corpus_parts.append(f"{manual.code or ''} {section_number}".strip())

    corpus = _normalise_citation_token(" ".join(corpus_parts))
    unsupported = [
        {"type": kind, "reference": reference}
        for kind, reference in citations
        if len(_normalise_citation_token(reference)) >= 2
        and _normalise_citation_token(reference) not in corpus
    ]
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_CITATION_UNSUPPORTED",
                "message": "Every stored regulation/procedure citation must be supported by the frozen checklist source or linked current-approved documentary evidence.",
                "unsupported_references": unsupported,
            },
        )


def _apply_assessment_state(
    governance: QualityAuditChecklistExecutionGovernance,
    assessment: ChecklistAssessmentState | None,
    canonical_response_status: CanonicalResponse,
) -> None:
    if assessment is None:
        return
    governance.assessment_applicability = assessment.applicability
    governance.applicability_reason = assessment.applicability_reason.strip() if assessment.applicability_reason else None
    governance.applicability_basis = list(assessment.applicability_basis)
    governance.documentary_status = assessment.documentary_status
    governance.implementation_status = assessment.implementation_status
    governance.field_verification_status = assessment.field_verification_status
    governance.evidence_ids = list(dict.fromkeys(assessment.evidence_ids))
    governance.document_revision_ids = list(dict.fromkeys(assessment.document_revision_ids))
    governance.regulation_refs = list(dict.fromkeys(assessment.regulation_refs))
    governance.procedure_refs = list(dict.fromkeys(assessment.procedure_refs))
    governance.conflicts = list(assessment.conflicts)
    governance.missing_evidence = list(dict.fromkeys(assessment.missing_evidence))
    governance.fieldwork_requirements = list(dict.fromkeys(assessment.fieldwork_requirements))
    governance.ai_analysis = assessment.ai_analysis.model_dump(mode="json") if assessment.ai_analysis else None
    governance.human_decision = assessment.human_decision or canonical_response_status
    governance.human_override_reason = (
        assessment.human_override_reason.strip() if assessment.human_override_reason else None
    )


def _governance_snapshot(row: QualityAuditChecklistExecutionGovernance) -> dict[str, Any]:
    return {
        "canonical_response_status": row.canonical_response_status,
        "response_value": row.response_value,
        "auditor_notes": row.auditor_notes,
        "auditee_comments": row.auditee_comments,
        "sampled_item_information": row.sampled_item_information,
        "applicability": row.applicability,
        "evidence_references": list(row.evidence_references or []),
        "assessment": _assessment_dict(row),
        "entity_version": int(row.entity_version or 1),
        "answered_by_user_id": row.answered_by_user_id,
        "answered_at": row.answered_at,
        "updated_by_user_id": row.updated_by_user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_dict(row: QualityAuditChecklistExecutionEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "before_snapshot": row.before_snapshot,
        "after_snapshot": row.after_snapshot,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _row_dict(item: models.QualityAuditChecklistItem, governance: QualityAuditChecklistExecutionGovernance | None) -> dict[str, Any]:
    canonical = governance.canonical_response_status if governance else _canonical_from_legacy(item.response_status)
    return {
        "checklist_item_id": str(item.id),
        "audit_id": str(item.audit_id),
        "section": item.section,
        "checklist_ref": item.checklist_ref,
        "requirement_ref": item.requirement_ref,
        "prompt": item.prompt,
        "legacy_response_status": item.response_status,
        "canonical_response_status": canonical,
        "response_value": governance.response_value if governance else None,
        "objective_evidence": item.objective_evidence,
        "finding_id": str(item.finding_id) if item.finding_id else None,
        "auditor_notes": governance.auditor_notes if governance else None,
        "auditee_comments": governance.auditee_comments if governance else None,
        "sampled_item_information": governance.sampled_item_information if governance else None,
        "applicability": governance.applicability if governance else "APPLICABLE",
        "evidence_references": list(governance.evidence_references or []) if governance else [],
        "assessment": _assessment_dict(governance) if governance else {
            "applicability": "UNVERIFIED",
            "applicability_reason": None,
            "applicability_basis": [],
            "documentary_status": "UNVERIFIED",
            "implementation_status": "UNVERIFIED",
            "field_verification_status": "UNVERIFIED",
            "evidence_ids": [],
            "document_revision_ids": [],
            "regulation_refs": [],
            "procedure_refs": [],
            "conflicts": [],
            "missing_evidence": [],
            "fieldwork_requirements": [],
            "ai_analysis": None,
            "human_decision": None,
            "human_override_reason": None,
        },
        "governance_id": str(governance.id) if governance else None,
        "entity_version": int(governance.entity_version or 1) if governance else 0,
        "updated_by_user_id": governance.updated_by_user_id if governance else item.completed_by_user_id,
        "updated_at": governance.updated_at if governance else item.updated_at,
        "events": [_event_dict(event) for event in list(governance.events or [])] if governance else [],
    }


def _apply_execution_update(
    db: Session,
    *,
    ctx: TenantContext,
    item: models.QualityAuditChecklistItem,
    payload: ChecklistExecutionUpdate,
    governance: QualityAuditChecklistExecutionGovernance | None,
) -> QualityAuditChecklistExecutionGovernance:
    _validate_assessment_links(
        db,
        ctx=ctx,
        item=item,
        assessment=payload.assessment,
        canonical_response_status=payload.canonical_response_status,
    )
    event_type = "UPDATED"
    before_snapshot: dict[str, Any] | None
    if governance is None:
        event_type = "CREATED"
        before_snapshot = {
            "canonical_response_status": _canonical_from_legacy(item.response_status),
            "response_value": None,
            "auditor_notes": None,
            "evidence_references": [],
            "entity_version": 0,
            "legacy_response_status": item.response_status,
        }
        governance = QualityAuditChecklistExecutionGovernance(
            amo_id=ctx.amo_id,
            audit_id=item.audit_id,
            checklist_item_id=item.id,
            canonical_response_status=payload.canonical_response_status,
            response_value=payload.response_value,
            auditor_notes=payload.auditor_notes.strip() if payload.auditor_notes else None,
            sampled_item_information=payload.sampled_item_information.strip() if payload.sampled_item_information else None,
            applicability=str(_frozen_item_definition_map(db, amo_id=ctx.amo_id, audit_id=item.audit_id).get(str(item.id), {}).get("applicability") or "APPLICABLE")[:128],
            evidence_references=list(payload.evidence_references),
            entity_version=1,
            answered_by_user_id=ctx.user_id if payload.canonical_response_status != "NOT_VERIFIED" else None,
            answered_at=_utcnow() if payload.canonical_response_status != "NOT_VERIFIED" else None,
            updated_by_user_id=ctx.user_id,
        )
        _apply_assessment_state(governance, payload.assessment, payload.canonical_response_status)
        db.add(governance)
        db.flush()
    else:
        before_snapshot = _governance_snapshot(governance)
        governance.canonical_response_status = payload.canonical_response_status
        if payload.response_value is not None:
            governance.response_value = payload.response_value
        governance.auditor_notes = payload.auditor_notes.strip() if payload.auditor_notes else None
        if payload.sampled_item_information is not None:
            governance.sampled_item_information = payload.sampled_item_information.strip() or None
        governance.applicability = str(_frozen_item_definition_map(db, amo_id=ctx.amo_id, audit_id=item.audit_id).get(str(item.id), {}).get("applicability") or governance.applicability or "APPLICABLE")[:128]
        governance.evidence_references = list(payload.evidence_references)
        _apply_assessment_state(governance, payload.assessment, payload.canonical_response_status)
        governance.entity_version = int(governance.entity_version or 1) + 1
        governance.updated_by_user_id = ctx.user_id
        governance.updated_at = _utcnow()

    legacy_status = _legacy_from_canonical(payload.canonical_response_status)
    item.response_status = legacy_status
    if payload.canonical_response_status == "NOT_VERIFIED":
        item.completed_by_user_id = None
        item.completed_at = None
    else:
        item.completed_by_user_id = ctx.user_id
        item.completed_at = _utcnow()
    item.updated_at = _utcnow()

    after_snapshot = {
        **_governance_snapshot(governance),
        "legacy_response_status": legacy_status,
        "objective_evidence": item.objective_evidence,
        "finding_id": str(item.finding_id) if item.finding_id else None,
    }
    db.add(QualityAuditChecklistExecutionEvent(
        amo_id=ctx.amo_id,
        audit_id=item.audit_id,
        checklist_item_id=item.id,
        governance_id=governance.id,
        event_type=event_type,
        reason=payload.reason.strip(),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        actor_user_id=ctx.user_id,
    ))
    return governance


def _mutation_hash(payload: BaseModel) -> str:
    encoded = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _publish_persisted_event(row: audit_models.AuditEvent) -> None:
    try:
        timestamp = (row.occurred_at or row.created_at or _utcnow()).isoformat()
        publish_event(EventEnvelope(
            id=str(row.id),
            type=f"{row.entity_type}.{row.action}".lower(),
            entityType=row.entity_type,
            entityId=row.entity_id,
            action=row.action,
            timestamp=timestamp,
            actor={"userId": row.actor_user_id} if row.actor_user_id else None,
            metadata={"amoId": row.amo_id, **(row.metadata_json or {})},
        ))
    except Exception:
        return


def _fieldwork_write_blocker(db: Session, *, amo_id: str, audit: models.QMSAudit) -> str | None:
    status_value = str(getattr(audit.status, "value", audit.status) or "").upper()
    if status_value == "CLOSED" or audit.actual_end is not None:
        return "Fieldwork is complete and read-only. Reopen the governed audit lifecycle before recording further work."
    prepared = db.query(QualityAuditPreparationRevision).filter(
        QualityAuditPreparationRevision.amo_id == amo_id,
        QualityAuditPreparationRevision.audit_id == audit.id,
    ).order_by(QualityAuditPreparationRevision.revision_no.desc()).first()
    if prepared is None or prepared.status != "ISSUED":
        return "Issue the controlled preparation revision before checklist execution, evidence capture, or finding creation."
    from .audit_preparation_router import _capture_sources, _preparation_readiness_blockers

    current = _capture_sources(db, amo_id=amo_id, audit=audit)
    if _preparation_readiness_blockers(current, phase="FIELDWORK"):
        return "Preparation is incomplete. Resolve every document request governed as required before fieldwork before checklist execution continues."
    if prepared.source_fingerprint != current["source_fingerprint"]:
        return "Preparation changed after its last issue. Create and issue a fresh controlled preparation revision before fieldwork continues."
    return None


def _require_fieldwork_write_window(db: Session, *, amo_id: str, audit: models.QMSAudit) -> None:
    blocker = _fieldwork_write_blocker(db, amo_id=amo_id, audit=audit)
    if blocker:
        raise HTTPException(
            status_code=409,
            detail={"code": "FIELDWORK_LIFECYCLE_BLOCKED", "message": blocker},
        )


def _mark_fieldwork_started(audit: models.QMSAudit) -> None:
    if audit.actual_start is None:
        audit.actual_start = date.today()
    if audit.status == QMSAuditStatus.PLANNED:
        audit.status = QMSAuditStatus.IN_PROGRESS


def _internal_fieldwork_viewer(db: Session, *, ctx: TenantContext, audit_id: uuid.UUID, lock: bool = False):
    from . import router as quality_router

    audit_query = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    )
    if lock:
        audit_query = audit_query.with_for_update()
    audit = audit_query.first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    user = db.query(account_models.User).filter(
        account_models.User.id == ctx.user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=403, detail="Active internal Quality identity is required.")
    if not quality_router._is_quality_admin(user) and not quality_router._audit_allows_user_by_audit(audit, user.id):
        raise HTTPException(status_code=403, detail="Private fieldwork is limited to the assigned audit team and Quality management.")
    return audit, user, quality_router


def _internal_fieldwork_actor(db: Session, *, ctx: TenantContext, audit_id: uuid.UUID):
    audit, user, quality_router = _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id, lock=True)
    quality_router._require_audit_fieldwork_write_access(user, audit)
    _require_fieldwork_write_window(db, amo_id=ctx.amo_id, audit=audit)
    _mark_fieldwork_started(audit)
    return audit, user, quality_router


def _finding_classification(payload: FieldworkFindingMutation) -> tuple[FindingLevel, QMSFindingType]:
    requested_type = QMSFindingType.OBSERVATION if payload.canonical_response_status == "OBSERVATION" else QMSFindingType.NON_CONFORMITY
    level = normalize_finding_level(payload.severity, payload.level, requested_type)
    finding_type = QMSFindingType.OBSERVATION if level == FindingLevel.LEVEL_4 else QMSFindingType.NON_CONFORMITY
    if payload.canonical_response_status == "OBSERVATION" and finding_type != QMSFindingType.OBSERVATION:
        raise HTTPException(status_code=422, detail="An OBSERVATION checklist response must use the governed Level 4 observation classification.")
    if payload.canonical_response_status == "NONCOMPLIANT" and finding_type != QMSFindingType.NON_CONFORMITY:
        raise HTTPException(status_code=422, detail="A NONCOMPLIANT checklist response must use a governed Level 1, 2 or 3 non-conformity classification.")
    return level, finding_type


def _existing_receipt_or_none(
    db: Session,
    *,
    ctx: TenantContext,
    client_mutation_id: str,
    payload_hash: str,
) -> QualityAuditFieldworkMutationReceipt | None:
    existing = db.query(QualityAuditFieldworkMutationReceipt).filter(
        QualityAuditFieldworkMutationReceipt.amo_id == ctx.amo_id,
        QualityAuditFieldworkMutationReceipt.client_mutation_id == client_mutation_id,
    ).first()
    if existing is not None and existing.payload_hash != payload_hash:
        message = "This client mutation id was already used with different fieldwork content."
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELDWORK_IDEMPOTENCY_CONFLICT",
                "error_code": "FIELDWORK_IDEMPOTENCY_CONFLICT",
                "message": message,
                "detail": message,
                "retryable": False,
                "client_mutation_id": client_mutation_id,
            },
        )
    return existing


def _locked_governance(
    db: Session,
    *,
    ctx: TenantContext,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
) -> QualityAuditChecklistExecutionGovernance | None:
    return db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        QualityAuditChecklistExecutionGovernance.checklist_item_id == item_id,
    ).with_for_update().first()


def _frozen_item_definition_map(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
) -> dict[str, dict[str, Any]]:
    """Resolve the complete frozen checklist definition for every instantiated item."""
    result: dict[str, dict[str, Any]] = {}
    bindings = db.query(QualityAuditChecklistBinding).filter(
        QualityAuditChecklistBinding.amo_id == amo_id,
        QualityAuditChecklistBinding.audit_id == audit_id,
    ).order_by(QualityAuditChecklistBinding.applied_at.asc()).all()
    for binding in bindings:
        ids = [str(value) for value in list(binding.instantiated_item_ids or [])]
        snapshot = list(binding.item_snapshot or [])
        for index, item_key in enumerate(ids):
            row = snapshot[index] if index < len(snapshot) and isinstance(snapshot[index], dict) else {}
            result[item_key] = dict(row)
    return result


def _frozen_response_policy_map(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    """Resolve frozen response vocabularies for all bound checklist items in one query."""
    return {
        item_key: (
            str(row.get("response_type") or "COMPLIANCE"),
            list(row.get("response_options") or []),
        )
        for item_key, row in _frozen_item_definition_map(
            db,
            amo_id=amo_id,
            audit_id=audit_id,
        ).items()
    }


def _frozen_response_policy(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
) -> tuple[str, list[dict[str, Any]]]:
    """Resolve the response vocabulary frozen with the checklist binding."""
    return _frozen_response_policy_map(db, amo_id=amo_id, audit_id=audit_id).get(
        str(item_id),
        ("COMPLIANCE", []),
    )


def _validate_frozen_item_requirements(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    canonical_status: str,
    auditor_notes: str | None,
    evidence_references: list[dict[str, Any] | str],
) -> None:
    item_definition = _frozen_item_definition_map(
        db,
        amo_id=amo_id,
        audit_id=audit_id,
    ).get(str(item_id), {})
    status_value = str(canonical_status or "").upper()
    notes_required = {
        str(value).upper()
        for value in list(item_definition.get("notes_required_when") or [])
    }
    evidence_required = {
        str(value).upper()
        for value in list(item_definition.get("evidence_required_when") or [])
    }
    note_present = bool(str(auditor_notes or "").strip())
    evidence_present = bool(list(evidence_references or []))

    if status_value == "NOT_APPLICABLE" and bool(item_definition.get("na_justification_required")) and not note_present:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_NA_JUSTIFICATION_REQUIRED",
                "message": "This governed checklist item requires an auditor reason before it can be marked not applicable.",
            },
        )
    if status_value in notes_required and not note_present:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_NOTES_REQUIRED",
                "message": f"This governed checklist item requires auditor notes for {status_value.replace('_', ' ').lower()}.",
            },
        )
    if status_value in evidence_required and not evidence_present:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CHECKLIST_EVIDENCE_REQUIRED",
                "message": f"This governed checklist item requires linked evidence for {status_value.replace('_', ' ').lower()}.",
            },
        )


def _validated_response_value(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    response_value: str | None,
    canonical_status: str,
) -> str:
    response_type, response_options = _frozen_response_policy(
        db,
        amo_id=amo_id,
        audit_id=audit_id,
        item_id=item_id,
    )
    try:
        return resolve_response_value(
            response_type=response_type,
            response_options=response_options,
            response_value=response_value,
            canonical_status=canonical_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _assert_base_version(
    *,
    payload_base_version: int,
    client_mutation_id: str,
    item: models.QualityAuditChecklistItem,
    governance: QualityAuditChecklistExecutionGovernance | None,
) -> int:
    current_version = int(governance.entity_version or 1) if governance is not None else 0
    if payload_base_version != current_version:
        message = "This checklist item changed after the device copy was read. Review the server version before retrying."
        raise HTTPException(
            status_code=409,
            detail={
                "code": "FIELDWORK_VERSION_CONFLICT",
                "error_code": "FIELDWORK_VERSION_CONFLICT",
                "message": message,
                "detail": message,
                "retryable": True,
                "client_mutation_id": client_mutation_id,
                "base_version": payload_base_version,
                "server_version": current_version,
                "server_row": jsonable_encoder(_row_dict(item, governance)),
            },
        )
    return current_version


def _fieldwork_event(
    *,
    ctx: TenantContext,
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    client_mutation_id: str,
    device_id: str,
    device_sequence: int,
    client_timestamp: datetime,
    current_version: int,
    committed_version: int,
    response: str,
) -> audit_models.AuditEvent:
    return audit_models.AuditEvent(
        amo_id=ctx.amo_id,
        entity_type="qms.audit.checklist_item",
        entity_id=str(item_id),
        action="UPDATED",
        actor_user_id=ctx.user_id,
        before={"entity_version": current_version},
        after={"entity_version": committed_version, "canonical_response_status": response},
        correlation_id=client_mutation_id,
        metadata_json={
            "module": "quality",
            "auditId": str(audit_id),
            "checklistItemId": str(item_id),
            "clientMutationId": client_mutation_id,
            "deviceId": device_id,
            "deviceSequence": device_sequence,
            "clientTimestamp": _normalise_client_timestamp(client_timestamp).isoformat(),
            "entityVersion": committed_version,
        },
    )


@router.get("/audits/{audit_id}/checklist-execution-governance")
def list_checklist_execution_governance(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == ctx.amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
    ).order_by(models.QualityAuditChecklistItem.section.asc(), models.QualityAuditChecklistItem.sort_order.asc()).limit(1000).all()
    governance_rows = db.query(QualityAuditChecklistExecutionGovernance).options(
        selectinload(QualityAuditChecklistExecutionGovernance.events)
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
    ).all()
    by_item = {row.checklist_item_id: row for row in governance_rows}
    return {
        "items": [_row_dict(item, by_item.get(item.id)) for item in items],
        "canonical_response_values": ["COMPLIANT", "NONCOMPLIANT", "OBSERVATION", "NOT_APPLICABLE", "NOT_VERIFIED"],
        "legacy_compatibility": {
            "NONCOMPLIANT": "NON_CONFORMING",
            "NOT_VERIFIED": "PENDING",
        },
    }


def _applicability_fact_dict(row: QualityAuditApplicabilityFact) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "applicability_rule_id": row.applicability_rule_id,
        "source_manual_id": row.source_manual_id,
        "source_revision_id": row.source_revision_id,
        "rule_type": row.rule_type,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "target_value": row.target_value,
        "source": row.source,
        "criteria": dict(row.criteria_json or {}),
        "reason": row.reason,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    }


def _applicability_rule_dict(row: document_control_models.DocumentApplicabilityRule) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "rule_type": row.rule_type,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "target_value": row.target_value,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "status": row.status,
        "source": row.source,
        "criteria": dict(row.criteria_json or {}),
    }


def _audit_applicability_facts(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> list[QualityAuditApplicabilityFact]:
    return (
        db.query(QualityAuditApplicabilityFact)
        .filter(
            QualityAuditApplicabilityFact.amo_id == amo_id,
            QualityAuditApplicabilityFact.audit_id == audit_id,
        )
        .order_by(QualityAuditApplicabilityFact.created_at.asc())
        .all()
    )


def _tenant_applicability_rules(
    db: Session,
    *,
    amo_id: str,
) -> list[tuple[document_control_models.DocumentApplicabilityRule, manual_models.Manual]]:
    return (
        db.query(document_control_models.DocumentApplicabilityRule, manual_models.Manual)
        .join(manual_models.Manual, manual_models.Manual.id == document_control_models.DocumentApplicabilityRule.manual_id)
        .join(manual_models.Tenant, manual_models.Tenant.id == manual_models.Manual.tenant_id)
        .filter(
            document_control_models.DocumentApplicabilityRule.tenant_id == amo_id,
            manual_models.Tenant.amo_id == amo_id,
            document_control_models.DocumentApplicabilityRule.status == "ACTIVE",
        )
        .order_by(
            document_control_models.DocumentApplicabilityRule.target_type.asc(),
            document_control_models.DocumentApplicabilityRule.created_at.desc(),
        )
        .limit(1000)
        .all()
    )


def _published_revision_for_manual(
    db: Session,
    *,
    manual_id: str,
    revision_id: str | None = None,
) -> manual_models.ManualRevision | None:
    query = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.manual_id == manual_id,
        manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
    )
    if revision_id:
        return query.filter(manual_models.ManualRevision.id == revision_id).first()
    return query.order_by(
        manual_models.ManualRevision.effective_date.desc().nullslast(),
        manual_models.ManualRevision.published_at.desc().nullslast(),
        manual_models.ManualRevision.created_at.desc(),
    ).first()


@router.get("/audits/{audit_id}/applicability-context")
def get_audit_applicability_context(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit, _user, _quality_router = _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    as_of = audit.actual_start or audit.planned_start or date.today()
    selected = _audit_applicability_facts(db, amo_id=ctx.amo_id, audit_id=audit_id)
    selected_rule_ids = {row.applicability_rule_id for row in selected}
    available: list[dict[str, Any]] = []
    for rule, manual in _tenant_applicability_rules(db, amo_id=ctx.amo_id):
        if rule.effective_from and rule.effective_from > as_of:
            continue
        if rule.effective_to and rule.effective_to < as_of:
            continue
        revision = _published_revision_for_manual(
            db,
            manual_id=manual.id,
            revision_id=rule.revision_id,
        )
        if rule.revision_id and revision is None:
            continue
        if revision is None:
            revision = _published_revision_for_manual(db, manual_id=manual.id)
        if revision is None:
            continue
        available.append({
            **_applicability_rule_dict(rule),
            "document_code": manual.code,
            "document_title": manual.title,
            "current_revision_id": str(revision.id),
            "current_revision": revision.rev_number,
            "selected": str(rule.id) in selected_rule_ids,
        })
    return {
        "items": [_applicability_fact_dict(row) for row in selected],
        "available_rules": available,
    }


@router.post("/audits/{audit_id}/applicability-context", status_code=201)
def add_audit_applicability_context(
    audit_id: uuid.UUID,
    payload: AuditApplicabilityFactCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit, _user, _quality_router = _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    if str(getattr(audit.status, "value", audit.status)).upper() == "CLOSED" or audit.actual_end is not None:
        raise HTTPException(status_code=409, detail="Closed audit applicability context is immutable.")

    rule = (
        db.query(document_control_models.DocumentApplicabilityRule)
        .filter(
            document_control_models.DocumentApplicabilityRule.id == payload.applicability_rule_id,
            document_control_models.DocumentApplicabilityRule.tenant_id == ctx.amo_id,
            document_control_models.DocumentApplicabilityRule.status == "ACTIVE",
        )
        .first()
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Governed applicability rule not found.")
    as_of = audit.actual_start or audit.planned_start or date.today()
    if rule.effective_from and rule.effective_from > as_of:
        raise HTTPException(
            status_code=409,
            detail="The governed applicability rule is not yet effective for this audit date.",
        )
    if rule.effective_to and rule.effective_to < as_of:
        raise HTTPException(
            status_code=409,
            detail="The governed applicability rule expired before this audit date.",
        )
    revision = _published_revision_for_manual(
        db,
        manual_id=rule.manual_id,
        revision_id=rule.revision_id,
    )
    if rule.revision_id and revision is None:
        raise HTTPException(
            status_code=409,
            detail="The applicability rule is tied to a revision that is not currently published.",
        )
    if revision is None:
        revision = _published_revision_for_manual(db, manual_id=rule.manual_id)
    if revision is None:
        raise HTTPException(
            status_code=409,
            detail="The applicability rule has no current published controlled-document revision.",
        )

    existing = (
        db.query(QualityAuditApplicabilityFact)
        .filter(
            QualityAuditApplicabilityFact.amo_id == ctx.amo_id,
            QualityAuditApplicabilityFact.audit_id == audit_id,
            QualityAuditApplicabilityFact.applicability_rule_id == rule.id,
        )
        .first()
    )
    if existing is not None:
        return _applicability_fact_dict(existing)

    row = QualityAuditApplicabilityFact(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        applicability_rule_id=rule.id,
        source_manual_id=rule.manual_id,
        source_revision_id=revision.id,
        rule_type=str(rule.rule_type).upper(),
        target_type=rule.target_type,
        target_id=rule.target_id,
        target_value=rule.target_value,
        source=rule.source,
        criteria_json=dict(rule.criteria_json or {}),
        reason=payload.reason.strip(),
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _applicability_fact_dict(row)


@router.delete("/audits/{audit_id}/applicability-context/{fact_id}", status_code=204)
def remove_audit_applicability_context(
    audit_id: uuid.UUID,
    fact_id: str,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    assert_quality_permission_any(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit, _user, _quality_router = _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    if str(getattr(audit.status, "value", audit.status)).upper() == "CLOSED" or audit.actual_end is not None:
        raise HTTPException(status_code=409, detail="Closed audit applicability context is immutable.")
    row = (
        db.query(QualityAuditApplicabilityFact)
        .filter(
            QualityAuditApplicabilityFact.id == fact_id,
            QualityAuditApplicabilityFact.amo_id == ctx.amo_id,
            QualityAuditApplicabilityFact.audit_id == audit_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Audit applicability fact not found.")
    db.delete(row)
    db.commit()
    return None


@router.get("/audits/{audit_id}/checklist-items/{item_id}/evidence-candidates")
def checklist_item_evidence_candidates(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    limit: int = Query(default=12, ge=1, le=20),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """Retrieve governed current-approved evidence candidates for one checklist item."""
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit, user, _quality_router = _internal_fieldwork_viewer(db, ctx=ctx, audit_id=audit_id)
    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id)
    tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.amo_id == ctx.amo_id).first()
    if tenant is None:
        raise HTTPException(status_code=409, detail="Document Control is not configured for this AMO.")

    definition = _frozen_item_definition_map(
        db,
        amo_id=ctx.amo_id,
        audit_id=audit_id,
    ).get(str(item_id), {})
    evidence_context = normalise_evidence_context(definition.get("evidence_context"))
    query_parts = [
        item.requirement_ref,
        item.checklist_ref,
        item.prompt,
        definition.get("regulatory_source_ref"),
        definition.get("manual_source_ref"),
    ]
    retrieval_query = " ".join(
        dict.fromkeys(
            value
            for value in (str(part or "").strip() for part in query_parts)
            if value
        )
    )[:2000]
    if len(retrieval_query) < 2:
        return {
            "checklist_item_id": str(item.id),
            "query": retrieval_query,
            "evidence_context": evidence_context,
            "retrieval_mode": "NO_QUERY",
            "authority_policy": precedence_policy(evidence_context),
            "items": [],
            "conflicts": [],
            "applicability_recommendation": {
                "status": "UNVERIFIED",
                "reason": "No usable checklist requirement text is available for controlled-source retrieval.",
                "basis": [],
            },
            "limitations": [
                "No usable checklist requirement text is available for controlled-source retrieval.",
            ],
        }

    sources = search_authorised_controlled_sources(
        db,
        tenant=tenant,
        user=user,
        query=retrieval_query,
        limit=limit,
    )
    revision_ids = list({str(source.get("revision_id") or "") for source in sources if source.get("revision_id")})
    manual_ids = list({str(source.get("manual_id") or "") for source in sources if source.get("manual_id")})
    section_ids = list({str(source.get("section_id") or "") for source in sources if source.get("section_id")})

    revisions = {
        str(row.id): row
        for row in db.query(manual_models.ManualRevision).filter(
            manual_models.ManualRevision.id.in_(revision_ids or ["-"])
        ).all()
    }
    profiles = {
        str(row.manual_id): row
        for row in db.query(document_control_models.DocumentControlProfile).filter(
            document_control_models.DocumentControlProfile.tenant_id == ctx.amo_id,
            document_control_models.DocumentControlProfile.manual_id.in_(manual_ids or ["-"]),
        ).all()
    }
    rules_by_manual: dict[str, list[dict[str, Any]]] = {}
    for rule in db.query(document_control_models.DocumentApplicabilityRule).filter(
        document_control_models.DocumentApplicabilityRule.tenant_id == ctx.amo_id,
        document_control_models.DocumentApplicabilityRule.manual_id.in_(manual_ids or ["-"]),
        document_control_models.DocumentApplicabilityRule.status == "ACTIVE",
    ).all():
        rules_by_manual.setdefault(str(rule.manual_id), []).append(_applicability_rule_dict(rule))

    section_text: dict[str, list[str]] = {}
    if section_ids:
        for block in (
            db.query(manual_models.ManualBlock)
            .filter(manual_models.ManualBlock.section_id.in_(section_ids))
            .order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc())
            .all()
        ):
            text_value = str(block.text_plain or "").strip()
            if text_value:
                section_text.setdefault(str(block.section_id), []).append(text_value)

    fact_payload = [_applicability_fact_dict(row) for row in _audit_applicability_facts(db, amo_id=ctx.amo_id, audit_id=audit_id)]
    as_of = audit.actual_start or audit.planned_start or date.today()
    semantic_used = any(
        any(
            str(value).startswith("SEMANTIC")
            for value in (source.get("retrieval_channels") or [])
        )
        for source in sources
    )
    lexical_used = any(
        bool({"LEXICAL", "METADATA"} & set(str(value) for value in (source.get("retrieval_channels") or [])))
        for source in sources
    )
    retrieval_mode = (
        "HYBRID_CURRENT_APPROVED"
        if semantic_used and lexical_used
        else "SEMANTIC_CURRENT_APPROVED"
        if semantic_used
        else "LEXICAL_CURRENT_APPROVED"
    )

    output: list[dict[str, Any]] = []
    conflict_inputs: list[dict[str, Any]] = []
    for source in sources:
        revision = revisions.get(str(source.get("revision_id") or ""))
        status_value = str(getattr(revision.status_enum, "value", revision.status_enum or "")).upper() if revision else None
        if revision is None or status_value != "PUBLISHED":
            continue

        manual_id = str(source.get("manual_id") or "")
        source_rules = [
            rule
            for rule in rules_by_manual.get(manual_id, [])
            if not rule.get("revision_id") or str(rule.get("revision_id")) == str(revision.id)
        ]
        applicability = evaluate_applicability(source_rules, fact_payload, as_of=as_of)
        profile = profiles.get(manual_id)
        metadata = dict(profile.metadata_json or {}) if profile else {}
        evidence_role = normalise_evidence_role(metadata.get("compliance_evidence_role"))
        authority_priority = evidence_priority(evidence_context, evidence_role)
        source_text = "\n".join(section_text.get(str(source.get("section_id") or ""), []))
        if not source_text:
            source_text = str(source.get("snippet") or "")
        candidate = {
            "evidence_id": source["id"],
            "kind": source.get("kind"),
            "document_id": source.get("manual_id"),
            "document_code": source.get("code"),
            "document_title": source.get("title"),
            "revision_id": source.get("revision_id"),
            "revision": revision.rev_number,
            "revision_status": status_value,
            "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
            "section_id": source.get("section_id"),
            "heading": source.get("heading"),
            "page_number": source.get("page_number"),
            "snippet": source.get("snippet"),
            "reader_url": source.get("reader_url"),
            "score": source.get("score"),
            "reason": source.get("reason"),
            "retrieval_channels": list(source.get("retrieval_channels") or []),
            "semantic_similarity": source.get("semantic_similarity"),
            "current_approved": True,
            "evidence_role": evidence_role,
            "authority_priority": authority_priority,
            "applicability": applicability,
        }
        output.append(candidate)
        if applicability.get("status") != "NOT_APPLICABLE":
            conflict_inputs.append({
                **candidate,
                "reference": " · ".join(
                    value for value in (
                        str(source.get("code") or "").strip(),
                        str(source.get("heading") or "").strip(),
                    ) if value
                ),
                "source_text": source_text,
            })

    output.sort(
        key=lambda item: (
            -1 if item.get("authority_priority") is None else int(item.get("authority_priority") or 0),
            float(item.get("score") or 0),
        ),
        reverse=True,
    )
    conflicts = detect_requirement_conflicts(conflict_inputs)
    policy = precedence_policy(evidence_context)
    ranked = [item for item in output if item.get("authority_priority") is not None]
    applicability_recommendation: dict[str, Any] = {
        "status": "UNVERIFIED",
        "reason": "Applicability remains subject to the selected governed audit context and auditor confirmation.",
        "basis": [],
    }
    if evidence_context != "GENERAL" and policy and ranked:
        highest = max(int(item.get("authority_priority") or 0) for item in ranked)
        authoritative = [item for item in ranked if int(item.get("authority_priority") or 0) == highest]
        if authoritative and all(item.get("applicability", {}).get("status") == "NOT_APPLICABLE" for item in authoritative):
            applicability_recommendation = {
                "status": "NOT_APPLICABLE",
                "reason": "The highest-priority governed evidence for this checklist context is outside the selected audit applicability context.",
                "basis": [
                    {
                        "evidence_id": item.get("evidence_id"),
                        "document_code": item.get("document_code"),
                        "revision_id": item.get("revision_id"),
                        "evidence_role": item.get("evidence_role"),
                        "authority_priority": item.get("authority_priority"),
                        "applicability": item.get("applicability"),
                    }
                    for item in authoritative
                ],
            }
        elif any(item.get("applicability", {}).get("status") == "APPLICABLE" for item in authoritative):
            applicability_recommendation = {
                "status": "APPLICABLE",
                "reason": "At least one highest-priority governed evidence source matches the selected audit applicability context.",
                "basis": [
                    {
                        "evidence_id": item.get("evidence_id"),
                        "document_code": item.get("document_code"),
                        "revision_id": item.get("revision_id"),
                        "evidence_role": item.get("evidence_role"),
                        "authority_priority": item.get("authority_priority"),
                        "applicability": item.get("applicability"),
                    }
                    for item in authoritative
                    if item.get("applicability", {}).get("status") == "APPLICABLE"
                ],
            }

    limitations = [
        "Candidate retrieval and applicability analysis do not make the final compliance decision.",
    ]
    if semantic_used is False:
        limitations.append("Semantic retrieval was unavailable or disabled; results use lexical/full-text and metadata matching only.")
    if evidence_context != "GENERAL" and not policy:
        limitations.append("No context-specific evidence precedence policy is configured for this checklist item.")
    if not fact_payload:
        limitations.append("No governed audit applicability facts are selected; applicability remains unverified where documents are scoped.")

    return {
        "checklist_item_id": str(item.id),
        "query": retrieval_query,
        "evidence_context": evidence_context,
        "retrieval_mode": retrieval_mode,
        "authority_policy": policy,
        "applicability_context": fact_payload,
        "applicability_recommendation": applicability_recommendation,
        "conflicts": conflicts,
        "documentary_recommendation": "CONFLICT" if conflicts else "UNVERIFIED",
        "items": output,
        "limitations": limitations,
    }


@router.patch("/audits/{audit_id}/checklist-items/{item_id}/execution-governance")
def update_checklist_execution_governance(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ChecklistExecutionUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    # Compatibility route retained only to produce an explicit migration signal.
    # All authoritative checklist writes must carry base_version + idempotency
    # through the guarded fieldwork mutation command.
    assert_quality_permission_any(db, ctx, "qms.audit.manage", "qms.audit.execute")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    raise HTTPException(
        status_code=410,
        detail={
            "code": "FIELDWORK_LEGACY_WRITE_RETIRED",
            "message": "Use the guarded fieldwork-mutations endpoint with base_version and an idempotency key.",
        },
    )


@router.post("/audits/{audit_id}/checklist-items/{item_id}/fieldwork-mutations")
def mutate_live_fieldwork(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: FieldworkMutation,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", "qms.audit.execute")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _internal_fieldwork_actor(db, ctx=ctx, audit_id=audit_id)
    payload_hash = _mutation_hash(payload)
    existing = _existing_receipt_or_none(
        db,
        ctx=ctx,
        client_mutation_id=payload.client_mutation_id,
        payload_hash=payload_hash,
    )
    if existing is not None:
        return {
            "client_mutation_id": payload.client_mutation_id,
            "committed_version": existing.committed_version,
            "replayed": True,
            "row": existing.result_snapshot,
        }

    item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
    governance = _locked_governance(db, ctx=ctx, audit_id=audit_id, item_id=item_id)
    current_version = _assert_base_version(
        payload_base_version=payload.base_version,
        client_mutation_id=payload.client_mutation_id,
        item=item,
        governance=governance,
    )

    _validate_frozen_item_requirements(
        db,
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        item_id=item_id,
        canonical_status=payload.canonical_response_status,
        auditor_notes=payload.auditor_notes,
        evidence_references=payload.evidence_references,
    )
    response_value = _validated_response_value(
        db,
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        item_id=item_id,
        response_value=payload.response_value,
        canonical_status=payload.canonical_response_status,
    )
    update = ChecklistExecutionUpdate(
        canonical_response_status=payload.canonical_response_status,
        response_value=response_value,
        auditor_notes=payload.auditor_notes,
        sampled_item_information=payload.sampled_item_information,
        evidence_references=payload.evidence_references,
        assessment=payload.assessment,
        reason=payload.reason,
    )
    governance = _apply_execution_update(db, ctx=ctx, item=item, payload=update, governance=governance)
    committed_version = int(governance.entity_version or 1)
    db.flush()

    row_snapshot = jsonable_encoder(_row_dict(item, governance))
    receipt = QualityAuditFieldworkMutationReceipt(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        checklist_item_id=item_id,
        client_mutation_id=payload.client_mutation_id,
        device_id=payload.device_id,
        device_sequence=payload.device_sequence,
        client_timestamp=_normalise_client_timestamp(payload.client_timestamp),
        base_version=payload.base_version,
        committed_version=committed_version,
        operation=payload.operation,
        payload_hash=payload_hash,
        result_snapshot=row_snapshot,
        actor_user_id=ctx.user_id,
    )
    db.add(receipt)
    realtime_event = _fieldwork_event(
        ctx=ctx,
        audit_id=audit_id,
        item_id=item_id,
        client_mutation_id=payload.client_mutation_id,
        device_id=payload.device_id,
        device_sequence=payload.device_sequence,
        client_timestamp=payload.client_timestamp,
        current_version=current_version,
        committed_version=committed_version,
        response=payload.canonical_response_status,
    )
    db.add(realtime_event)
    db.flush()
    db.commit()

    _publish_persisted_event(realtime_event)
    return {
        "client_mutation_id": payload.client_mutation_id,
        "committed_version": committed_version,
        "replayed": False,
        "row": row_snapshot,
    }


@router.post("/audits/{audit_id}/checklist-items/{item_id}/fieldwork-findings")
def create_atomic_fieldwork_finding(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: FieldworkFindingMutation,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission_any(db, ctx, "qms.audit.manage", "qms.audit.execute")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit, _user, quality_router = _internal_fieldwork_actor(db, ctx=ctx, audit_id=audit_id)
    payload_hash = _mutation_hash(payload)
    existing = _existing_receipt_or_none(
        db,
        ctx=ctx,
        client_mutation_id=payload.client_mutation_id,
        payload_hash=payload_hash,
    )
    if existing is not None:
        stored = dict(existing.result_snapshot or {})
        return {
            "client_mutation_id": payload.client_mutation_id,
            "committed_version": existing.committed_version,
            "replayed": True,
            **stored,
        }

    published_events: list[audit_models.AuditEvent] = []
    try:
        item = _item(db, amo_id=ctx.amo_id, audit_id=audit_id, item_id=item_id, lock=True)
        governance = _locked_governance(db, ctx=ctx, audit_id=audit_id, item_id=item_id)
        current_version = _assert_base_version(
            payload_base_version=payload.base_version,
            client_mutation_id=payload.client_mutation_id,
            item=item,
            governance=governance,
        )
        if item.finding_id is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "FIELDWORK_FINDING_ALREADY_LINKED",
                    "message": "This checklist item already has a governed finding. Review the existing finding before creating another.",
                    "finding_id": str(item.finding_id),
                },
            )

        level, finding_type = _finding_classification(payload)
        target_close_date = payload.target_close_date
        if target_close_date is None and level != FindingLevel.LEVEL_4:
            target_close_date = compute_target_close_date(level)

        finding = models.QMSAuditFinding(
            amo_id=audit.amo_id,
            audit_id=audit_id,
            finding_ref=quality_router._next_audit_finding_ref(db, audit),
            finding_type=finding_type,
            severity=payload.severity,
            level=level,
            requirement_ref=payload.requirement_ref.strip() if payload.requirement_ref else None,
            description=payload.description.strip(),
            objective_evidence=payload.objective_evidence.strip() if payload.objective_evidence else None,
            safety_sensitive=payload.safety_sensitive,
            target_close_date=target_close_date,
            created_by_user_id=ctx.user_id,
        )
        db.add(finding)
        db.flush()
        item.finding_id = finding.id

        if level != FindingLevel.LEVEL_4:
            task_owner = audit.lead_auditor_user_id or ctx.user_id
            quality_router.task_services.create_task(
                db,
                amo_id=ctx.amo_id,
                title="Respond to finding",
                description=f"Finding {finding.finding_ref or finding.id} requires response.",
                owner_user_id=task_owner,
                supervisor_user_id=audit.observer_auditor_user_id,
                due_at=quality_router._date_to_datetime(finding.target_close_date),
                entity_type="qms_finding",
                entity_id=str(finding.id),
                priority=2,
            )
            if audit.status in (QMSAuditStatus.PLANNED, QMSAuditStatus.IN_PROGRESS):
                audit.status = QMSAuditStatus.CAP_OPEN

        linked_car = quality_router._ensure_car_for_finding(
            db,
            audit=audit,
            finding=finding,
            requested_by_user_id=ctx.user_id,
        )

        _validate_frozen_item_requirements(
            db,
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            item_id=item_id,
            canonical_status=payload.canonical_response_status,
            auditor_notes=payload.auditor_notes,
            evidence_references=payload.evidence_references,
        )
        response_value = _validated_response_value(
            db,
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            item_id=item_id,
            response_value=payload.response_value,
            canonical_status=payload.canonical_response_status,
        )
        execution_update = ChecklistExecutionUpdate(
            canonical_response_status=payload.canonical_response_status,
            response_value=response_value,
            auditor_notes=payload.auditor_notes,
            sampled_item_information=payload.sampled_item_information,
            evidence_references=payload.evidence_references,
            assessment=payload.assessment,
            reason=payload.reason,
        )
        governance = _apply_execution_update(
            db,
            ctx=ctx,
            item=item,
            payload=execution_update,
            governance=governance,
        )
        committed_version = int(governance.entity_version or 1)
        db.flush()

        row_snapshot = jsonable_encoder(_row_dict(item, governance))
        finding_snapshot = jsonable_encoder(quality_router._serialize_finding(finding))
        result_snapshot = {
            "row": row_snapshot,
            "finding": finding_snapshot,
            "car_id": str(linked_car.id) if linked_car else None,
            "car_number": linked_car.car_number if linked_car else None,
        }
        db.add(QualityAuditFieldworkMutationReceipt(
            amo_id=ctx.amo_id,
            audit_id=audit_id,
            checklist_item_id=item_id,
            client_mutation_id=payload.client_mutation_id,
            device_id=payload.device_id,
            device_sequence=payload.device_sequence,
            client_timestamp=_normalise_client_timestamp(payload.client_timestamp),
            base_version=payload.base_version,
            committed_version=committed_version,
            operation=payload.operation,
            payload_hash=payload_hash,
            result_snapshot=result_snapshot,
            actor_user_id=ctx.user_id,
        ))

        finding_event = audit_models.AuditEvent(
            amo_id=ctx.amo_id,
            entity_type="qms.finding",
            entity_id=str(finding.id),
            action="CREATED",
            actor_user_id=ctx.user_id,
            after={
                "audit_id": str(audit_id),
                "finding_ref": finding.finding_ref,
                "severity": finding.severity.value,
                "level": finding.level.value,
                "target_close_date": str(finding.target_close_date) if finding.target_close_date else None,
                "checklist_item_id": str(item_id),
            },
            correlation_id=payload.client_mutation_id,
            metadata_json={
                "module": "quality",
                "auditId": str(audit_id),
                "checklistItemId": str(item_id),
                "clientMutationId": payload.client_mutation_id,
                "clientTimestamp": _normalise_client_timestamp(payload.client_timestamp).isoformat(),
            },
        )
        fieldwork_event = _fieldwork_event(
            ctx=ctx,
            audit_id=audit_id,
            item_id=item_id,
            client_mutation_id=payload.client_mutation_id,
            device_id=payload.device_id,
            device_sequence=payload.device_sequence,
            client_timestamp=payload.client_timestamp,
            current_version=current_version,
            committed_version=committed_version,
            response=payload.canonical_response_status,
        )
        db.add_all([finding_event, fieldwork_event])
        published_events.extend([finding_event, fieldwork_event])
        if linked_car is not None:
            car_event = audit_models.AuditEvent(
                amo_id=ctx.amo_id,
                entity_type="qms.car",
                entity_id=str(linked_car.id),
                action="AUTO_CREATED_FROM_FINDING",
                actor_user_id=ctx.user_id,
                after={"finding_id": str(finding.id), "car_number": linked_car.car_number},
                correlation_id=payload.client_mutation_id,
                metadata_json={
                    "module": "quality",
                    "auditId": str(audit_id),
                    "clientTimestamp": _normalise_client_timestamp(payload.client_timestamp).isoformat(),
                },
            )
            db.add(car_event)
            published_events.append(car_event)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    for event in published_events:
        _publish_persisted_event(event)
    return {
        "client_mutation_id": payload.client_mutation_id,
        "committed_version": committed_version,
        "replayed": False,
        **result_snapshot,
    }
