from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlalchemy.orm import Session, noload, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.training import models as training_models
from amodb.apps.training.integration import (
    QMS_ADMIN,
    QMS_COMPETENCE_CODES,
    QMS_INIT,
    QMS_REF,
    current_training_evidence,
    qms_auditor_competence_evidence,
)
from amodb.database import get_read_db, get_write_db
from amodb.user_id import generate_user_id

from . import models as quality_models
from .people_competence import (
    active_qm_bypass,
    apply_auto_suspend_if_currency_lapsed,
    cap_privilege_expires_on,
    evaluate_qms_competence_for_privilege,
    record_qm_training_bypass,
    select_best_qms_certificate_record,
    user_ids_matching_rule_training,
)
from .people_default_rules import (
    ensure_default_quality_privilege_rules,
    sync_default_quality_privilege_rule_competence,
)
from .people_models import (
    QualityIndependenceDeclaration,
    QualityPrivilege,
    QualityPrivilegeDecision,
    QualityPrivilegeRule,
)
from .independence_conflict import (
    evaluate_independence_conflicts,
    get_independence_policy,
    set_independence_policy,
)
from .planner_schedule_models import QMSPlannerScheduleMetadata
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    require_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)

router = APIRouter(prefix="/people", tags=["Quality people and privileges"])

PrivilegeType = Literal["AUDITOR", "LEAD_AUDITOR", "QUALITY_INSPECTOR", "AUTHORIZATION_REVIEWER", "CUSTOM"]
DecisionType = Literal["GRANT", "RENEW", "SUSPEND", "REINSTATE", "REVOKE", "EXPIRE", "REJECT"]
ContextType = Literal["AUDIT", "AUDIT_SCHEDULE", "PROGRAMME_ITEM", "ASSURANCE_CASE", "MISSION", "OTHER"]
Declaration = Literal["INDEPENDENT", "CONFLICT", "REQUIRES_REVIEW"]

_PRIVILEGE_DECISION_ALLOWED_FROM: dict[str, set[str]] = {
    "GRANT": {"DRAFT"},
    "REJECT": {"DRAFT"},
    "RENEW": {"ACTIVE", "EXPIRED"},
    "SUSPEND": {"ACTIVE"},
    "REINSTATE": {"SUSPENDED"},
    "REVOKE": {"ACTIVE", "SUSPENDED"},
    "EXPIRE": {"ACTIVE", "SUSPENDED"},
}


class PrivilegeRuleCreate(BaseModel):
    privilege_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_\-]+$")
    title: str = Field(min_length=3, max_length=255)
    privilege_type: PrivilegeType
    description: str | None = None
    required_training_course_codes: list[str] = Field(default_factory=list, max_length=50)
    independence_required: bool = True
    max_concurrent_assignments: int | None = Field(default=None, ge=1, le=100)
    scope_schema: dict[str, Any] = Field(default_factory=dict)


class PrivilegeRuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    required_training_course_codes: list[str] | None = Field(default=None, max_length=50)
    independence_required: bool | None = None
    max_concurrent_assignments: int | None = Field(default=None, ge=1, le=100)
    scope_schema: dict[str, Any] | None = None
    is_active: bool | None = None


class PrivilegeCreate(BaseModel):
    rule_id: str = Field(min_length=1, max_length=36)
    user_id: str = Field(min_length=1, max_length=36)
    scope_key: str = Field(default="GLOBAL", min_length=1, max_length=255)
    scope: dict[str, Any] = Field(default_factory=dict)
    limitations: list[dict[str, Any] | str] = Field(default_factory=list)


class PrivilegeDecisionCreate(BaseModel):
    decision_type: DecisionType
    rationale: str = Field(min_length=8, max_length=4000)
    effective_from: date | None = None
    expires_on: date | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class IndependenceCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    context_type: ContextType
    context_id: str = Field(min_length=1, max_length=160)
    declaration: Declaration
    relationship_to_subject: str | None = Field(default=None, max_length=2000)
    rationale: str = Field(min_length=8, max_length=4000)
    source_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class RankChange(BaseModel):
    rule_id: str = Field(min_length=1, max_length=36)
    rationale: str = Field(min_length=8, max_length=4000)


class QmTrainingBypassCreate(BaseModel):
    rationale: str = Field(min_length=8, max_length=4000)
    valid_until: date



def _lock_person(db: Session, amo_id: str, user_id: str):
    person = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id, account_models.User.id == user_id,
    ).with_for_update().first()
    if person is None:
        raise HTTPException(404, "Person not found.")
    return person


def _retire_other_ranks(db: Session, ctx: TenantContext, privilege: QualityPrivilege):
    rank_rules = db.query(QualityPrivilegeRule.id).filter(
        QualityPrivilegeRule.amo_id == ctx.amo_id,
        QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]),
    )
    others = db.query(QualityPrivilege).options(noload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.user_id == privilege.user_id,
        QualityPrivilege.id != privilege.id, QualityPrivilege.rule_id.in_(rank_rules),
        QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
    ).with_for_update().all()
    for other in others:
        decision = QualityPrivilegeDecision(
            amo_id=ctx.amo_id, privilege_id=other.id, decision_type="REVOKE", resulting_status="REVOKED",
            rationale="Replaced by the person's current auditor rank.",
            eligibility_snapshot={"replacement_rank": privilege.privilege_code}, source_references=[],
            decided_by_user_id=ctx.user_id, decided_at=_utcnow(),
        )
        db.add(decision)
        db.flush()
        other.status = "REVOKED"
        other.latest_decision_id = decision.id
        other.updated_by_user_id = ctx.user_id
        other.updated_at = _utcnow()


def _apply_rank_change(
    db: Session,
    ctx: TenantContext,
    row: QualityPrivilege,
    rule: QualityPrivilegeRule,
    rationale: str,
) -> QualityPrivilege:
    previous = _rule(db, amo_id=ctx.amo_id, rule_id=row.rule_id)
    if not rule.is_active or rule.privilege_type not in {"AUDITOR", "LEAD_AUDITOR"} or previous.privilege_type not in {"AUDITOR", "LEAD_AUDITOR"}:
        raise HTTPException(422, "Choose an active auditor rank.")
    if row.status != "ACTIVE":
        raise HTTPException(409, "Activate the authorization before changing rank.")
    if row.expires_on and row.expires_on < date.today():
        raise HTTPException(409, "Renew the expired authorization before changing rank.")
    eligibility = evaluate_eligibility(
        db, amo_id=ctx.amo_id, user_id=row.user_id, rule=rule, as_of=date.today(),
        require_active_privilege=False, actor_user_id=ctx.user_id,
    )
    gates = {key: value for key, value in eligibility["hard_gates"].items() if key not in {"active_privilege", "independence"}}
    if not all(gates.values()):
        raise HTTPException(409, {"message": "Required training or personnel checks are incomplete.", "eligibility": eligibility})
    capped_expires = cap_privilege_expires_on(
        row.expires_on,
        eligibility.get("training") if isinstance(eligibility, dict) else None,
        as_of=date.today(),
    )
    duplicates = db.query(QualityPrivilege).options(noload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.user_id == row.user_id,
        QualityPrivilege.privilege_code == rule.privilege_code, QualityPrivilege.scope_key == row.scope_key,
        QualityPrivilege.id != row.id,
    ).all()
    for duplicate in duplicates:
        db.query(QualityPrivilegeDecision).filter(
            QualityPrivilegeDecision.privilege_id == duplicate.id,
            QualityPrivilegeDecision.amo_id == ctx.amo_id,
        ).update({"privilege_id": row.id}, synchronize_session=False)
        db.delete(duplicate)
    db.flush()
    old_code = row.privilege_code
    row.rule_id = rule.id
    row.privilege_code = rule.privilege_code
    row.expires_on = capped_expires
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    decision = QualityPrivilegeDecision(
        amo_id=ctx.amo_id, privilege_id=row.id, decision_type="RENEW", resulting_status="ACTIVE",
        rationale=rationale.strip(), eligibility_snapshot=eligibility,
        source_references=[{"previous_rank": old_code, "new_rank": rule.privilege_code}],
        effective_from=row.effective_from, expires_on=row.expires_on,
        decided_by_user_id=ctx.user_id, decided_at=_utcnow(),
    )
    db.add(decision)
    db.flush()
    row.latest_decision_id = decision.id
    _retire_other_ranks(db, ctx, row)
    return row


