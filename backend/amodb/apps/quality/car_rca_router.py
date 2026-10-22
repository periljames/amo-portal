"""Governed RCA documents and action endpoints for the authoritative CAR.

Public invitation possession grants access only to the matching CAR. It never
grants authenticated Assurance Case or Quality review permissions.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db, get_write_db
from . import models
from .car_rca_models import (
    QualityCarRcaAction, QualityCarRcaActionEvent, QualityCarRcaDocument,
    QualityCarRcaMutation, QualityCarRcaRevision, QualityCarRcaRollout,
    QualityCarResponseRetainedRevision, QualityCarInviteAccessControl
)
from .tenant_security import (
    TenantContext, assert_quality_permission, require_quality_permission,
    set_postgres_tenant_context, write_tenant_context
)

public_router = APIRouter(prefix="/cars/invite", tags=["Quality / Public CAR RCA"])
router = APIRouter(prefix="/cars/{car_id}", tags=["Quality / CAR RCA"])

METHODS = {
    "FIVE_WHYS", "ISHIKAWA", "PARETO", "CAUSAL_FACTOR", "BARRIER_ANALYSIS",
    "CHANGE_ANALYSIS", "HUMAN_ORGANIZATIONAL", "EIGHT_D", "FMEA"
}
NODE_TYPES = {"FACT", "HYPOTHESIS", "CAUSAL_CONCLUSION", "RULED_OUT"}
ACTIVE_ACTIONS = {"PROPOSED", "ACCEPTED", "IN_PROGRESS", "SUBMITTED", "VERIFIED", "REJECTED", "CANCELLED"}


def _utcnow():
    return datetime.now(timezone.utc)


class CauseNode(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    parent_id: str | None = Field(default=None, max_length=80)
    statement: str = Field(min_length=2, max_length=4000)
    category: str = Field(default="Process", max_length=80)
    entry_type: Literal["FACT", "HYPOTHESIS", "CAUSAL_CONCLUSION", "RULED_OUT"] = "HYPOTHESIS"
    evidence_references: list[str] = Field(default_factory=list, max_length=30)
    rationale: str = Field(default="", max_length=4000)

    @field_validator("evidence_references")
    @classmethod
    def check_evidence_references(cls, references: list[str]) -> list[str]:
        if any(not str(ref).strip() or len(ref) > 500 for ref in references):
            raise ValueError("Evidence references must be nonblank and at most 500 characters each.")
        return references


class Investigation(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    method: Literal[
        "FIVE_WHYS", "ISHIKAWA", "PARETO", "CAUSAL_FACTOR", "BARRIER_ANALYSIS",
        "CHANGE_ANALYSIS", "HUMAN_ORGANIZATIONAL", "EIGHT_D", "FMEA"
    ]
    version: int = Field(default=1, ge=1, le=100)
    nodes: list[CauseNode] = Field(default_factory=list, max_length=100)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def bounded_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 40 or len(json.dumps(value, default=str)) > 40000:
            raise ValueError("Analysis metadata exceeds the controlled size limit.")
        if "frequencies" in value:
            rows = value["frequencies"]
            if not isinstance(rows, list) or len(rows) > 200:
                raise ValueError("Pareto must include at most 200 documented categories.")
            for row in rows:
                if not isinstance(row, dict) or not str(row.get("source_ref", "")).strip():
                    raise ValueError("Pareto source references are required for each category.")
                count = row.get("count")
                if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 1_000_000:
                    raise ValueError("Pareto frequencies must be positive whole numbers.")
        return value


class EffectivenessProposal(BaseModel):
    # Partial drafts are valid. Adoption requires complete measured criteria.
    expected_result: str = Field(default="", max_length=8000)
    verification_method: str = Field(default="", max_length=8000)
    measurable_success_criterion: str = Field(default="", max_length=8000)
    observation_period: str = Field(default="", max_length=255)
    proposed_review_date: date | None = None
    supporting_records: list[str] = Field(default_factory=list, max_length=40)


class InvestigationDocument(BaseModel):
    version: int = Field(default=1, ge=1, le=100)
    problem_statement: str = Field(default="", max_length=8000)
    investigations: list[Investigation] = Field(default_factory=list, max_length=12)
    conclusion: str = Field(default="", max_length=8000)
    supported_cause_ids: list[str] = Field(default_factory=list, max_length=30)
    conclusion_evidence_references: list[str] = Field(default_factory=list, max_length=60)
    evidence_notes: str = Field(default="", max_length=8000)
    effectiveness_proposal: EffectivenessProposal | None = None

    @field_validator("conclusion_evidence_references")
    @classmethod
    def check_conclusion_sources(cls, references: list[str]) -> list[str]:
        if any(not str(ref).strip() or len(ref) > 500 for ref in references):
            raise ValueError("Conclusion references must be nonblank and at most 500 characters each.")
        return references

    @model_validator(mode="after")
    def validate_graphs(self):
        method_ids = set()
        all_nodes = {}
        for method in self.investigations:
            if method.id in method_ids:
                raise ValueError("Each investigation requires a distinct identifier.")
            method_ids.add(method.id)
            local = set()
            for node in method.nodes:
                if node.id in all_nodes:
                    raise ValueError("Cause IDs must be unique across investigations.")
                all_nodes[node.id] = node
                local.add(node.id)
            for node in method.nodes:
                if node.parent_id and node.parent_id not in local:
                    raise ValueError("Every parent cause must belong to the same method.")
                if node.parent_id == node.id:
                    raise ValueError("A cause cannot be its own parent.")
                seen = {node.id}
                current = node.parent_id
                while current:
                    if current in seen:
                        raise ValueError("Causal graphs must not contain cycles.")
                    seen.add(current)
                    current = all_nodes[current].parent_id
        for cause_id in self.supported_cause_ids:
            node = all_nodes.get(cause_id)
            if not node or node.entry_type != "CAUSAL_CONCLUSION":
                raise ValueError("Supported causes must reference documented causal conclusions.")
            if not node.evidence_references:
                raise ValueError("A supported causal conclusion requires its own evidence references.")
        return self


class CarRcaSave(BaseModel):
    expected_revision: int = Field(ge=0)
    mutation_key: str = Field(min_length=8, max_length=100)
    investigation: InvestigationDocument = Field(default_factory=InvestigationDocument)
    form: dict[str, str] = Field(default_factory=dict)


class ActionCreate(BaseModel):
    kind: Literal["CORRECTIVE", "PREVENTIVE", "CONTAINMENT"] = "CORRECTIVE"
    description: str = Field(min_length=5, max_length=8000)
    cause_node_ids: list[str] = Field(default_factory=list, max_length=30)
    evidence_references: list[str] = Field(default_factory=list, max_length=40)
    owner_user_id: str | None = Field(default=None, max_length=36)
    external_owner_name: str | None = Field(default=None, max_length=255)
    target_date: date | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"


class ActionProgress(BaseModel):
    state: Literal["IN_PROGRESS", "SUBMITTED"]
    completion_note: str = Field(default="", max_length=4000)
    evidence_references: list[str] = Field(default_factory=list, max_length=40)


class ActionReview(BaseModel):
    state: Literal["ACCEPTED", "REJECTED", "VERIFIED"]
    reason: str = Field(min_length=8, max_length=4000)


def _control_for_car(db: Session, car):
    return db.query(QualityCarInviteAccessControl).filter(
        QualityCarInviteAccessControl.amo_id == str(car.amo_id),
        QualityCarInviteAccessControl.car_id == car.id,
    ).first()


def assert_invite_access(db: Session, car) -> None:
    """Reject expired/revoked guest capabilities regardless of CAR edit status."""
    # A token is first resolved against the indexed, unique quality_cars token;
    # tenant RLS is set from the resolved row, never from a caller-supplied ID.
    set_postgres_tenant_context(
        db, amo_id=str(car.amo_id),
        user_id="00000000-0000-0000-0000-000000000000",
    )
    control = _control_for_car(db, car)
    if control is None:
        return  # Preserve links issued before governance activation.
    if control.revoked_at is not None:
        raise HTTPException(status_code=410, detail="This CAR invitation was revoked by Quality.")
    if control.expires_at is not None:
        expires_at = control.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _utcnow():
            raise HTTPException(status_code=410, detail="This CAR invitation has expired. Contact Quality.")


def _car_for_guest(db: Session, token: str, *, lock=False):
    if not token or len(token) > 64:
        raise HTTPException(status_code=404, detail="CAR invitation not found")
    query = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.invite_token == token
    )
    car = (query.with_for_update() if lock else query).first()
    if car is None:
        raise HTTPException(status_code=404, detail="CAR invitation not found")
    assert_invite_access(db, car)
    return car


def _car_for_employee(db: Session, ctx: TenantContext, car_id: uuid.UUID, *, lock=False):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.amo_id == ctx.amo_id,
        models.CorrectiveActionRequest.id == car_id,
    )
    car = (query.with_for_update() if lock else query).first()
    if car is None:
        raise HTTPException(status_code=404, detail="CAR not found for this tenant")
    return car


def _assert_guest_editable(db: Session, car):
    from .router import _require_public_car_invite_editable
    _require_public_car_invite_editable(db, car)


def _document(db: Session, car, *, lock=False, create=False):
    query = db.query(QualityCarRcaDocument).filter(
        QualityCarRcaDocument.amo_id == str(car.amo_id),
        QualityCarRcaDocument.car_id == car.id,
    )
    doc = (query.with_for_update() if lock else query).first()
    if doc is None and create:
        doc = QualityCarRcaDocument(
            id=uuid.uuid4(), amo_id=str(car.amo_id), car_id=car.id,
            revision=0, draft={"form": {}, "investigation": InvestigationDocument().model_dump()}
        )
        db.add(doc)
        db.flush()
    return doc


def _action_dict(row: QualityCarRcaAction):
    return {
        "id": str(row.id), "car_id": str(row.car_id), "sequence_no": row.sequence_no,
        "action_number": str(row.sequence_no).zfill(2),
        "kind": row.kind, "description": row.description,
        "cause_node_ids": row.cause_node_ids or [],
        "evidence_references": row.evidence_references or [],
        "owner_user_id": row.owner_user_id, "external_owner_name": row.external_owner_name,
        "target_date": row.target_date, "priority": row.priority, "state": row.state,
        "completion_note": row.completion_note, "completed_at": row.completed_at,
        "quality_review_note": row.quality_review_note,
        "reviewed_by_user_id": row.reviewed_by_user_id, "reviewed_at": row.reviewed_at,
    }


def _record_action_event(db: Session, car, row: QualityCarRcaAction, *,
                         from_state: str | None, actor_kind: str, actor_ref: str | None, reason: str):
    db.add(QualityCarRcaActionEvent(
        id=uuid.uuid4(), amo_id=str(car.amo_id), car_id=car.id,
        action_id=row.id, previous_state=from_state, next_state=row.state,
        snapshot=json.loads(json.dumps(_action_dict(row), default=str)), actor_kind=actor_kind,
        actor_ref=actor_ref, reason=reason
    ))


def _action_events(db: Session, car):
    rows = db.query(QualityCarRcaActionEvent).filter(
        QualityCarRcaActionEvent.amo_id == str(car.amo_id),
        QualityCarRcaActionEvent.car_id == car.id
    ).order_by(QualityCarRcaActionEvent.created_at.desc()).limit(250).all()
    return [
        {
            "id": str(row.id), "action_id": str(row.action_id),
            "previous_state": row.previous_state, "next_state": row.next_state,
            "actor_kind": row.actor_kind, "actor_ref": row.actor_ref,
            "reason": row.reason, "created_at": row.created_at,
            "snapshot": row.snapshot
        } for row in rows
    ]


def _actions(db: Session, car):
    return db.query(QualityCarRcaAction).filter(
        QualityCarRcaAction.amo_id == str(car.amo_id),
        QualityCarRcaAction.car_id == car.id
    ).order_by(QualityCarRcaAction.sequence_no).all()


def retain_recalled_car_response(db: Session, car, response, *, reason: str):
    """Preserve the original response before removing it from the active queue."""
    previous = db.query(QualityCarResponseRetainedRevision.id).filter(
        QualityCarResponseRetainedRevision.amo_id == str(car.amo_id),
        QualityCarResponseRetainedRevision.car_id == car.id,
        QualityCarResponseRetainedRevision.original_response_id == str(response.id),
    ).first()
    if previous is not None:
        return
    state = {
        column.name: getattr(response, column.name)
        for column in response.__table__.columns
    }
    db.add(QualityCarResponseRetainedRevision(
        id=uuid.uuid4(), amo_id=str(car.amo_id), car_id=car.id,
        original_response_id=str(response.id), event_type="RECALLED",
        submitted_at=response.submitted_at,
        snapshot=json.loads(json.dumps(state, default=str)),
        reason=reason
    ))
    db.flush()


def _public_projection(db: Session, car, *, include_history=False):
    doc = _document(db, car)
    revisions = []
    if include_history and doc is not None:
        revisions = db.query(QualityCarRcaRevision).filter(
            QualityCarRcaRevision.amo_id == str(car.amo_id),
            QualityCarRcaRevision.car_id == car.id
        ).order_by(QualityCarRcaRevision.revision.desc()).limit(100).all()
    recalled = (
        db.query(QualityCarResponseRetainedRevision).filter(
            QualityCarResponseRetainedRevision.amo_id == str(car.amo_id),
            QualityCarResponseRetainedRevision.car_id == car.id,
        ).order_by(QualityCarResponseRetainedRevision.retained_at.desc()).limit(100).all()
        if include_history else []
    )
    return {
        "car_id": str(car.id), "revision": doc.revision if doc else 0,
        "draft": doc.draft if doc else {
            "form": {}, "investigation": InvestigationDocument(
                problem_statement=str(car.summary or "")
            ).model_dump()
        },
        "submitted_revision": doc.submitted_revision if doc else None,
        "submitted_snapshot": doc.submitted_snapshot if doc else None,
        "submitted_at": doc.submitted_at if doc else None,
        # Public bearer capabilities must not expose internal actor identities.
        # Full attributed history is available only to tenant Quality readers.
        "actions": [
            _action_dict(item) if include_history
            else {**_action_dict(item), "owner_user_id": None,
                  "reviewed_by_user_id": None}
            for item in _actions(db, car)
        ],
        "action_events": _action_events(db, car) if include_history else [],
        "retained_responses": [
            {"id": str(item.id), "original_response_id": item.original_response_id,
             "event_type": item.event_type, "submitted_at": item.submitted_at,
             "retained_at": item.retained_at, "reason": item.reason,
             "snapshot": item.snapshot} for item in recalled
        ],
        "history": [
            {
                "id": str(item.id), "revision": item.revision,
                "event_type": item.event_type, "actor_kind": item.actor_kind,
                "actor_ref": item.actor_ref, "created_at": item.created_at,
                "reason": item.reason, "snapshot": item.snapshot
            } for item in revisions
        ],
    }


def _append_revision(db: Session, car, doc, *, event, actor, actor_ref, reason):
    db.add(QualityCarRcaRevision(
        id=uuid.uuid4(), amo_id=str(car.amo_id), car_id=car.id,
        document_id=doc.id, revision=doc.revision, event_type=event,
        snapshot=doc.draft, actor_kind=actor, actor_ref=actor_ref,
        reason=reason
    ))


def _save(db: Session, car, payload: CarRcaSave, *, actor, actor_ref):
    _assert_guest_editable(db, car) if actor == "GUEST" else None
    doc = _document(db, car, lock=True, create=True)
    data = {
        "investigation": payload.investigation.model_dump(mode="json"),
        "form": {key: value[:8000] for key, value in payload.form.items()
                 if key in {
                     "submitted_by_name", "submitted_by_email", "containment_action",
                     "root_cause", "corrective_action", "preventive_action",
                     "evidence_ref", "due_date", "target_closure_date"
                 } and isinstance(value, str)}
    }
    fingerprint = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.query(QualityCarRcaMutation).filter(
        QualityCarRcaMutation.amo_id == str(car.amo_id),
        QualityCarRcaMutation.car_id == car.id,
        QualityCarRcaMutation.mutation_key == payload.mutation_key,
    ).first()
    if existing:
        if existing.fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="The save key was already used for different content.")
        return _public_projection(db, car)
    if doc.revision != payload.expected_revision:
        raise HTTPException(
            status_code=409,
            detail={"message": "A newer draft was saved elsewhere; reload before overwriting.",
                    "server_revision": doc.revision}
        )
    if doc.draft == data:
        return _public_projection(db, car)
    doc.revision += 1
    doc.draft = data
    _append_revision(
        db, car, doc, event="DRAFT_SAVED", actor=actor,
        actor_ref=actor_ref, reason="Investigation draft saved."
    )
    db.add(QualityCarRcaMutation(
        id=uuid.uuid4(), amo_id=str(car.amo_id), car_id=car.id,
        mutation_key=payload.mutation_key, fingerprint=fingerprint,
        result_revision=doc.revision
    ))
    db.commit()
    return _public_projection(db, car)


def structured_rca_required(db: Session, car) -> bool:
    """Preserve pre-migration invitation contracts without a bypass for new CARs."""
    rollout = db.query(QualityCarRcaRollout).filter(QualityCarRcaRollout.id == 1).first()
    if rollout is None:
        # Missing migration data is not a reason to downgrade review controls.
        raise HTTPException(status_code=503, detail="RCA policy activation is unavailable.")
    creation = car.created_at
    activation = rollout.activated_at
    if creation is not None:
        if creation.tzinfo is None:
            creation = creation.replace(tzinfo=timezone.utc)
        if activation.tzinfo is None:
            activation = activation.replace(tzinfo=timezone.utc)
        if creation >= activation:
            return True
    document = _document(db, car)
    return document is not None and document.revision > 0


def submit_rca_document(db: Session, car, root_cause_text: str | None, *, responder_email: str | None = None):
    """Stage the structured evidence in the SAME transaction as base CAR submission.

    Legacy CARs without a structured RCA document retain their established
    submissions. Newly created structured investigations require a supported
    conclusion and evidence-backed cause; a hypothesis alone is never verified.
    """
    required = structured_rca_required(db, car)
    doc = _document(db, car, lock=True)
    if doc is None or doc.revision == 0:
        if required:
            raise HTTPException(status_code=422, detail="This newly issued CAR requires a saved, structured RCA investigation before submission.")
        return
    data = InvestigationDocument.model_validate(doc.draft.get("investigation") or {})
    if not data.conclusion.strip() or not data.supported_cause_ids:
        raise HTTPException(status_code=422, detail="Complete an evidence-backed root cause conclusion before submitting.")
    source_nodes = [node for method in data.investigations for node in method.nodes]
    if not any(node.entry_type == "FACT" and node.evidence_references for node in source_nodes):
        raise HTTPException(status_code=422, detail="Record at least one evidence-linked fact before submitting a causal conclusion.")
    if not data.conclusion_evidence_references:
        raise HTTPException(status_code=422, detail="Reference the evidence supporting the final root cause.")
    if (root_cause_text or "").strip() != data.conclusion.strip():
        raise HTTPException(status_code=409, detail="The CAR root-cause narrative differs from your saved investigation. Save the latest conclusion and resubmit.")
    actions = _actions(db, car)
    if not any(action.kind == "CORRECTIVE" and action.target_date and
               (action.owner_user_id or action.external_owner_name) for action in actions):
        raise HTTPException(status_code=422, detail="Add an individually owned, dated corrective action before submitting.")
    doc.revision += 1
    doc.submitted_revision = doc.revision
    doc.submitted_at = _utcnow()
    doc.submitted_snapshot = dict(doc.draft)
    _append_revision(
        db, car, doc, event="SUBMITTED", actor="GUEST",
        actor_ref=(responder_email or car.submitted_by_email), reason="Structured RCA submitted with CAR response."
    )


@public_router.get("/{invite_token}/draft")
@public_router.get("/{invite_token}/investigation")
def read_public_rca(invite_token: str, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Referrer-Policy"] = "no-referrer"
    car = _car_for_guest(db, invite_token)
    return _public_projection(db, car)


@public_router.put("/{invite_token}/draft")
@public_router.put("/{invite_token}/investigation")
def save_public_rca(invite_token: str, payload: CarRcaSave, db: Session = Depends(get_db)):
    car = _car_for_guest(db, invite_token, lock=True)
    identity = (payload.form.get("submitted_by_email") or "").strip()[:255]
    return _save(db, car, payload, actor="GUEST", actor_ref=identity or "invited-responder")


@router.get("/investigation")
def read_employee_rca(car_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")),
    db: Session = Depends(get_read_db)):
    car = _car_for_employee(db, ctx, car_id)
    return _public_projection(db, car, include_history=True)


@router.put("/investigation")
def save_employee_rca(car_id: uuid.UUID, payload: CarRcaSave,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db)):
    assert_quality_permission(db, ctx, "qms.car.manage")
    car = _car_for_employee(db, ctx, car_id, lock=True)
    if getattr(car.status, "value", car.status) in {"CLOSED", "CANCELLED", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="CAR is locked.")
    return _save(db, car, payload, actor="EMPLOYEE", actor_ref=ctx.user_id)


@public_router.get("/{invite_token}/corrective-actions")
def public_actions(invite_token: str, db: Session = Depends(get_db)):
    return _public_projection(db, _car_for_guest(db, invite_token))["actions"]


@router.get("/corrective-actions")
def employee_actions(car_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")),
    db: Session = Depends(get_read_db)):
    return _public_projection(db, _car_for_employee(db, ctx, car_id))["actions"]


def _assert_action_scope(db: Session, car, payload: ActionCreate, *, public: bool):
    if payload.owner_user_id and public:
        raise HTTPException(status_code=403, detail="Guest cannot assign internal employee privileges.")
    if payload.target_date and (car.target_closure_date or car.due_date):
        limit = car.target_closure_date or car.due_date
        if payload.target_date > limit:
            raise HTTPException(status_code=409, detail="An action date beyond the agreed CAR deadline requires a governed extension.")
    if payload.cause_node_ids:
        doc = _document(db, car)
        if doc is None:
            raise HTTPException(status_code=422, detail="Causes must be recorded in this CAR investigation first.")
        active = {
            node.id for investigation in InvestigationDocument.model_validate(
                doc.draft.get("investigation") or {}
            ).investigations for node in investigation.nodes
        }
        if not set(payload.cause_node_ids).issubset(active):
            raise HTTPException(status_code=422, detail="Action references a cause outside this CAR.")
    if payload.owner_user_id:
        from amodb.apps.accounts import models as accounts
        exists = db.query(accounts.User.id).filter(
            accounts.User.id == payload.owner_user_id,
            accounts.User.amo_id == str(car.amo_id),
            accounts.User.is_active.is_(True),
            accounts.User.is_system_account.is_(False),
        ).first()
        if not exists:
            raise HTTPException(status_code=422, detail="Owner is not an active tenant user.")


def _add_action(db, car, payload: ActionCreate, *, public: bool, actor_ref: str):
    _assert_action_scope(db, car, payload, public=public)
    # The CAR row is locked by the route, protecting action sequence allocation.
    existing = _actions(db, car)
    row = QualityCarRcaAction(
        id=uuid.uuid4(), amo_id=str(car.amo_id), car_id=car.id,
        sequence_no=max([x.sequence_no for x in existing] + [0]) + 1,
        kind=payload.kind, description=payload.description.strip(),
        cause_node_ids=payload.cause_node_ids,
        evidence_references=payload.evidence_references,
        owner_user_id=payload.owner_user_id,
        external_owner_name=payload.external_owner_name,
        target_date=payload.target_date, priority=payload.priority,
        state="PROPOSED"
    )
    db.add(row)
    db.flush()
    _record_action_event(
        db, car, row, from_state=None, actor_kind="GUEST" if public else "EMPLOYEE",
        actor_ref=actor_ref,
        reason="Corrective action proposed."
    )
    db.commit()
    return _action_dict(row)


@public_router.post("/{invite_token}/corrective-actions", status_code=201)
def add_public_action(invite_token: str, payload: ActionCreate,
    db: Session = Depends(get_db)):
    car = _car_for_guest(db, invite_token, lock=True)
    _assert_guest_editable(db, car)
    return _add_action(db, car, payload, public=True, actor_ref="Invited responder")


@router.post("/corrective-actions", status_code=201)
def add_employee_action(car_id: uuid.UUID, payload: ActionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db)):
    assert_quality_permission(db, ctx, "qms.car.manage")
    car = _car_for_employee(db, ctx, car_id, lock=True)
    if getattr(car.status, "value", car.status) in {"CLOSED", "CANCELLED", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="CAR is locked.")
    return _add_action(db, car, payload, public=False, actor_ref=ctx.user_id)


@public_router.put("/{invite_token}/corrective-actions/{action_id}")
def revise_public_action(invite_token: str, action_id: uuid.UUID, payload: ActionCreate,
    db: Session = Depends(get_db)):
    car = _car_for_guest(db, invite_token, lock=True)
    _assert_guest_editable(db, car)
    row = db.query(QualityCarRcaAction).filter(
        QualityCarRcaAction.amo_id == str(car.amo_id),
        QualityCarRcaAction.car_id == car.id,
        QualityCarRcaAction.id == action_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Action does not belong to this invitation.")
    if row.state not in {"PROPOSED", "REJECTED"}:
        raise HTTPException(status_code=409, detail="Only proposed or returned actions can be revised.")
    _assert_action_scope(db, car, payload, public=True)
    previous = row.state
    row.kind = payload.kind
    row.description = payload.description.strip()
    row.cause_node_ids = payload.cause_node_ids
    row.evidence_references = payload.evidence_references
    row.external_owner_name = payload.external_owner_name
    row.target_date = payload.target_date
    row.priority = payload.priority
    row.state = "PROPOSED"
    _record_action_event(
        db, car, row, from_state=previous, actor_kind="GUEST",
        actor_ref="Invited responder", reason="Responder revised proposed corrective action."
    )
    db.commit()
    return _action_dict(row)


@public_router.patch("/{invite_token}/corrective-actions/{action_id}")
def report_public_action(invite_token: str, action_id: uuid.UUID, payload: ActionProgress,
    db: Session = Depends(get_db)):
    car = _car_for_guest(db, invite_token, lock=True)
    # After CAR submission, the narrative is locked for independent review,
    # but accepted corrective actions still require real implementation.
    if str(getattr(car.status, "value", car.status)) in {"CLOSED", "CANCELLED", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="The CAR is closed or restricted.")
    row = db.query(QualityCarRcaAction).filter(
        QualityCarRcaAction.id == action_id,
        QualityCarRcaAction.amo_id == str(car.amo_id),
        QualityCarRcaAction.car_id == car.id
    ).with_for_update().first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found for this CAR")
    if car.root_cause_status != "ACCEPTED" or car.capa_status != "ACCEPTED":
        raise HTTPException(status_code=409, detail="Quality must accept the RCA and CAPA before implementation progress can be recorded.")
    if row.state not in {"ACCEPTED", "IN_PROGRESS"}:
        raise HTTPException(status_code=409, detail="Only an approved corrective action can enter implementation.")
    previous = row.state
    row.state = payload.state
    row.completion_note = payload.completion_note.strip()
    row.evidence_references = payload.evidence_references
    if row.state == "SUBMITTED":
        if not row.completion_note or not row.evidence_references:
            raise HTTPException(status_code=422, detail="Completion needs a declaration and evidence.")
        row.completed_at = _utcnow()
    _record_action_event(
        db, car, row, from_state=previous, actor_kind="GUEST",
        actor_ref="Invited responder", reason="Respondent reported implementation progress."
    )
    db.commit()
    return _action_dict(row)


@router.patch("/corrective-actions/{action_id}/review")
def review_action(car_id: uuid.UUID, action_id: uuid.UUID, payload: ActionReview,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db)):
    assert_quality_permission(db, ctx, "qms.car.manage")
    car = _car_for_employee(db, ctx, car_id, lock=True)
    if getattr(car.status, "value", car.status) in {"CLOSED", "CANCELLED", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="Closed or escalated CAR cannot receive action approvals.")
    row = db.query(QualityCarRcaAction).filter(
        QualityCarRcaAction.amo_id == ctx.amo_id,
        QualityCarRcaAction.car_id == car.id,
        QualityCarRcaAction.id == action_id
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if ctx.user_id in {row.owner_user_id, car.assigned_to_user_id}:
        raise HTTPException(status_code=403, detail="Action implementer cannot approve their own action.")
    if payload.state == "ACCEPTED" and row.state != "PROPOSED":
        raise HTTPException(status_code=409, detail="Only proposed actions may be approved.")
    if payload.state == "ACCEPTED" and (car.root_cause_status != "ACCEPTED" or car.capa_status != "ACCEPTED"):
        raise HTTPException(status_code=409, detail="Accept the governed RCA and CAPA response before approving proposed implementation.")
    if payload.state == "VERIFIED" and (row.state != "SUBMITTED" or not row.evidence_references):
        raise HTTPException(status_code=409, detail="Verify submitted implementation evidence before approving.")
    if payload.state == "VERIFIED" and (
        car.root_cause_status != "ACCEPTED" or car.capa_status != "ACCEPTED"
    ):
        raise HTTPException(status_code=409, detail="Quality must accept the RCA and corrective action plan before implementation verification.")
    if payload.state == "REJECTED" and row.state not in {"PROPOSED", "SUBMITTED"}:
        raise HTTPException(status_code=409, detail="This action is not in a reviewable state.")
    previous = row.state
    row.state = payload.state
    row.quality_review_note = payload.reason.strip()
    row.reviewed_by_user_id = ctx.user_id
    row.reviewed_at = _utcnow()
    _record_action_event(
        db, car, row, from_state=previous, actor_kind="EMPLOYEE",
        actor_ref=ctx.user_id, reason="Quality decision: " + payload.reason.strip()
    )
    db.commit()
    return _action_dict(row)

class InviteAccessChange(BaseModel):
    expires_at: datetime | None = None
    revoke: bool = False
    reason: str = Field(min_length=8, max_length=4000)


def _invite_control_dict(control):
    return {
        "expires_at": control.expires_at if control else None,
        "revoked_at": control.revoked_at if control else None,
        "reason": control.reason if control else "",
        "updated_by_user_id": control.updated_by_user_id if control else None,
        "updated_at": control.updated_at if control else None,
    }


@router.get("/invite-access")
def read_invite_access_control(
    car_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")),
    db: Session = Depends(get_read_db),
):
    car = _car_for_employee(db, ctx, car_id)
    return _invite_control_dict(_control_for_car(db, car))


@router.put("/invite-access")
def update_invite_access_control(
    car_id: uuid.UUID, payload: InviteAccessChange,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    assert_quality_permission(db, ctx, "qms.car.manage")
    car = _car_for_employee(db, ctx, car_id, lock=True)
    control = _control_for_car(db, car)
    if control is not None and control.revoked_at is not None:
        raise HTTPException(status_code=409, detail="A revoked token cannot be reactivated. Issue a new controlled invitation.")
    if payload.expires_at is not None:
        expiry = payload.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= _utcnow() and not payload.revoke:
            raise HTTPException(status_code=422, detail="Future expiry must be after the current time.")
    if control is None:
        control = QualityCarInviteAccessControl(
            id=uuid.uuid4(), amo_id=ctx.amo_id, car_id=car.id,
            reason=payload.reason.strip(), updated_by_user_id=ctx.user_id,
        )
        db.add(control)
    if "expires_at" in payload.model_fields_set:
        control.expires_at = payload.expires_at
    if payload.revoke:
        control.revoked_at = _utcnow()
    control.reason = payload.reason.strip()
    control.updated_by_user_id = ctx.user_id
    from .service import add_car_action
    add_car_action(
        db=db, car=car, action_type=models.CARActionType.COMMENT,
        message=("CAR invitation revoked: " if payload.revoke else "CAR invitation expiry revised: ") + payload.reason.strip(),
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return _invite_control_dict(control)


class AdoptEffectivenessProposal(BaseModel):
    responsible_reviewer_user_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=8, max_length=4000)


@router.post("/effectiveness-plan", status_code=201)
def adopt_car_effectiveness_proposal(
    car_id: uuid.UUID, payload: AdoptEffectivenessProposal,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    """Quality alone adopts a responder's proposal into authoritative assurance planning."""
    assert_quality_permission(db, ctx, "qms.car.manage")
    car = _car_for_employee(db, ctx, car_id, lock=True)
    if getattr(car.status, "value", car.status) in {"CLOSED", "CANCELLED", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="Locked CAR cannot receive a new effectiveness plan.")
    if car.root_cause_status != "ACCEPTED" or car.capa_status != "ACCEPTED":
        raise HTTPException(status_code=409, detail="Accept the root cause and CAPA before adopting the effectiveness proposal.")
    doc = _document(db, car)
    if doc is None or doc.submitted_snapshot is None:
        raise HTTPException(status_code=409, detail="No submitted structured RCA proposal exists.")
    investigation = InvestigationDocument.model_validate(
        doc.submitted_snapshot.get("investigation") or {}
    )
    proposal = investigation.effectiveness_proposal
    if proposal is None:
        raise HTTPException(status_code=422, detail="Responder has not supplied an effectiveness proposal.")
    if not all((
        len(proposal.expected_result.strip()) >= 8,
        len(proposal.verification_method.strip()) >= 8,
        len(proposal.measurable_success_criterion.strip()) >= 8,
        len(proposal.observation_period.strip()) >= 3,
        proposal.proposed_review_date is not None,
    )):
        raise HTTPException(status_code=422, detail="Complete the expected result, measurement, verification method, observation period and review date.")
    if proposal.proposed_review_date < date.today():
        raise HTTPException(status_code=422, detail="Update the expired proposed review date through controlled rework.")
    if payload.responsible_reviewer_user_id in {car.assigned_to_user_id} | {
        action.owner_user_id for action in _actions(db, car)
    }:
        raise HTTPException(status_code=403, detail="An action implementer cannot independently review effectiveness.")
    from .assurance_case_router import _assert_user, _case_ref, _add_event
    from .assurance_case_models import QualityAssuranceCase, QualityEffectivenessPlan
    _assert_user(db, amo_id=ctx.amo_id, user_id=payload.responsible_reviewer_user_id)
    previous = db.query(QualityEffectivenessPlan).filter(
        QualityEffectivenessPlan.amo_id == ctx.amo_id,
        QualityEffectivenessPlan.source_type == "CAR",
        QualityEffectivenessPlan.source_id == str(car.id),
        QualityEffectivenessPlan.status != "CANCELLED",
    ).order_by(QualityEffectivenessPlan.created_at.desc()).first()
    if previous and previous.status != "CONCLUDED":
        raise HTTPException(status_code=409, detail="A governed effectiveness plan is already active for this CAR.")
    case = QualityAssuranceCase(
        amo_id=ctx.amo_id, case_ref=_case_ref(), case_type="EFFECTIVENESS",
        title="CAR " + str(car.car_number) + " — effectiveness verification",
        description=payload.reason.strip(), severity="MEDIUM", status="EFFECTIVENESS_REVIEW",
        source_references=[{"source_type": "CAR", "source_id": str(car.id)}],
        regulatory_basis=[], owner_user_id=payload.responsible_reviewer_user_id,
        due_date=proposal.proposed_review_date,
        created_by_user_id=ctx.user_id, updated_by_user_id=ctx.user_id,
    )
    db.add(case)
    db.flush()
    plan = QualityEffectivenessPlan(
        amo_id=ctx.amo_id, case_id=case.id,
        source_type="CAR", source_id=str(car.id),
        source_route="/maintenance/" + ctx.amo_code + "/quality/cars/" + str(car.id) + "/overview",
        expected_outcome=proposal.expected_result.strip(),
        effectiveness_measure=proposal.measurable_success_criterion.strip(),
        verification_method=proposal.verification_method.strip(),
        observation_window=proposal.observation_period.strip(),
        source_indicators=[{"source_type": "RESPONDER_PROPOSAL", "supporting_records": proposal.supporting_records}],
        responsible_reviewer_user_id=payload.responsible_reviewer_user_id,
        planned_review_date=proposal.proposed_review_date,
        status="PLANNED", created_by_user_id=ctx.user_id
    )
    db.add(plan)
    db.flush()
    _add_event(db, row=case, event_type="CREATED", reason=payload.reason.strip(), actor_user_id=ctx.user_id)
    _add_event(db, row=case, event_type="EFFECTIVENESS_PLANNED", reason="Independent review planned from submitted CAR RCA.", actor_user_id=ctx.user_id)
    db.commit()
    return {
        "case_id": str(case.id), "case_ref": case.case_ref,
        "plan_id": str(plan.id), "planned_review_date": plan.planned_review_date,
        "reviewer_user_id": plan.responsible_reviewer_user_id,
    }