@router.post("/privileges/{privilege_id}/rank")
def change_rank(privilege_id: str, payload: RankChange,
                ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)):
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id).first()
    if row is None:
        raise HTTPException(404, "Authorization not found.")
    _lock_person(db, ctx.amo_id, row.user_id)
    db.refresh(row)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.rule_id)
    _apply_rank_change(db, ctx, row, rule, payload.rationale)
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    db.refresh(row)
    return _privilege_dict(row, include_history=True)


@router.delete("/privileges/{privilege_id}", status_code=204)
def purge_privilege(privilege_id: str, ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db)):
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id).first()
    if row is None:
        raise HTTPException(404, "Authorization not found.")
    _lock_person(db, ctx.amo_id, row.user_id)
    db.refresh(row)
    if row.status not in {"REVOKED", "DRAFT", "EXPIRED"}:
        raise HTTPException(409, "Revoke the authorization before deleting it.")
    db.query(QualityPrivilegeDecision).filter(QualityPrivilegeDecision.amo_id == ctx.amo_id,
        QualityPrivilegeDecision.privilege_id == row.id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()


def _qms_training_certificate_candidates(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """List Training certificate artifacts for this person's QMS competence courses.

    Course selection follows the same Training policy mapping used by People pills
    (exact course_id / group_code QMS / QUALITY_SYSTEMS + kind) — not alias guesses.
    """

    from amodb.apps.training.integration import canonicalize_qms_competence_code

    evidence = qms_auditor_competence_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        as_of=date.today(),
        track_admin=True,
    )
    record_ids = [
        str(row.get("record_id"))
        for row in (evidence.get("tracked_records") or [])
        if row.get("record_id")
    ]
    if not record_ids:
        # Fall back to records on courses Training maps to competence codes.
        rows = (
            db.query(training_models.TrainingRecord, training_models.TrainingCourse)
            .join(training_models.TrainingCourse, training_models.TrainingCourse.id == training_models.TrainingRecord.course_id)
            .filter(
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.user_id == user_id,
                training_models.TrainingCourse.amo_id == amo_id,
            )
            .order_by(
                training_models.TrainingRecord.valid_until.desc().nullslast(),
                training_models.TrainingRecord.completion_date.desc().nullslast(),
                training_models.TrainingRecord.created_at.desc().nullslast(),
            )
            .limit(250)
            .all()
        )
    else:
        rows = (
            db.query(training_models.TrainingRecord, training_models.TrainingCourse)
            .join(training_models.TrainingCourse, training_models.TrainingCourse.id == training_models.TrainingRecord.course_id)
            .filter(
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.id.in_(record_ids),
                training_models.TrainingCourse.amo_id == amo_id,
            )
            .order_by(
                training_models.TrainingRecord.valid_until.desc().nullslast(),
                training_models.TrainingRecord.completion_date.desc().nullslast(),
                training_models.TrainingRecord.created_at.desc().nullslast(),
            )
            .all()
        )

    items: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    wanted = set(QMS_COMPETENCE_CODES)
    for record, course in rows:
        code = canonicalize_qms_competence_code(course, requested=wanted)
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        cert_file = (
            db.query(training_models.TrainingFile)
            .filter(
                training_models.TrainingFile.amo_id == amo_id,
                training_models.TrainingFile.record_id == record.id,
                training_models.TrainingFile.kind.in_(
                    [
                        training_models.TrainingFileKind.CERTIFICATE,
                        training_models.TrainingFileKind.EVIDENCE,
                    ]
                ),
            )
            .order_by(training_models.TrainingFile.uploaded_at.desc())
            .first()
        )
        issue = (
            db.query(training_models.TrainingCertificateIssue)
            .filter(
                training_models.TrainingCertificateIssue.amo_id == amo_id,
                training_models.TrainingCertificateIssue.record_id == record.id,
            )
            .first()
        )
        items.append({
            "record_id": str(record.id),
            "course_code": code,
            "course_name": course.course_name,
            "completion_date": record.completion_date.isoformat() if record.completion_date else None,
            "valid_until": record.valid_until.isoformat() if record.valid_until else None,
            "verification_status": _enum_value(record.verification_status),
            "has_file": cert_file is not None,
            "file_id": str(cert_file.id) if cert_file else None,
            "original_filename": cert_file.original_filename if cert_file else None,
            "content_type": cert_file.content_type if cert_file else None,
            "storage_path": cert_file.storage_path if cert_file else None,
            "has_certificate_issue": issue is not None,
            "certificate_number": issue.certificate_number if issue else None,
        })
    return items


def _stream_training_certificate_file(candidate: dict[str, Any]):
    from pathlib import Path
    from fastapi.responses import FileResponse

    path = Path(str(candidate.get("storage_path") or ""))
    if not path.is_file():
        return None
    filename = candidate.get("original_filename") or f"{candidate.get('course_code')}-certificate.pdf"
    return FileResponse(
        path,
        media_type=candidate.get("content_type") or "application/pdf",
        filename=str(filename),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/privileges/{privilege_id}/qms-certificates")
def list_qms_certificates(
    privilege_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id).first()
    if row is None:
        raise HTTPException(404, "Authorization not found.")
    items = _qms_training_certificate_candidates(db, amo_id=ctx.amo_id, user_id=str(row.user_id))
    best = select_best_qms_certificate_record(items)
    return {"items": items, "preferred": best, "privilege_id": privilege_id}


@router.get("/privileges/{privilege_id}/record")
def authorization_record(privilege_id: str, ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
                         db: Session = Depends(get_read_db)):
    from io import BytesIO
    from html import escape
    from fastapi.responses import Response
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id).first()
    if row is None:
        raise HTTPException(404, "Authorization not found.")
    person = db.query(account_models.User).filter(account_models.User.amo_id == ctx.amo_id, account_models.User.id == row.user_id).first()
    if person is None:
        raise HTTPException(404, "Person not found.")
    # Prefer Training certificate artifacts for QMS course records.
    candidates = _qms_training_certificate_candidates(db, amo_id=ctx.amo_id, user_id=str(row.user_id))
    with_files = [item for item in candidates if item.get("has_file") and item.get("storage_path")]
    preferred = select_best_qms_certificate_record(with_files)
    if preferred:
        streamed = _stream_training_certificate_file(preferred)
        if streamed is not None:
            return streamed
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=row.rule_id)
    name = person.full_name or f"{person.first_name or ''} {person.last_name or ''}".strip() or person.email or "Person unavailable"
    output = BytesIO()
    styles = getSampleStyleSheet()
    title = "Quality authorization certificate" if person.is_active and row.status == "ACTIVE" and (not row.expires_on or row.expires_on >= date.today()) and (not row.effective_from or row.effective_from <= date.today()) else "Quality authorization record"
    lines = [Paragraph(title, styles["Title"]), Spacer(1, 18)]
    for label, value in [("Name", name), ("Authorization", rule.title), ("Status", row.status), ("Scope", row.scope_key),
                         ("Effective from", row.effective_from), ("Expires", row.expires_on), ("Generated", date.today())]:
        lines.append(Paragraph(f"<b>{label}:</b> {escape(str(value or 'Not set'))}", styles["Normal"]))
        lines.append(Spacer(1, 8))
    for decision in row.decisions:
        lines.append(Paragraph(escape(f"{decision.decided_at:%d %b %Y} — {decision.decision_type}: {decision.rationale}"), styles["Normal"]))
        lines.append(Spacer(1, 6))
    SimpleDocTemplate(output).build(lines)
    return Response(output.getvalue(), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="quality-authorization.pdf"', "Cache-Control": "no-store"})


@router.post("/privileges/{privilege_id}/qm-bypass", status_code=status.HTTP_201_CREATED)
def create_qm_training_bypass(
    privilege_id: str,
    payload: QmTrainingBypassCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Quality manager time-bounded bypass of the training/expiry gate."""

    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = (
        db.query(QualityPrivilege)
        .options(noload(QualityPrivilege.rule), selectinload(QualityPrivilege.decisions))
        .filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Authorization not found.")
    try:
        decision = record_qm_training_bypass(
            db,
            amo_id=ctx.amo_id,
            privilege=row,
            rationale=payload.rationale,
            valid_until=payload.valid_until,
            actor_user_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    db.refresh(row)
    db.refresh(decision)
    return {
        "privilege": _privilege_dict(row, include_history=True),
        "decision": _decision_dict(decision),
        "bypass": active_qm_bypass(row, as_of=date.today()),
    }


@router.post("/privileges/{privilege_id}/authorization-evidence", status_code=status.HTTP_201_CREATED)
async def upload_authorization_evidence(
    privilege_id: str,
    file: UploadFile = File(...),
    course_code: str = Form(default=QMS_INIT),
    completion_date: date | None = Form(default=None),
    valid_until: date | None = Form(default=None),
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Upload authorization evidence into Training (PENDING) when no verified record exists.

    Reuses Training storage paths — does not create a parallel QMS DMS store.
    PENDING records do not satisfy eligibility until verified in Training.
    """

    from pathlib import Path
    import hashlib
    import os

    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    privilege = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id,
    ).first()
    if privilege is None:
        raise HTTPException(404, "Authorization not found.")

    code = str(course_code or QMS_INIT).strip().upper()
    if code not in set(QMS_COMPETENCE_CODES):
        raise HTTPException(422, f"course_code must be one of {', '.join(QMS_COMPETENCE_CODES)}.")

    # Reject when a verified current record already covers this course (or currency).
    existing_current = current_training_evidence(
        db,
        amo_id=ctx.amo_id,
        user_id=str(privilege.user_id),
        required_codes=[code],
        as_of=date.today(),
    )
    if existing_current.get("passed"):
        raise HTTPException(
            409,
            f"A verified current {code} Training record already exists. Renew or supersede it in Training instead of uploading a duplicate.",
        )
    if code in {QMS_INIT, QMS_REF}:
        currency = qms_auditor_competence_evidence(
            db,
            amo_id=ctx.amo_id,
            user_id=str(privilege.user_id),
            as_of=date.today(),
            track_admin=False,
        )
        if currency.get("currency_passed") and code == QMS_INIT:
            raise HTTPException(
                409,
                "QMS currency is already covered by a current Training record. Upload QMS-REF only when renewing, or wait until currency lapses.",
            )

    course = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == ctx.amo_id,
            training_models.TrainingCourse.course_id == code,
        )
        .first()
    )
    if course is None:
        titles = {
            QMS_INIT: "QMS Initial Auditor Training",
            QMS_REF: "QMS Recurrent Auditor Training",
            QMS_ADMIN: "QMS Lead Auditor Administration",
        }
        course = training_models.TrainingCourse(
            amo_id=ctx.amo_id,
            course_id=code,
            course_name=titles.get(code, code),
            frequency_months=24 if code == QMS_REF else (36 if code == QMS_ADMIN else None),
            is_active=True,
            created_by_user_id=ctx.user_id,
            updated_by_user_id=ctx.user_id,
        )
        db.add(course)
        db.flush()

    completed_on = completion_date or date.today()
    if valid_until is not None and valid_until < completed_on:
        raise HTTPException(422, "valid_until cannot precede completion_date.")

    record = training_models.TrainingRecord(
        amo_id=ctx.amo_id,
        user_id=str(privilege.user_id),
        course_id=course.id,
        completion_date=completed_on,
        valid_until=valid_until,
        remarks="Authorization evidence uploaded from QMS People (pending Training verification).",
        verification_status=training_models.TrainingRecordVerificationStatus.PENDING,
        is_manual_entry=True,
        record_status="ACTIVE",
        created_by_user_id=ctx.user_id,
    )
    db.add(record)
    db.flush()

    upload_root = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve()
    max_bytes = int(os.getenv("TRAINING_MAX_UPLOAD_BYTES", "52428800") or "52428800")
    amo_folder = upload_root / ctx.amo_id
    amo_folder.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "authorization-evidence.bin"
    ext = "".join(Path(original_name).suffixes)[-20:]
    file_id = generate_user_id()
    dest_path = amo_folder / f"{file_id}{ext}"
    sha = hashlib.sha256()
    total = 0
    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes and total > max_bytes:
                try:
                    dest_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise HTTPException(status_code=413, detail="File too large.")
            sha.update(chunk)
            out.write(chunk)

    training_file = training_models.TrainingFile(
        id=file_id,
        amo_id=ctx.amo_id,
        owner_user_id=str(privilege.user_id),
        kind=training_models.TrainingFileKind.CERTIFICATE,
        course_id=course.id,
        record_id=record.id,
        original_filename=original_name,
        storage_path=str(dest_path),
        content_type=file.content_type,
        size_bytes=total,
        sha256=sha.hexdigest(),
        review_status=training_models.TrainingFileReviewStatus.PENDING,
        uploaded_by_user_id=ctx.user_id,
    )
    db.add(training_file)
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    db.refresh(record)
    db.refresh(training_file)
    return {
        "record_id": str(record.id),
        "file_id": str(training_file.id),
        "course_code": code,
        "course_id": str(course.id),
        "verification_status": _enum_value(record.verification_status),
        "review_status": _enum_value(training_file.review_status),
        "message": "Evidence stored in Training as PENDING. It does not satisfy eligibility until verified.",
        "source_route": f"/training/records/{record.id}",
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _person(db: Session, *, amo_id: str, user_id: str) -> account_models.User:
    user = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not user:
        raise HTTPException(status_code=422, detail="Selected person is inactive, belongs to another tenant, or does not exist.")
    return user


def _rule(db: Session, *, amo_id: str, rule_id: str | None = None, privilege_code: str | None = None) -> QualityPrivilegeRule:
    query = db.query(QualityPrivilegeRule).filter(QualityPrivilegeRule.amo_id == amo_id)
    if rule_id:
        query = query.filter(QualityPrivilegeRule.id == rule_id)
    elif privilege_code:
        query = query.filter(QualityPrivilegeRule.privilege_code == privilege_code)
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Quality privilege rule not found.")
    return row


def _training_evidence(db: Session, *, amo_id: str, user_id: str, required_codes: list[str], as_of: date) -> dict[str, Any]:
    return current_training_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required_codes=required_codes,
        as_of=as_of,
    )


def _independence_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    required: bool,
    context_type: str | None,
    context_id: str | None,
    assignment_scope_key: str | None = None,
) -> dict[str, Any]:
    if not required:
        return {"required": False, "passed": True, "declaration": None, "conflicts": [], "enforced": False}
    # People pill loads omit assignment context — skip conflict scans until preflight.
    if not context_type or not context_id:
        return {
            "required": True,
            "passed": None,
            "declaration": None,
            "message": "Assignment context is required to evaluate independence.",
            "conflicts": [],
            "remediations": [],
            "notes": ["Assign an audit or schedule context to run full independence conflict detection."],
            "enforced": True,
            "policy": None,
            "work_order_module_connected": False,
        }
    assessment = evaluate_independence_conflicts(
        db,
        amo_id=amo_id,
        user_id=user_id,
        context_type=context_type,
        context_id=context_id,
        assignment_scope_key=assignment_scope_key,
    )
    return {
        "required": True,
        "passed": assessment.get("passed"),
        "declaration": (assessment.get("impartiality_form") or {}).get("declaration"),
        "declaration_id": None,
        "rationale": (assessment.get("impartiality_form") or {}).get("rationale"),
        "declared_at": (assessment.get("impartiality_form") or {}).get("declared_at"),
        "message": assessment.get("message"),
        "conflicts": assessment.get("conflicts") or [],
        "remediations": assessment.get("remediations") or [],
        "notes": assessment.get("notes") or [],
        "enforced": assessment.get("enforced"),
        "policy": assessment.get("policy"),
        "work_order_module_connected": assessment.get("work_order_module_connected"),
        "hard_conflict_count": assessment.get("hard_conflict_count", 0),
    }


def _workload_evidence(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    on_date: date,
    capacity: int | None,
) -> dict[str, Any]:
    # Unlimited capacity: capacity gate always passes — avoid scanning the planner.
    if capacity is None:
        return {
            "date": on_date.isoformat(),
            "active_assignments": 0,
            "max_concurrent_assignments": None,
            "passed": True,
            "assignments": [],
        }
    window_start = on_date - timedelta(days=90)
    window_end = on_date + timedelta(days=90)
    schedules = db.query(quality_models.QMSAuditSchedule, QMSPlannerScheduleMetadata).join(
        QMSPlannerScheduleMetadata,
        and_(
            QMSPlannerScheduleMetadata.schedule_id == quality_models.QMSAuditSchedule.id,
            QMSPlannerScheduleMetadata.amo_id == quality_models.QMSAuditSchedule.amo_id,
        ),
    ).filter(
        quality_models.QMSAuditSchedule.amo_id == amo_id,
        QMSPlannerScheduleMetadata.amo_id == amo_id,
        quality_models.QMSAuditSchedule.is_active.is_(True),
        quality_models.QMSAuditSchedule.deleted_at.is_(None),
        quality_models.QMSAuditSchedule.next_due_date >= window_start,
        quality_models.QMSAuditSchedule.next_due_date <= window_end,
        QMSPlannerScheduleMetadata.lifecycle_status == "ACTIVE",
    ).limit(1000).all()

    assignments: list[dict[str, Any]] = []
    for schedule, metadata in schedules:
        schedule_users = {
            str(value)
            for value in [
                schedule.lead_auditor_user_id,
                schedule.observer_auditor_user_id,
                schedule.assistant_auditor_user_id,
                *_json_list(metadata.attendee_user_ids_json),
            ]
            if value
        }
        if user_id not in schedule_users:
            continue
        end_date = metadata.end_date or (
            schedule.next_due_date + timedelta(days=max(int(schedule.duration_days or 1), 1) - 1)
        )
        if schedule.next_due_date <= on_date <= end_date:
            assignments.append({
                "schedule_id": str(schedule.id),
                "title": schedule.title,
                "start_date": schedule.next_due_date.isoformat(),
                "end_date": end_date.isoformat(),
                "source_route": f"/quality/audits/plan?schedule={schedule.id}",
            })
    count = len(assignments)
    return {
        "date": on_date.isoformat(),
        "active_assignments": count,
        "max_concurrent_assignments": capacity,
        "passed": count < capacity,
        "assignments": assignments,
    }


def evaluate_eligibility(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    rule: QualityPrivilegeRule,
    as_of: date,
    context_type: str | None = None,
    context_id: str | None = None,
    require_active_privilege: bool = True,
    actor_user_id: str | None = None,
    apply_auto_suspend: bool = True,
) -> dict[str, Any]:
    user = _person(db, amo_id=amo_id, user_id=user_id)
    training = evaluate_qms_competence_for_privilege(
        db,
        amo_id=amo_id,
        user_id=user_id,
        rule=rule,
        as_of=as_of,
    )
    independence = _independence_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        required=bool(rule.independence_required),
        context_type=context_type,
        context_id=context_id,
    )
    workload = _workload_evidence(
        db,
        amo_id=amo_id,
        user_id=user_id,
        on_date=as_of,
        capacity=rule.max_concurrent_assignments,
    )
    privilege_query = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == amo_id,
        QualityPrivilege.user_id == user_id,
        QualityPrivilege.privilege_code == rule.privilege_code,
        QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
    )
    if apply_auto_suspend:
        privilege_query = privilege_query.options(selectinload(QualityPrivilege.decisions))
    else:
        privilege_query = privilege_query.options(noload(QualityPrivilege.decisions))
    privilege = privilege_query.order_by(QualityPrivilege.updated_at.desc()).first()
    bypass = active_qm_bypass(privilege, as_of=as_of) if privilege else None
    auto_suspend_decision = None
    if apply_auto_suspend and privilege is not None and privilege.status == "ACTIVE":
        auto_suspend_decision = apply_auto_suspend_if_currency_lapsed(
            db,
            amo_id=amo_id,
            privilege=privilege,
            rule=rule,
            competence=training,
            as_of=as_of,
            actor_user_id=actor_user_id,
        )
        if auto_suspend_decision is not None:
            db.flush()

    privilege_active = privilege is not None and privilege.status == "ACTIVE"
    privilege_passed = privilege_active
    if privilege and privilege.effective_from and privilege.effective_from > as_of:
        privilege_passed = False
    if privilege and privilege.expires_on and privilege.expires_on < as_of:
        privilege_passed = False

    training_passed = bool(training.get("passed")) or bypass is not None
    hard_gates = {
        "workforce_active": True,
        "training_current_verified": training_passed,
        "independence": independence["passed"] is not False,
        "capacity": bool(workload["passed"]),
        "active_privilege": privilege_passed if require_active_privilege else True,
    }
    return {
        "eligible": all(hard_gates.values()),
        "as_of": as_of.isoformat(),
        "person": {
            "user_id": str(user.id),
            "full_name": str(getattr(user, "full_name", "") or "").strip() or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": getattr(user, "email", None),
            "role": _enum_value(getattr(user, "role", None)),
        },
        "rule": {
            "id": str(rule.id),
            "privilege_code": rule.privilege_code,
            "title": rule.title,
            "privilege_type": rule.privilege_type,
        },
        "hard_gates": hard_gates,
        "training": {
            **training,
            "passed": training_passed,
            "qm_bypass": bypass,
            "competence_package": training.get("package"),
        },
        "qm_bypass": bypass,
        "auto_suspended": auto_suspend_decision is not None,
        "independence": independence,
        "workload": workload,
        "active_privilege": {
            "id": str(privilege.id),
            "status": privilege.status,
            "effective_from": privilege.effective_from.isoformat() if privilege and privilege.effective_from else None,
            "expires_on": privilege.expires_on.isoformat() if privilege and privilege.expires_on else None,
        } if privilege else None,
    }


def _rule_dict(row: QualityPrivilegeRule, *, active_holders: int = 0, total_holders: int = 0, live_holders: int = 0) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "privilege_code": row.privilege_code,
        "title": row.title,
        "privilege_type": row.privilege_type,
        "description": row.description,
        "required_training_course_codes": list(row.required_training_course_codes or []),
        "independence_required": bool(row.independence_required),
        "max_concurrent_assignments": row.max_concurrent_assignments,
        "scope_schema": row.scope_schema or {},
        "is_active": bool(row.is_active),
        "updated_at": row.updated_at,
        "active_holders": int(active_holders),
        "live_holders": int(live_holders),
        "total_holders": int(total_holders),
        "can_delete": int(live_holders) == 0,
    }


def _decision_dict(row: QualityPrivilegeDecision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "decision_type": row.decision_type,
        "resulting_status": row.resulting_status,
        "rationale": row.rationale,
        "eligibility_snapshot": row.eligibility_snapshot,
        "source_references": row.source_references,
        "effective_from": row.effective_from,
        "expires_on": row.expires_on,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
    }


def _privilege_dict(row: QualityPrivilege, *, include_history: bool = False) -> dict[str, Any]:
    data = {
        "id": str(row.id),
        "rule_id": str(row.rule_id),
        "user_id": str(row.user_id),
        "privilege_code": row.privilege_code,
        "scope_key": row.scope_key,
        "scope": row.scope or {},
        "limitations": row.limitations or [],
        "status": row.status,
        "effective_from": row.effective_from,
        "expires_on": row.expires_on,
        "latest_decision_id": row.latest_decision_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_history:
        data["decisions"] = [_decision_dict(item) for item in list(row.decisions or [])]
    return data


def _rule_holder_counts(db: Session, *, amo_id: str, rule_ids: list[str]) -> dict[str, dict[str, int]]:
    counts = {rule_id: {"active_holders": 0, "live_holders": 0, "total_holders": 0} for rule_id in rule_ids}
    if not rule_ids:
        return counts
    rows = (
        db.query(QualityPrivilege.rule_id, QualityPrivilege.status)
        .filter(QualityPrivilege.amo_id == amo_id, QualityPrivilege.rule_id.in_(rule_ids))
        .all()
    )
    for rule_id, status_value in rows:
        key = str(rule_id)
        bucket = counts.setdefault(key, {"active_holders": 0, "live_holders": 0, "total_holders": 0})
        bucket["total_holders"] += 1
        if status_value == "ACTIVE":
            bucket["active_holders"] += 1
            bucket["live_holders"] += 1
        elif status_value in {"SUSPENDED", "DRAFT"}:
            bucket["live_holders"] += 1
    return counts


@router.get("/summary")
def people_summary(
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()
    active = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.status == "ACTIVE").count()
    expiring = db.query(QualityPrivilege).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.status == "ACTIVE",
        QualityPrivilege.expires_on.is_not(None),
        QualityPrivilege.expires_on >= today,
        QualityPrivilege.expires_on <= today + timedelta(days=60),
    ).count()
    suspended = db.query(QualityPrivilege).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.status == "SUSPENDED").count()
    conflicts = db.query(QualityIndependenceDeclaration).filter(
        QualityIndependenceDeclaration.amo_id == ctx.amo_id,
        QualityIndependenceDeclaration.declaration.in_(["CONFLICT", "REQUIRES_REVIEW"]),
    ).count()
    active_rows = (
        db.query(QualityPrivilege.rule_id, QualityPrivilegeRule.privilege_type, QualityPrivilegeRule.scope_schema)
        .join(QualityPrivilegeRule, QualityPrivilegeRule.id == QualityPrivilege.rule_id)
        .filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.status == "ACTIVE")
        .all()
    )
    lead_auditors = auditors = observers = inspectors = reviewers = 0
    for _rule_id, privilege_type, scope_schema in active_rows:
        supervised = bool((scope_schema or {}).get("supervised_development"))
        if privilege_type == "LEAD_AUDITOR":
            lead_auditors += 1
        elif privilege_type == "AUDITOR" and supervised:
            observers += 1
        elif privilege_type == "AUDITOR":
            auditors += 1
        elif privilege_type == "QUALITY_INSPECTOR":
            inspectors += 1
        elif privilege_type == "AUTHORIZATION_REVIEWER":
            reviewers += 1
    return {
        "active_privileges": active,
        "expiring_within_60_days": expiring,
        "suspended_privileges": suspended,
        "independence_exceptions": conflicts,
        "lead_auditors": lead_auditors,
        "auditors": auditors,
        "observers": observers,
        "inspectors": inspectors,
        "reviewers": reviewers,
    }


@router.get("/rules")
def list_rules(
    include_inactive: bool = False,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    # Every tenant receives the default Lead / Observer-Trainee / Auditor catalog.
    ensure_default_quality_privilege_rules(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    sync_default_quality_privilege_rule_competence(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    # Flush only — commit would clear transaction-local RLS (app.tenant_id) before the list query.
    db.flush()
    query = db.query(QualityPrivilegeRule).filter(QualityPrivilegeRule.amo_id == ctx.amo_id)
    if not include_inactive:
        query = query.filter(QualityPrivilegeRule.is_active.is_(True))
    rows = query.order_by(QualityPrivilegeRule.title.asc()).limit(250).all()
    holder_counts = _rule_holder_counts(db, amo_id=ctx.amo_id, rule_ids=[str(row.id) for row in rows])
    payload = {
        "items": [
            _rule_dict(
                row,
                active_holders=holder_counts.get(str(row.id), {}).get("active_holders", 0),
                live_holders=holder_counts.get(str(row.id), {}).get("live_holders", 0),
                total_holders=holder_counts.get(str(row.id), {}).get("total_holders", 0),
            )
            for row in rows
        ]
    }
    db.commit()
    return payload


@router.post("/rules/ensure-defaults", status_code=status.HTTP_200_OK)
def ensure_default_rules(
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Idempotently provision the default audit competence rule catalog."""
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = ensure_default_quality_privilege_rules(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    payload = {"items": [_rule_dict(row) for row in rows]}
    db.commit()
    return payload


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: PrivilegeRuleCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    code = payload.privilege_code.strip().upper()
    if db.query(QualityPrivilegeRule.id).filter(QualityPrivilegeRule.amo_id == ctx.amo_id, QualityPrivilegeRule.privilege_code == code).first():
        raise HTTPException(status_code=409, detail="A privilege rule with this code already exists.")
    row = QualityPrivilegeRule(
        amo_id=ctx.amo_id,
        privilege_code=code,
        title=payload.title.strip(),
        privilege_type=payload.privilege_type,
        description=payload.description,
        required_training_course_codes=sorted({value.strip().upper() for value in payload.required_training_course_codes if value.strip()}),
        independence_required=payload.independence_required,
        max_concurrent_assignments=payload.max_concurrent_assignments,
        scope_schema=payload.scope_schema,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rule_dict(row)


@router.patch("/rules/{rule_id}")
def update_rule(
    rule_id: str,
    payload: PrivilegeRuleUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _rule(db, amo_id=ctx.amo_id, rule_id=rule_id)
    updates = payload.model_dump(exclude_unset=True)
    if "title" in updates:
        row.title = str(updates["title"]).strip()
    if "description" in updates:
        row.description = updates["description"]
    if "required_training_course_codes" in updates:
        row.required_training_course_codes = sorted({
            value.strip().upper()
            for value in (updates["required_training_course_codes"] or [])
            if value.strip()
        })
    if "independence_required" in updates:
        row.independence_required = updates["independence_required"]
    if "max_concurrent_assignments" in updates:
        row.max_concurrent_assignments = updates["max_concurrent_assignments"]
    if "scope_schema" in updates:
        row.scope_schema = updates["scope_schema"] or {}
    if "is_active" in updates:
        row.is_active = updates["is_active"]
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    counts = _rule_holder_counts(db, amo_id=ctx.amo_id, rule_ids=[str(row.id)]).get(str(row.id), {})
    return _rule_dict(
        row,
        active_holders=counts.get("active_holders", 0),
        live_holders=counts.get("live_holders", 0),
        total_holders=counts.get("total_holders", 0),
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: str,
    purge_retired: bool = Query(default=True, description="Also permanently remove revoked/expired authorizations for this rule."),
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    """Delete a privilege rule that no longer has live holders."""
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _rule(db, amo_id=ctx.amo_id, rule_id=rule_id)
    live = (
        db.query(QualityPrivilege)
        .filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.rule_id == row.id,
            QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED", "DRAFT"]),
        )
        .count()
    )
    if live:
        raise HTTPException(
            status_code=409,
            detail=f"This rule still authorizes {live} person(s). Revoke or reassign them before deleting the rule.",
        )
    retired = (
        db.query(QualityPrivilege)
        .options(noload(QualityPrivilege.decisions))
        .filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.rule_id == row.id,
            QualityPrivilege.status.in_(["REVOKED", "EXPIRED"]),
        )
        .all()
    )
    if retired and not purge_retired:
        raise HTTPException(
            status_code=409,
            detail=f"This rule still has {len(retired)} revoked/expired authorization record(s). Purge them first or retry with purge_retired=true.",
        )
    for privilege in retired:
        db.query(QualityPrivilegeDecision).filter(
            QualityPrivilegeDecision.amo_id == ctx.amo_id,
            QualityPrivilegeDecision.privilege_id == privilege.id,
        ).delete(synchronize_session=False)
        db.delete(privilege)
    db.delete(row)
    db.commit()


@router.get("/{user_id}/audit-participation")
def person_audit_participation(
    user_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """Audits this person participated in as lead, observer, or assistant."""
    from amodb.apps.quality.audit_report_governance_models import QualityAuditReportRevision
    from amodb.apps.quality import models as qms_models

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    person = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id == user_id,
        account_models.User.is_system_account.is_(False),
    ).first()
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    audits = (
        db.query(qms_models.QMSAudit)
        .filter(
            qms_models.QMSAudit.amo_id == ctx.amo_id,
            qms_models.QMSAudit.deleted_at.is_(None),
            (
                (qms_models.QMSAudit.lead_auditor_user_id == user_id)
                | (qms_models.QMSAudit.observer_auditor_user_id == user_id)
                | (qms_models.QMSAudit.assistant_auditor_user_id == user_id)
            ),
        )
        .order_by(qms_models.QMSAudit.planned_start.desc().nullslast(), qms_models.QMSAudit.created_at.desc())
        .limit(100)
        .all()
    )
    audit_ids = [audit.id for audit in audits]
    issued_by_audit: dict[str, QualityAuditReportRevision] = {}
    if audit_ids:
        revisions = (
            db.query(QualityAuditReportRevision)
            .filter(
                QualityAuditReportRevision.amo_id == ctx.amo_id,
                QualityAuditReportRevision.audit_id.in_(audit_ids),
                QualityAuditReportRevision.status == "ISSUED",
            )
            .order_by(QualityAuditReportRevision.revision_no.desc())
            .all()
        )
        for revision in revisions:
            key = str(revision.audit_id)
            if key not in issued_by_audit:
                issued_by_audit[key] = revision

    items: list[dict[str, Any]] = []
    for audit in audits:
        roles: list[str] = []
        if audit.lead_auditor_user_id == user_id:
            roles.append("LEAD_AUDITOR")
        if audit.observer_auditor_user_id == user_id:
            roles.append("OBSERVER_AUDITOR")
        if audit.assistant_auditor_user_id == user_id:
            roles.append("ASSISTANT_AUDITOR")
        issued = issued_by_audit.get(str(audit.id))
        items.append({
            "audit_id": str(audit.id),
            "audit_ref": audit.audit_ref,
            "title": audit.title,
            "status": _enum_value(audit.status),
            "roles": roles,
            "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
            "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
            "actual_end": audit.actual_end.isoformat() if audit.actual_end else None,
            "has_issued_report": issued is not None,
            "issued_revision_id": str(issued.id) if issued else None,
            "issued_revision_no": issued.revision_no if issued else None,
            "issued_filename": issued.filename if issued else None,
            "issued_at": issued.issued_at.isoformat() if issued and issued.issued_at else None,
        })
    return {"items": items, "person_user_id": user_id}


@router.get("/{user_id}/audit-participation/{audit_id}/issued-report")
def download_person_audit_issued_report(
    user_id: str,
    audit_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
):
    """Download the issued report for an audit this person participated in."""
    from pathlib import Path
    import hashlib
    from fastapi.responses import FileResponse
    from amodb.apps.quality.audit_report_governance_models import QualityAuditReportRevision
    from amodb.apps.quality import models as qms_models

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = db.query(qms_models.QMSAudit).filter(
        qms_models.QMSAudit.amo_id == ctx.amo_id,
        qms_models.QMSAudit.id == audit_id,
        qms_models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit is None:
        raise HTTPException(404, "Audit not found.")
    participated = user_id in {
        audit.lead_auditor_user_id,
        audit.observer_auditor_user_id,
        audit.assistant_auditor_user_id,
    }
    if not participated:
        raise HTTPException(404, "This person did not participate in that audit.")
    revision = (
        db.query(QualityAuditReportRevision)
        .filter(
            QualityAuditReportRevision.amo_id == ctx.amo_id,
            QualityAuditReportRevision.audit_id == audit.id,
            QualityAuditReportRevision.status == "ISSUED",
        )
        .order_by(QualityAuditReportRevision.revision_no.desc())
        .first()
    )
    if revision is None:
        raise HTTPException(404, "No issued report is available for this audit.")
    path = Path(revision.file_ref)
    if not path.is_file():
        raise HTTPException(409, "Issued report file is missing from storage.")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != (revision.sha256 or "").lower():
        raise HTTPException(409, "Issued report failed integrity verification.")
    return FileResponse(
        path,
        media_type=revision.content_type or "application/pdf",
        filename=revision.filename or f"{audit.audit_ref}-report.pdf",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/privileges")
def list_privileges(
    user_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityPrivilege).options(selectinload(QualityPrivilege.decisions)).filter(QualityPrivilege.amo_id == ctx.amo_id)
    if user_id:
        query = query.filter(QualityPrivilege.user_id == user_id)
    if status_filter:
        query = query.filter(QualityPrivilege.status == status_filter.upper())
    rows = query.order_by(QualityPrivilege.updated_at.desc()).limit(500).all()
    users = db.query(account_models.User).filter(account_models.User.amo_id == ctx.amo_id, account_models.User.id.in_({row.user_id for row in rows})).all() if rows else []
    names = {str(user.id): user.full_name or f"{user.first_name or chr(32)} {user.last_name or chr(32)}".strip() or user.email or "Person unavailable" for user in users}
    return {"items": [{**_privilege_dict(row, include_history=True), "person_name": names.get(str(row.user_id), "Person unavailable")} for row in rows]}


@router.post("/privileges", status_code=status.HTTP_201_CREATED)
def create_privilege(
    payload: PrivilegeCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=payload.rule_id)
    _lock_person(db, ctx.amo_id, payload.user_id)
    scope_key = payload.scope_key.strip().upper() or "GLOBAL"
    existing = db.query(QualityPrivilege).options(noload(QualityPrivilege.decisions)).filter(
        QualityPrivilege.amo_id == ctx.amo_id,
        QualityPrivilege.user_id == payload.user_id,
        QualityPrivilege.privilege_code == rule.privilege_code,
        QualityPrivilege.scope_key == scope_key,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This person already has this privilege/scope record; use a governed decision or rank change.")
    # Auditor ranks are exclusive — reuse the live authorization instead of stacking Observer + Auditor.
    if rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}:
        rank_rule_ids = [
            item[0] for item in db.query(QualityPrivilegeRule.id).filter(
                QualityPrivilegeRule.amo_id == ctx.amo_id,
                QualityPrivilegeRule.privilege_type.in_(["AUDITOR", "LEAD_AUDITOR"]),
            ).all()
        ]
        live_rank = db.query(QualityPrivilege).options(noload(QualityPrivilege.decisions)).filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.user_id == payload.user_id,
            QualityPrivilege.scope_key == scope_key,
            QualityPrivilege.rule_id.in_(rank_rule_ids),
            QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED"]),
        ).with_for_update().first()
        if live_rank is not None:
            if live_rank.status != "ACTIVE":
                raise HTTPException(status_code=409, detail="Reinstate or revoke the suspended auditor rank before assigning a different rank.")
            if live_rank.rule_id == rule.id:
                raise HTTPException(status_code=409, detail="This person already holds this auditor rank.")
            _apply_rank_change(
                db, ctx, live_rank, rule,
                "Consolidated to a single auditor rank during authorization.",
            )
            db.commit()
            set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
            db.refresh(live_rank)
            return _privilege_dict(live_rank, include_history=True)
    row = QualityPrivilege(
        amo_id=ctx.amo_id,
        rule_id=rule.id,
        user_id=payload.user_id,
        privilege_code=rule.privilege_code,
        scope_key=scope_key,
        scope=payload.scope,
        limitations=payload.limitations,
        status="DRAFT",
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    db.refresh(row)
    return _privilege_dict(row)


@router.get("/authorization-candidates")
def list_authorization_candidates(
    rule_id: str = Query(..., min_length=1),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=500),
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """People eligible to appear in Authorize for a specific privilege rule.

    Filtering is relational to that rule's training configuration only:
    competence package ``codes`` with join AND (default) or an Advanced AND/OR
    expression; legacy ``currency_any_of`` keeps OR; or ``required_training_course_codes`` (AND).
    Candidates must have a Training
    record and/or a scheduled enrollment for the matched course(s). Rules with
    no training codes return the active workforce (unrestricted).
    """

    from sqlalchemy import String, cast, func, or_

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=rule_id)
    if not rule.is_active:
        raise HTTPException(status_code=422, detail="Select an active privilege rule.")

    match = user_ids_matching_rule_training(db, amo_id=ctx.amo_id, rule=rule)
    allowed_ids = match.get("user_ids")
    match_by_user = match.get("match_by_user") or {}

    qs = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if allowed_ids is not None:
        if not allowed_ids:
            return {
                "rule_id": str(rule.id),
                "privilege_code": rule.privilege_code,
                "title": rule.title,
                "match_mode": match.get("mode"),
                "training_codes": list(match.get("codes") or []),
                "items": [],
                "total": 0,
            }
        qs = qs.filter(account_models.User.id.in_(list(allowed_ids)))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        qs = qs.filter(
            or_(
                account_models.User.full_name.ilike(pattern),
                account_models.User.first_name.ilike(pattern),
                account_models.User.last_name.ilike(pattern),
                account_models.User.email.ilike(pattern),
                account_models.User.staff_code.ilike(pattern),
                cast(account_models.User.id, String).ilike(pattern),
            )
        )
    users = (
        qs.order_by(
            func.coalesce(account_models.User.full_name, ""),
            func.coalesce(account_models.User.first_name, ""),
            func.coalesce(account_models.User.last_name, ""),
            account_models.User.email,
        )
        .limit(limit)
        .all()
    )

    items: list[dict[str, Any]] = []
    for user in users:
        user_id = str(user.id)
        full_name = (
            str(getattr(user, "full_name", "") or "").strip()
            or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            or getattr(user, "email", None)
            or "Person unavailable"
        )
        role_value = getattr(user, "role", None)
        role_value = getattr(role_value, "value", role_value)
        footprint = match_by_user.get(user_id) or {}
        items.append({
            "id": user_id,
            "staff_code": getattr(user, "staff_code", None),
            "full_name": full_name,
            "email": getattr(user, "email", None),
            "role": str(role_value) if role_value else None,
            "department_id": getattr(user, "department_id", None),
            "match_reasons": list(footprint.get("reasons") or []),
            "matched_course_codes": list(footprint.get("course_codes") or []),
            "valid_until": footprint.get("valid_until"),
        })

    return {
        "rule_id": str(rule.id),
        "privilege_code": rule.privilege_code,
        "title": rule.title,
        "match_mode": match.get("mode"),
        "training_codes": list(match.get("codes") or []),
        "items": items,
        "total": len(items),
    }


@router.get("/eligibility")
def get_eligibility(
    user_id: str,
    privilege_code: str,
    as_of: date | None = None,
    context_type: ContextType | None = None,
    context_id: str | None = None,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rule = _rule(db, amo_id=ctx.amo_id, privilege_code=privilege_code.strip().upper())
    try:
        # Read path: never auto-suspend/write on pill loads. Assignment/decision
        # paths still apply currency auto-suspend when mutating.
        result = evaluate_eligibility(
            db,
            amo_id=ctx.amo_id,
            user_id=user_id,
            rule=rule,
            as_of=as_of or date.today(),
            context_type=context_type,
            context_id=context_id,
            require_active_privilege=True,
            actor_user_id=ctx.user_id,
            apply_auto_suspend=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Eligibility evaluation failed: {exc}") from exc
    return result


@router.post("/privileges/{privilege_id}/decisions", status_code=status.HTTP_201_CREATED)
def decide_privilege(
    privilege_id: str,
    payload: PrivilegeDecisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.training.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    identity = db.query(QualityPrivilege.user_id).filter(QualityPrivilege.amo_id == ctx.amo_id, QualityPrivilege.id == privilege_id).first()
    if identity is None:
        raise HTTPException(404, "Authorization not found.")
    _lock_person(db, ctx.amo_id, identity[0])
    # Lock the privilege row only. Do not eager-load relationships here: a joined
    # rule load produces LEFT OUTER JOIN … FOR UPDATE, which Postgres rejects.
    privilege = (
        db.query(QualityPrivilege)
        .options(noload(QualityPrivilege.rule), noload(QualityPrivilege.decisions))
        .filter(
            QualityPrivilege.amo_id == ctx.amo_id,
            QualityPrivilege.id == privilege_id,
        )
        .with_for_update()
        .first()
    )
    if not privilege:
        raise HTTPException(status_code=404, detail="Quality privilege not found.")
    rule = _rule(db, amo_id=ctx.amo_id, rule_id=str(privilege.rule_id))

    allowed_from = _PRIVILEGE_DECISION_ALLOWED_FROM[payload.decision_type]
    if privilege.status not in allowed_from:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Privilege decision is not valid from the current lifecycle state.",
                "current_status": privilege.status,
                "decision_type": payload.decision_type,
                "allowed_from": sorted(allowed_from),
            },
        )

    resulting_status = {
        "GRANT": "ACTIVE",
        "RENEW": "ACTIVE",
        "REINSTATE": "ACTIVE",
        "SUSPEND": "SUSPENDED",
        "REVOKE": "REVOKED",
        "EXPIRE": "EXPIRED",
        "REJECT": "REVOKED",
    }[payload.decision_type]
    activation_decision = payload.decision_type in {"GRANT", "RENEW", "REINSTATE"}
    if not activation_decision and (payload.effective_from is not None or payload.expires_on is not None):
        raise HTTPException(status_code=422, detail="Lifecycle-only privilege decisions must not alter effective dates.")
    effective_from = (
        payload.effective_from or privilege.effective_from or date.today()
        if activation_decision
        else privilege.effective_from
    )
    expires_on = (
        payload.expires_on if "expires_on" in payload.model_fields_set else privilege.expires_on
    )
    if expires_on and effective_from and expires_on < effective_from:
        raise HTTPException(status_code=422, detail="Privilege expiry cannot precede its effective date.")
    if activation_decision and expires_on and expires_on < date.today():
        raise HTTPException(status_code=422, detail="An active privilege cannot retain an expiry date in the past.")

    eligibility = evaluate_eligibility(
        db,
        amo_id=ctx.amo_id,
        user_id=str(privilege.user_id),
        rule=rule,
        as_of=effective_from or date.today(),
        require_active_privilege=False,
        actor_user_id=ctx.user_id,
    ) if activation_decision else {"lifecycle_only": True}
    if payload.decision_type in {"GRANT", "RENEW", "REINSTATE"}:
        grant_gates = dict(eligibility["hard_gates"])
        grant_gates.pop("active_privilege", None)
        # Independence is assignment-specific. A privilege may be granted without
        # declaring independence from an audit that does not yet exist.
        grant_gates.pop("independence", None)
        if not all(grant_gates.values()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Hard source-backed eligibility gates do not allow this privilege decision.", "eligibility": eligibility},
            )
        # Authorization cannot outlive governing Training course currency.
        expires_on = cap_privilege_expires_on(
            expires_on,
            eligibility.get("training") if isinstance(eligibility, dict) else None,
            as_of=effective_from or date.today(),
        )
        if expires_on and effective_from and expires_on < effective_from:
            raise HTTPException(status_code=422, detail="Privilege expiry cannot precede its effective date.")
        if expires_on and expires_on < date.today():
            raise HTTPException(status_code=422, detail="An active privilege cannot retain an expiry date in the past.")

    # Re-bind tenant GUC before the append-only insert. Transaction-local
    # set_config is cleared by any mid-request commit/rollback, and RLS WITH CHECK
    # on quality_privilege_decisions rejects the row as a bare 500 without it.
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    decision = QualityPrivilegeDecision(
        amo_id=ctx.amo_id,
        privilege_id=privilege.id,
        decision_type=payload.decision_type,
        resulting_status=resulting_status,
        rationale=payload.rationale.strip(),
        eligibility_snapshot=eligibility,
        source_references=payload.source_references,
        effective_from=effective_from,
        expires_on=expires_on,
        decided_by_user_id=ctx.user_id,
        decided_at=_utcnow(),
    )
    db.add(decision)
    db.flush()
    privilege.status = resulting_status
    if activation_decision and rule.privilege_type in {"AUDITOR", "LEAD_AUDITOR"}:
        _retire_other_ranks(db, ctx, privilege)
    if activation_decision:
        privilege.effective_from = effective_from
        privilege.expires_on = expires_on
    privilege.latest_decision_id = decision.id
    privilege.updated_by_user_id = ctx.user_id
    privilege.updated_at = _utcnow()
    db.commit()
    # Commit clears transaction-local tenant GUC; re-bind before post-commit reads.
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    db.refresh(privilege)
    db.refresh(decision)
    return {"privilege": _privilege_dict(privilege), "decision": _decision_dict(decision)}


def _independence_dict(row: QualityIndependenceDeclaration) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "context_type": row.context_type,
        "context_id": row.context_id,
        "declaration": row.declaration,
        "relationship_to_subject": row.relationship_to_subject,
        "rationale": row.rationale,
        "source_references": row.source_references,
        "declared_by_user_id": row.declared_by_user_id,
        "declared_at": row.declared_at,
    }


@router.get("/independence/policy")
def independence_policy(
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return get_independence_policy(db, amo_id=ctx.amo_id)


class IndependencePolicyUpdate(BaseModel):
    enforced: bool | None = None
    allow_impartiality_form: bool | None = None


@router.patch("/independence/policy")
def update_independence_policy(
    payload: IndependencePolicyUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    if not ctx.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only a platform superuser may deactivate or change independence enforcement for a tenant.",
        )
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    try:
        policy = set_independence_policy(
            db,
            amo_id=ctx.amo_id,
            enforced=payload.enforced,
            allow_impartiality_form=payload.allow_impartiality_form,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return policy


@router.get("/independence/assessment")
def assess_independence(
    user_id: str = Query(..., min_length=1),
    context_type: ContextType | None = None,
    context_id: str | None = None,
    assignment_scope_key: str | None = None,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _person(db, amo_id=ctx.amo_id, user_id=user_id)
    try:
        return evaluate_independence_conflicts(
            db,
            amo_id=ctx.amo_id,
            user_id=user_id,
            context_type=context_type,
            context_id=context_id,
            assignment_scope_key=assignment_scope_key,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Independence assessment failed: {exc}",
        ) from exc


@router.get("/independence")
def list_independence(
    user_id: str | None = None,
    context_type: ContextType | None = None,
    context_id: str | None = None,
    ctx: TenantContext = Depends(require_quality_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityIndependenceDeclaration).filter(QualityIndependenceDeclaration.amo_id == ctx.amo_id)
    if user_id:
        query = query.filter(QualityIndependenceDeclaration.user_id == user_id)
    if context_type:
        query = query.filter(QualityIndependenceDeclaration.context_type == context_type)
    if context_id:
        query = query.filter(QualityIndependenceDeclaration.context_id == context_id)
    rows = query.order_by(QualityIndependenceDeclaration.declared_at.desc()).limit(250).all()
    return {"items": [_independence_dict(row) for row in rows]}


@router.post("/independence", status_code=status.HTTP_201_CREATED)
def declare_independence(
    payload: IndependenceCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Record an Auditor Impartiality Form for residual small-organisation cases.

    This is a remediation artifact — not a free-form independence toggle.
    Hard conflicts (own work / own department) cannot be cleared by this form.
    """

    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _person(db, amo_id=ctx.amo_id, user_id=payload.user_id)
    policy = get_independence_policy(db, amo_id=ctx.amo_id)
    if not policy.get("allow_impartiality_form", True):
        raise HTTPException(status_code=403, detail="Auditor Impartiality Forms are disabled for this tenant.")
    assessment = evaluate_independence_conflicts(
        db,
        amo_id=ctx.amo_id,
        user_id=payload.user_id,
        context_type=payload.context_type,
        context_id=payload.context_id,
    )
    hard_codes = {item.get("code") for item in assessment.get("conflicts") or []}
    if "OWN_WORK" in hard_codes or "OWN_DEPARTMENT" in hard_codes:
        raise HTTPException(
            status_code=422,
            detail="An impartiality form cannot clear a hard independence conflict. Select another auditor or outsource externally.",
        )
    existing = db.query(QualityIndependenceDeclaration.id).filter(
        QualityIndependenceDeclaration.amo_id == ctx.amo_id,
        QualityIndependenceDeclaration.user_id == payload.user_id,
        QualityIndependenceDeclaration.context_type == payload.context_type,
        QualityIndependenceDeclaration.context_id == payload.context_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="An impartiality form already exists for this person and context. Preserve it and create a new governed assignment/context if circumstances change.",
        )
    if payload.declaration == "CONFLICT" and not (payload.relationship_to_subject or "").strip():
        raise HTTPException(status_code=422, detail="A conflict declaration must describe the relationship to the audit subject.")
    row = QualityIndependenceDeclaration(
        amo_id=ctx.amo_id,
        user_id=payload.user_id,
        context_type=payload.context_type,
        context_id=payload.context_id,
        declaration=payload.declaration,
        relationship_to_subject=payload.relationship_to_subject,
        rationale=payload.rationale.strip(),
        source_references=payload.source_references or [{"type": "AUDITOR_IMPARTIALITY_FORM"}],
        declared_by_user_id=ctx.user_id,
        declared_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _independence_dict(row)
