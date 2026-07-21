# backend/amodb/apps/quality/router.py
from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta
import calendar
import json
from pathlib import Path
import hashlib
import re
import shutil
import io
import zipfile
from threading import Lock
from typing import Optional, List, Iterator, Any
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Request, Response, Header, Form, Body
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import func, or_, inspect, cast, String, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from amodb.entitlements import require_module
from amodb.security import get_current_actor_id, get_current_active_user
from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services
from amodb.apps.notifications import service as notification_service
from amodb.apps.exports import build_evidence_pack
from amodb.apps.tasks import services as task_services
from amodb.database import get_db, get_read_db

from . import models
from . import transitions as car_transitions
from .schemas import (
    CARActionCreate,
    CARActionOut,
    CARAssigneeOut,
    CARCreate,
    CARInviteOut,
    CARInviteUpdate,
    CARAttachmentOut,
    CARAttachmentUpdate,
    CAROut,
    CARRegisterResponse,
    CARUpdate,
    CARReviewUpdate,
    CARResponseOut,
    AuditorStatsOut,
    QMSNotificationOut,
    QMSNotificationSummaryOut,
    QMSDashboardOut,
    QMSCockpitSnapshotOut,
    QMSManpowerAvailabilityOut,
    QMSManpowerAvailabilityUpsert,
    QMSDocumentCreate, QMSDocumentUpdate, QMSDocumentOut,
    QMSDocumentRevisionCreate, QMSDocumentRevisionOut, QMSPublishRevision,
    QMSDistributionCreate, QMSDistributionOut,
    QMSChangeRequestCreate, QMSChangeRequestUpdate, QMSChangeRequestOut,
    QMSAuditCreate, QMSAuditUpdate, QMSAuditOut, QMSAuditScopeCreate, QMSAuditScopeUpdate, QMSAuditScopeOut, QMSAuditRegisterResponse, QMSAuditRegisterRowOut, QMSAuditWorkspaceOut, QMSAuditWorkflowSummaryOut, QMSAuditWorkflowStageOut, QMSAuditNoticeDispatchOut,
    QMSFindingCreate, QMSFindingOut, QMSFindingAttachmentOut, QMSFindingVerify, QMSFindingAcknowledge, QMSFindingUpdate, QMSFindingReviewFlag,
    QMSAuditScheduleCreate, QMSAuditScheduleUpdate, QMSAuditScheduleOut,
    QMSCAPUpsert, QMSCAPOut,
    QMSUploadRevisionOut, QMSPhysicalCopyRequest, QMSPhysicalCopyOut,
    QMSCustodyActionCreate, QMSCustodyLogOut, QMSPhysicalVerifyOut,
    QMSIssueRevisionRequest, QMSDamageReportRequest, QMSDamageReportOut,
    QMSPersonOptionOut,
    QualityWorkflowSettingsOut, QualityWorkflowSettingsUpdate,
    QualityDocumentRequestCreate, QualityDocumentRequestUpdate, QualityDocumentRequestOut,
    QualityChecklistItemCreate, QualityChecklistItemUpdate, QualityChecklistItemOut,
    QualityFieldworkComplete, QualityPostBriefCreate, QualityPostBriefOut,
    QualityReportTrackerOut, QualityCARExtensionRequestCreate, QualityCARExtensionReview,
    QualityCARExtensionRequestOut, QualityReminderMilestoneOut, QualityArchivePackageOut,
    QualityAuditMetricsOut,
)
from .enums import CARStatus, QMSDomain, QMSAuditStatus, QMSPhysicalCopyStatus, QMSCustodyAction, QMSRevisionLifecycleStatus, FindingLevel, QMSFindingType
from .schema_compat import ensure_qms_audit_reference_schema, ensure_qms_audit_scope_schema
from .storage_replication import replicate_file
from .service import (
    add_car_action,
    build_car_invite_link,
    compute_target_close_date,
    create_car,
    generate_car_form_pdf,
    get_dashboard,
    get_cockpit_snapshot,
    normalize_finding_level,
    schedule_next_reminder,
)
from ..workflow import apply_transition, TransitionError

_QMS_SCHEMA_COMPAT_LOCK = Lock()
_QMS_SCHEMA_COMPAT_READY = False


def _ensure_qms_runtime_schema_compat(db: Session = Depends(get_db)) -> None:
    """
    Runtime guard for environments where the CAR responses migration was missed.

    Some deployments have the ORM expecting ``quality_car_responses`` while the
    live database is missing the table, which causes selectin relationship loads
    to fail on otherwise routine CAR reads. Create the table on first access so
    the quality module remains available until migrations are fully reconciled.
    """
    global _QMS_SCHEMA_COMPAT_READY
    if _QMS_SCHEMA_COMPAT_READY:
        return

    with _QMS_SCHEMA_COMPAT_LOCK:
        if _QMS_SCHEMA_COMPAT_READY:
            return
        bind = db.get_bind()
        inspector = inspect(bind)
        if inspector.has_table("quality_cars") and not inspector.has_table("quality_car_responses"):
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS quality_car_responses (
                        id UUID NOT NULL,
                        car_id UUID NOT NULL,
                        containment_action TEXT,
                        root_cause TEXT,
                        corrective_action TEXT,
                        preventive_action TEXT,
                        evidence_ref VARCHAR(512),
                        submitted_by_name VARCHAR(255),
                        submitted_by_email VARCHAR(255),
                        submitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        status VARCHAR(32) NOT NULL
                    )
                    """
                )
            )
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_id_runtime ON quality_car_responses (id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_car_runtime ON quality_car_responses (car_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_submitted_runtime ON quality_car_responses (submitted_at)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_status_runtime ON quality_car_responses (status)"))

        if inspector.has_table("quality_cars") and not inspector.has_table("quality_car_attachments"):
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS quality_car_attachments (
                        id UUID NOT NULL,
                        car_id UUID NOT NULL,
                        filename VARCHAR(255) NOT NULL,
                        description VARCHAR(500),
                        file_ref VARCHAR(512) NOT NULL,
                        content_type VARCHAR(128),
                        size_bytes INTEGER,
                        sha256 VARCHAR(64),
                        uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                    """
                )
            )
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_id_runtime ON quality_car_attachments (id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_car_runtime ON quality_car_attachments (car_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_sha_runtime ON quality_car_attachments (sha256)"))

        # Final Quality workflow tables were introduced after the QMS -> Quality
        # merge.  Some live/dev databases may have the application code before the
        # Alembic head has been applied, which must not make existing scheduled
        # audits unreadable.  Create only missing workflow tables here, matching
        # the ORM definitions where it is safe to do so.  The two finding/CAPA
        # tables are handled separately with constraint-free runtime DDL because
        # some PostgreSQL databases already contain orphaned/global constraint
        # names such as pk_qms_corrective_actions.  SQLAlchemy table.create() then
        # raises DuplicateTable even though the table itself is absent.
        workflow_tables = (
            models.QualityTenantWorkflowSettings.__table__,
            models.QualityAuditDocumentRequest.__table__,
            models.QualityAuditChecklistItem.__table__,
            models.QualityAuditPostBrief.__table__,
            models.QualityAuditReportTracker.__table__,
            models.QualityCARExtensionRequest.__table__,
            models.QualityReminderMilestone.__table__,
            models.QualityArchivePackage.__table__,
        )
        for table in workflow_tables:
            if not inspector.has_table(table.name):
                table.create(bind=bind, checkfirst=True)

        inspector = inspect(bind)

        if not inspector.has_table("qms_corrective_actions"):
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS qms_corrective_actions (
                        id UUID NOT NULL,
                        amo_id VARCHAR(36) NOT NULL,
                        finding_id UUID NOT NULL,
                        root_cause TEXT,
                        containment_action TEXT,
                        corrective_action TEXT,
                        preventive_action TEXT,
                        responsible_user_id VARCHAR(36),
                        due_date DATE,
                        evidence_ref VARCHAR(512),
                        verified_at TIMESTAMP WITH TIME ZONE,
                        verified_by_user_id VARCHAR(36),
                        status VARCHAR(11) NOT NULL,
                        created_by_user_id VARCHAR(36),
                        updated_by_user_id VARCHAR(36),
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                    """
                )
            )
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_corrective_actions_id_runtime ON qms_corrective_actions (id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_corrective_actions_finding_runtime ON qms_corrective_actions (finding_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_corrective_actions_amo_runtime ON qms_corrective_actions (amo_id)"))

        if not inspector.has_table("qms_finding_attachments"):
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS qms_finding_attachments (
                        id UUID NOT NULL,
                        finding_id UUID NOT NULL,
                        filename VARCHAR(255) NOT NULL,
                        description VARCHAR(500),
                        file_ref VARCHAR(512) NOT NULL,
                        content_type VARCHAR(128),
                        size_bytes INTEGER,
                        sha256 VARCHAR(64),
                        uploaded_by_user_id VARCHAR(36),
                        uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                    """
                )
            )
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_id_runtime ON qms_finding_attachments (id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_finding_runtime ON qms_finding_attachments (finding_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_uploaded_runtime ON qms_finding_attachments (uploaded_at)"))

        inspector = inspect(bind)

        def _has_column(table_name: str, column_name: str) -> bool:
            return column_name in {column["name"] for column in inspector.get_columns(table_name)}

        def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
            if not inspector.has_table(table_name):
                return
            if _has_column(table_name, column_name):
                return
            db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))

        _add_column_if_missing("qms_audit_schedules", "amo_id", "VARCHAR(36)")
        _add_column_if_missing("qms_audit_schedules", "external_auditees_json", "TEXT")
        _add_column_if_missing("qms_audit_schedules", "notify_auditors", "BOOLEAN DEFAULT TRUE")
        _add_column_if_missing("qms_audit_schedules", "notify_auditees", "BOOLEAN DEFAULT TRUE")
        _add_column_if_missing("qms_audit_schedules", "reminder_interval_days", "INTEGER DEFAULT 7")
        _add_column_if_missing("qms_audits", "external_auditees_json", "TEXT")
        _add_column_if_missing("qms_audits", "notify_auditors", "BOOLEAN DEFAULT TRUE")
        _add_column_if_missing("qms_audits", "notify_auditees", "BOOLEAN DEFAULT TRUE")
        _add_column_if_missing("qms_audits", "reminder_interval_days", "INTEGER DEFAULT 7")
        _add_column_if_missing("qms_finding_attachments", "id", "UUID")
        _add_column_if_missing("qms_finding_attachments", "finding_id", "UUID")
        _add_column_if_missing("qms_finding_attachments", "filename", "VARCHAR(255) DEFAULT 'finding-evidence'")
        _add_column_if_missing("qms_finding_attachments", "description", "VARCHAR(500)")
        _add_column_if_missing("qms_finding_attachments", "file_ref", "VARCHAR(512) DEFAULT ''")
        _add_column_if_missing("qms_finding_attachments", "content_type", "VARCHAR(128)")
        _add_column_if_missing("qms_finding_attachments", "size_bytes", "INTEGER")
        _add_column_if_missing("qms_finding_attachments", "sha256", "VARCHAR(64)")
        _add_column_if_missing("qms_finding_attachments", "uploaded_by_user_id", "VARCHAR(36)")
        _add_column_if_missing("qms_finding_attachments", "uploaded_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
        if inspector.has_table("qms_finding_attachments"):
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_id_runtime ON qms_finding_attachments (id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_finding_runtime ON qms_finding_attachments (finding_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_uploaded_runtime ON qms_finding_attachments (uploaded_at)"))

        _add_column_if_missing("quality_car_attachments", "id", "UUID")
        _add_column_if_missing("quality_car_attachments", "car_id", "UUID")
        _add_column_if_missing("quality_car_attachments", "filename", "VARCHAR(255) DEFAULT 'evidence-file'")
        _add_column_if_missing("quality_car_attachments", "description", "VARCHAR(500)")
        _add_column_if_missing("quality_car_attachments", "file_ref", "VARCHAR(512) DEFAULT ''")
        _add_column_if_missing("quality_car_attachments", "content_type", "VARCHAR(128)")
        _add_column_if_missing("quality_car_attachments", "size_bytes", "INTEGER")
        _add_column_if_missing("quality_car_attachments", "sha256", "VARCHAR(64)")
        _add_column_if_missing("quality_car_attachments", "uploaded_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
        _add_column_if_missing("quality_car_responses", "id", "UUID")
        _add_column_if_missing("quality_car_responses", "car_id", "UUID")
        _add_column_if_missing("quality_car_responses", "containment_action", "TEXT")
        _add_column_if_missing("quality_car_responses", "root_cause", "TEXT")
        _add_column_if_missing("quality_car_responses", "corrective_action", "TEXT")
        _add_column_if_missing("quality_car_responses", "preventive_action", "TEXT")
        _add_column_if_missing("quality_car_responses", "evidence_ref", "VARCHAR(512)")
        _add_column_if_missing("quality_car_responses", "submitted_by_name", "VARCHAR(255)")
        _add_column_if_missing("quality_car_responses", "submitted_by_email", "VARCHAR(255)")
        _add_column_if_missing("quality_car_responses", "submitted_at", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")
        _add_column_if_missing("quality_car_responses", "status", "VARCHAR(32) DEFAULT 'SUBMITTED'")
        if inspector.has_table("quality_car_responses"):
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_id_runtime ON quality_car_responses (id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_car_runtime ON quality_car_responses (car_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_submitted_runtime ON quality_car_responses (submitted_at)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_status_runtime ON quality_car_responses (status)"))

        inspector = inspect(bind)

        if inspector.has_table("qms_audit_schedules") and _has_column("qms_audit_schedules", "amo_id"):
            db.execute(
                text(
                    """
                    UPDATE qms_audit_schedules s
                    SET amo_id = u.amo_id
                    FROM users u
                    WHERE s.amo_id IS NULL
                      AND s.created_by_user_id IS NOT NULL
                      AND u.id = s.created_by_user_id
                      AND u.amo_id IS NOT NULL
                    """
                )
            )

        db.commit()
        if inspector.has_table("qms_notifications"):
            existing_notification_columns = {col["name"] for col in inspector.get_columns("qms_notifications")}
            for column_name, column_type in {
                "action_url": "VARCHAR(1024)",
                "action_label": "VARCHAR(80)",
                "entity_type": "VARCHAR(64)",
                "entity_id": "VARCHAR(64)",
            }.items():
                if column_name not in existing_notification_columns:
                    db.execute(text(f"ALTER TABLE qms_notifications ADD COLUMN {column_name} {column_type}"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_notifications_entity_runtime ON qms_notifications (entity_type, entity_id)"))

        _QMS_SCHEMA_COMPAT_READY = True


router = APIRouter(
    prefix="/quality",
    tags=["Quality / QMS"],
    dependencies=[Depends(require_module("quality")), Depends(_ensure_qms_runtime_schema_compat)],
)

public_router = APIRouter(
    prefix="/quality",
    tags=["Quality / Public CAR"],
    dependencies=[Depends(_ensure_qms_runtime_schema_compat)],
)

CAR_ATTACHMENT_DIR = Path(__file__).resolve().parents[2] / "generated" / "quality" / "car_attachments"
CAR_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
MAX_CAR_ATTACHMENT_BYTES = 100 * 1024 * 1024
CAR_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/heic",
    "image/heif",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "text/plain",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
}
CAR_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".heic",
    ".heif",
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".txt",
    ".csv",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}

FINDING_ATTACHMENT_DIR = Path(__file__).resolve().parents[2] / "generated" / "quality" / "finding_attachments"
FINDING_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
MAX_FINDING_ATTACHMENT_BYTES = 15 * 1024 * 1024
FINDING_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
}
FINDING_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv", ".doc", ".docx", ".xls", ".xlsx"}

AUDIT_CHECKLIST_DIR = Path(__file__).resolve().parents[2] / "generated" / "quality" / "audit_checklists"
AUDIT_CHECKLIST_DIR.mkdir(parents=True, exist_ok=True)
MAX_AUDIT_CHECKLIST_BYTES = 15 * 1024 * 1024
AUDIT_CHECKLIST_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
AUDIT_CHECKLIST_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

AUDIT_REPORT_DIR = Path(__file__).resolve().parents[2] / "generated" / "quality" / "audit_reports"
AUDIT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
MAX_AUDIT_REPORT_BYTES = 25 * 1024 * 1024

def _audit_download_filename(audit: models.QMSAudit, artifact: str, file_path: Path) -> str:
    """Return a safe download name for audit files.

    Audit references such as QAR/SAF/28/002 contain slashes, which are display
    text but unsafe in Content-Disposition filenames. A missing helper here
    makes checklist/report preview fail with a backend 500.
    """
    raw_ref = audit.audit_ref or audit.title or str(audit.id)
    safe_ref = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw_ref)).strip("-._") or "audit"
    safe_artifact = re.sub(r"[^A-Za-z0-9._-]+", "-", artifact).strip("-._") or "file"
    extension = file_path.suffix if file_path.suffix else ""
    return f"{safe_ref}-{safe_artifact}{extension}"


def _audit_file_media_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".doc":
        return "application/msword"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "application/octet-stream"


def _audit_metadata(request: Request) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "module": "quality",
    }


def _date_to_datetime(value: Optional[date]) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _derive_audit_unit_code(db: Session, amo_id: Optional[str]) -> str:
    if not amo_id:
        return "MO"
    amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    raw = (amo.amo_code if amo else "") or (amo.icao_code if amo else "") or "MO"
    cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if len(cleaned) <= 8:
        return cleaned or "MO"
    compact = "".join(part[:3] for part in re.split(r"[^A-Z0-9]+", raw.upper()) if part)
    compact_clean = re.sub(r"[^A-Z0-9]", "", compact)
    return (compact_clean[:8] or cleaned[:8] or "MO")




def _normalize_scope_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return cleaned[:16] or None


def _scope_default_code_for_kind(kind: models.QMSAuditKind) -> str:
    if kind == models.QMSAuditKind.THIRD_PARTY:
        return "REG"
    if kind == models.QMSAuditKind.EXTERNAL:
        return "SC"
    return "MO"


def _require_scope_admin(current_user: account_models.User) -> None:
    if not _is_quality_admin(current_user):
        raise HTTPException(status_code=403, detail="Only AMO Admins or Quality Managers can manage audit scopes")


def _validate_one_calendar_year(*, start: Optional[date], end: Optional[date], duration_days: Optional[int] = None) -> None:
    if start and duration_days is not None and duration_days > 0:
        computed_end = start + timedelta(days=max(duration_days, 1) - 1)
        if computed_end.year != start.year:
            raise HTTPException(status_code=400, detail="Audit schedule must stay within one calendar year. Split audits that cross 31 December into separate schedules.")
    if start and end and start.year != end.year:
        raise HTTPException(status_code=400, detail="Audit start and end dates must be in the same calendar year as the system-generated reference.")
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="Audit end date cannot be before the start date.")


def _resolve_audit_scope(
    db: Session,
    *,
    amo_id: Optional[str],
    audit_scope_id: Optional[UUID] = None,
    audit_scope_code: Optional[str] = None,
    kind: Optional[models.QMSAuditKind] = None,
) -> models.QMSAuditScope:
    ensure_qms_audit_scope_schema(db)
    if not amo_id:
        raise HTTPException(status_code=400, detail="AMO scope is required to resolve audit scope")
    query = db.query(models.QMSAuditScope).filter(models.QMSAuditScope.amo_id == amo_id)
    if audit_scope_id:
        scope = query.filter(models.QMSAuditScope.id == audit_scope_id).first()
    else:
        code = _normalize_scope_code(audit_scope_code) or _scope_default_code_for_kind(kind or models.QMSAuditKind.INTERNAL)
        scope = query.filter(models.QMSAuditScope.code == code).first()
    if not scope:
        raise HTTPException(status_code=404, detail="Audit scope not found for this tenant")
    if not scope.is_active:
        raise HTTPException(status_code=400, detail=f"Audit scope {scope.code} is inactive")
    return scope


def _external_audit_is_editable(kind: models.QMSAuditKind) -> bool:
    return kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY}


def _audit_reference_matches_schedule(audit: models.QMSAudit) -> bool:
    if not audit.planned_start or not audit.audit_ref:
        return True
    expected_year = audit.planned_start.year % 100
    expected_scope = _normalize_scope_code(audit.audit_scope_code or audit.unit_code) or audit.unit_code
    match = re.match(r"^QAR/([A-Z0-9]+)/([0-9]{2})/[0-9]{3,}$", audit.audit_ref.strip().upper())
    if not match:
        return False
    return match.group(1) == expected_scope and int(match.group(2)) == expected_year

def _current_amo_id(current_user: account_models.User) -> Optional[str]:
    return getattr(current_user, "effective_amo_id", None) or current_user.amo_id




def _schedule_query_for_amo(db: Session, amo_id: Optional[str]):
    query = db.query(models.QMSAuditSchedule)
    if amo_id:
        query = query.filter(models.QMSAuditSchedule.amo_id == amo_id)
    return query


def _car_query_for_amo(db: Session, amo_id: Optional[str]):
    query = db.query(models.CorrectiveActionRequest)
    if amo_id:
        query = query.join(models.QMSAuditFinding, models.QMSAuditFinding.id == models.CorrectiveActionRequest.finding_id).join(models.QMSAudit, models.QMSAudit.id == models.QMSAuditFinding.audit_id).filter(models.QMSAudit.amo_id == amo_id)
    return query


def _get_schedule_for_amo(db: Session, *, amo_id: Optional[str], schedule_id: UUID) -> models.QMSAuditSchedule:
    schedule = _schedule_query_for_amo(db, amo_id).filter(models.QMSAuditSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    return schedule


def _get_car_for_amo(db: Session, *, amo_id: Optional[str], car_id: UUID) -> models.CorrectiveActionRequest:
    car = _car_query_for_amo(db, amo_id).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    return car

def _get_audit_for_amo(db: Session, *, amo_id: Optional[str], audit_id: UUID) -> models.QMSAudit:
    ensure_qms_audit_reference_schema(db)
    audit = (
        db.query(models.QMSAudit)
        .filter(
            models.QMSAudit.id == audit_id,
            models.QMSAudit.amo_id == amo_id,
        )
        .first()
    )
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


def _get_finding_for_amo(db: Session, *, amo_id: Optional[str], finding_id: UUID) -> models.QMSAuditFinding:
    ensure_qms_audit_reference_schema(db)
    finding = (
        db.query(models.QMSAuditFinding)
        .join(models.QMSAudit, models.QMSAudit.id == models.QMSAuditFinding.audit_id)
        .filter(
            models.QMSAuditFinding.id == finding_id,
            models.QMSAudit.amo_id == amo_id,
        )
        .first()
    )
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


def _get_finding_and_audit_for_amo(
    db: Session,
    *,
    current_user: account_models.User,
    finding_id: UUID,
    audit_id: Optional[UUID] = None,
) -> tuple[models.QMSAuditFinding, models.QMSAudit]:
    amo_id = _current_amo_id(current_user)
    ensure_qms_audit_reference_schema(db)
    if audit_id is not None:
        audit = _get_audit_for_amo(db, amo_id=amo_id, audit_id=audit_id)
        finding = (
            db.query(models.QMSAuditFinding)
            .filter(
                models.QMSAuditFinding.id == finding_id,
                models.QMSAuditFinding.audit_id == audit.id,
            )
            .first()
        )
        if not finding:
            raise HTTPException(status_code=404, detail="Finding not found for this audit")
        return finding, audit

    finding = _get_finding_for_amo(db, amo_id=amo_id, finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=amo_id, audit_id=finding.audit_id)
    return finding, audit


def _generate_audit_reference(
    db: Session,
    *,
    amo_id: Optional[str],
    target_date: Optional[date],
    audit_scope_code: Optional[str] = None,
    reference_family: str = "QAR",
) -> tuple[str, str, int, int]:
    ensure_qms_audit_reference_schema(db)
    ensure_qms_audit_scope_schema(db)
    if not amo_id:
        raise HTTPException(status_code=400, detail="AMO scope is required to generate audit references")

    unit_code = _normalize_scope_code(audit_scope_code) or "MO"
    ref_year = (target_date or date.today()).year % 100
    for _ in range(5):
        counter = (
            db.query(models.QMSAuditReferenceCounter)
            .filter(
                models.QMSAuditReferenceCounter.amo_id == amo_id,
                models.QMSAuditReferenceCounter.reference_family == reference_family,
                models.QMSAuditReferenceCounter.unit_code == unit_code,
                models.QMSAuditReferenceCounter.ref_year == ref_year,
            )
            .with_for_update()
            .first()
        )
        if counter:
            counter.last_value += 1
            ref_sequence = counter.last_value
            audit_ref = f"{reference_family}/{unit_code}/{ref_year:02d}/{ref_sequence:03d}"
            return audit_ref, unit_code, ref_year, ref_sequence

        try:
            with db.begin_nested():
                db.add(
                    models.QMSAuditReferenceCounter(
                        amo_id=amo_id,
                        reference_family=reference_family,
                        unit_code=unit_code,
                        ref_year=ref_year,
                        last_value=0,
                    )
                )
                db.flush()
        except IntegrityError:
            continue

    raise HTTPException(status_code=409, detail="Unable to reserve an audit reference. Please retry.")


def _advance_schedule_date(schedule: models.QMSAuditSchedule, base_date: date) -> date:
    def _add_months(months: int) -> date:
        year_offset, month_index = divmod(base_date.month - 1 + months, 12)
        year = base_date.year + year_offset
        month = month_index + 1
        day = min(base_date.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    if schedule.frequency == models.QMSAuditScheduleFrequency.ONE_TIME:
        return base_date
    if schedule.frequency == models.QMSAuditScheduleFrequency.MONTHLY:
        return _add_months(1)
    if schedule.frequency == models.QMSAuditScheduleFrequency.QUARTERLY:
        return _add_months(3)
    if schedule.frequency == models.QMSAuditScheduleFrequency.BI_ANNUAL:
        return _add_months(6)
    if schedule.frequency == models.QMSAuditScheduleFrequency.ANNUAL:
        year = base_date.year + 1
        day = min(base_date.day, calendar.monthrange(year, base_date.month)[1])
        return date(year, base_date.month, day)
    return base_date


def _serialize_attachment(invite_token: str, attachment: models.CARAttachment) -> CARAttachmentOut:
    return CARAttachmentOut(
        id=attachment.id,
        car_id=attachment.car_id,
        filename=attachment.filename,
        description=getattr(attachment, "description", None),
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_at=attachment.uploaded_at,
        download_url=f"/quality/cars/invite/{invite_token}/attachments/{attachment.id}/download",
    )


def _serialize_finding_attachment(attachment: models.QMSFindingAttachment) -> QMSFindingAttachmentOut:
    return QMSFindingAttachmentOut(
        id=attachment.id,
        finding_id=attachment.finding_id,
        filename=attachment.filename,
        description=getattr(attachment, "description", None),
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_by_user_id=attachment.uploaded_by_user_id,
        uploaded_at=attachment.uploaded_at,
        download_url=f"/quality/findings/{attachment.finding_id}/attachments/{attachment.id}/download",
    )


def _serialize_finding(finding: models.QMSAuditFinding) -> QMSFindingOut:
    return QMSFindingOut(
        id=finding.id,
        audit_id=finding.audit_id,
        finding_ref=finding.finding_ref,
        finding_type=finding.finding_type,
        severity=finding.severity,
        level=finding.level,
        requirement_ref=finding.requirement_ref,
        description=finding.description,
        objective_evidence=finding.objective_evidence,
        safety_sensitive=finding.safety_sensitive,
        target_close_date=finding.target_close_date,
        closed_at=finding.closed_at,
        verified_at=finding.verified_at,
        verified_by_user_id=finding.verified_by_user_id,
        acknowledged_at=finding.acknowledged_at,
        acknowledged_by_user_id=finding.acknowledged_by_user_id,
        acknowledged_by_name=finding.acknowledged_by_name,
        acknowledged_by_email=finding.acknowledged_by_email,
        created_by_user_id=finding.created_by_user_id,
        created_at=finding.created_at,
    )


def _sanitize_attachment_filename(value: str) -> str:
    base = Path(value or "attachment.bin").name
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    if not clean:
        clean = "attachment.bin"
    return clean[:120]


def _sanitize_checklist_filename(value: str | None) -> str:
    base = Path(value or "checklist").name
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._")
    if not clean:
        clean = "checklist"
    return clean[:160]


def _normalized_upload_mime(file: UploadFile) -> str:
    return (file.content_type or "").split(";", 1)[0].strip().lower()


def _store_car_attachment(car_id: UUID, file: UploadFile) -> tuple[Path, str, str, int]:
    original_name = _sanitize_attachment_filename(file.filename or "attachment.bin")
    ext = Path(original_name).suffix.lower()
    mime = _normalized_upload_mime(file)
    if ext not in CAR_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Attachment extension is not allowed.")
    if mime and not mime.startswith("image/") and not mime.startswith("video/") and mime not in CAR_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Attachment MIME type is not allowed.")

    unique_name = f"{uuid.uuid4().hex}{ext}"
    target_dir = CAR_ATTACHMENT_DIR / str(car_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / unique_name

    digest = hashlib.sha256()
    total = 0
    with target_path.open("wb") as handle:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CAR_ATTACHMENT_BYTES:
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Attachment exceeds the 100MB limit.")
            digest.update(chunk)
            handle.write(chunk)

    if total <= 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Attachment is empty.")

    return target_path, original_name, digest.hexdigest(), total


def _store_finding_attachment(finding_id: UUID, file: UploadFile) -> tuple[Path, str, str, int]:
    original_name = _sanitize_attachment_filename(file.filename or "evidence.bin")
    ext = Path(original_name).suffix.lower()
    mime = _normalized_upload_mime(file)
    if ext not in FINDING_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Finding evidence extension is not allowed.")
    if mime and mime not in FINDING_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Finding evidence MIME type is not allowed.")

    unique_name = f"{uuid.uuid4().hex}{ext}"
    target_dir = FINDING_ATTACHMENT_DIR / str(finding_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / unique_name

    digest = hashlib.sha256()
    total = 0
    with target_path.open("wb") as handle:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FINDING_ATTACHMENT_BYTES:
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Finding evidence exceeds the 15MB limit.")
            digest.update(chunk)
            handle.write(chunk)

    if total <= 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Finding evidence file is empty.")

    return target_path, original_name, digest.hexdigest(), total

def get_actor() -> Optional[str]:
    """
    Replace with your JWT dependency.
    Return a stable user id string (e.g., UUID or int as str).
    """
    return get_current_actor_id()


def _ensure_qms_notification_assets(db: Session) -> None:
    bind = db.get_bind()
    models.QMSNotification.__table__.create(bind=bind, checkfirst=True)
    inspector = inspect(bind)
    if inspector.has_table("qms_notifications"):
        existing = {col["name"] for col in inspector.get_columns("qms_notifications")}
        notification_columns = {
            "action_url": "VARCHAR(1024)",
            "action_label": "VARCHAR(80)",
            "entity_type": "VARCHAR(64)",
            "entity_id": "VARCHAR(64)",
        }
        for column_name, column_type in notification_columns.items():
            if column_name not in existing:
                db.execute(text(f"ALTER TABLE qms_notifications ADD COLUMN {column_name} {column_type}"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_notifications_entity_runtime ON qms_notifications (entity_type, entity_id)"))


def _safe_notification_action_url(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    if len(raw) > 1024:
        raw = raw[:1024]
    if raw.startswith(("/", "http://", "https://")):
        return raw
    return f"/{raw}"


def _safe_notification_action_label(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip()
    return raw[:80] if raw else None


def _amo_login_slug(db: Session, amo_id: Optional[str]) -> str:
    if not amo_id:
        return "safarilink"
    try:
        amo = db.query(account_models.AMO).filter(account_models.AMO.id == amo_id).first()
    except Exception:
        amo = None
    slug = getattr(amo, "login_slug", None) or getattr(amo, "amo_code", None) or amo_id
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(slug).strip().lower()).strip("-")
    return slug or str(amo_id).lower()


def _audit_workspace_notification_url(db: Session, audit: Optional[models.QMSAudit], *, tab: str = "cars", car_id: Optional[UUID] = None) -> Optional[str]:
    if not audit:
        return None
    params = f"tab={tab}"
    if car_id:
        params += f"&carId={car_id}"
    return f"/maintenance/{_amo_login_slug(db, audit.amo_id)}/quality/audits/{audit.id}?{params}"


def _notify_user(
    db: Session,
    user_id: Optional[str],
    message: str,
    severity=models.QMSNotificationSeverity,
    *,
    action_url: Optional[str] = None,
    action_label: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
):
    if not user_id:
        return
    recipient = _load_user(db, user_id)
    amo_id = getattr(recipient, "effective_amo_id", None) or getattr(recipient, "amo_id", None)
    if not amo_id:
        return

    def _insert_notification() -> None:
        note = models.QMSNotification(
            amo_id=amo_id,
            user_id=user_id,
            message=message,
            severity=severity,
            created_by_user_id=get_actor(),
            action_url=_safe_notification_action_url(action_url),
            action_label=_safe_notification_action_label(action_label),
            entity_type=(entity_type or None),
            entity_id=(str(entity_id) if entity_id is not None else None),
        )
        with db.begin_nested():
            db.add(note)
            db.flush()

    try:
        _insert_notification()
    except (OperationalError, ProgrammingError) as exc:
        if not _is_missing_table_error(exc):
            raise
        _ensure_qms_notification_assets(db)
        _insert_notification()


def _load_user(db: Session, user_id: Optional[str]) -> Optional[account_models.User]:
    if not user_id:
        return None
    return db.query(account_models.User).filter(account_models.User.id == user_id).first()


def _json_list(value: Optional[str], fallback: Optional[list] = None) -> list:
    if not value:
        return list(fallback or [])
    try:
        parsed = json.loads(value)
    except Exception:
        return list(fallback or [])
    return parsed if isinstance(parsed, list) else list(fallback or [])


def _json_dict(value: Optional[str], fallback: Optional[dict] = None) -> dict:
    if not value:
        return dict(fallback or {})
    try:
        parsed = json.loads(value)
    except Exception:
        return dict(fallback or {})
    return parsed if isinstance(parsed, dict) else dict(fallback or {})


def _settings_out(settings: models.QualityTenantWorkflowSettings) -> QualityWorkflowSettingsOut:
    return QualityWorkflowSettingsOut(
        id=settings.id,
        amo_id=settings.amo_id,
        report_due_days=settings.report_due_days,
        report_reminder_days=settings.report_reminder_days,
        car_reminder_percentages=settings.car_reminder_percentages,
        final_reminder_days_before_due=settings.final_reminder_days_before_due,
        auto_escalation_enabled=settings.auto_escalation_enabled,
        auto_escalation_locked=settings.auto_escalation_locked,
        created_by_user_id=settings.created_by_user_id,
        updated_by_user_id=settings.updated_by_user_id,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


def _get_or_create_workflow_settings(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str] = None,
) -> models.QualityTenantWorkflowSettings:
    settings = (
        db.query(models.QualityTenantWorkflowSettings)
        .filter(models.QualityTenantWorkflowSettings.amo_id == amo_id)
        .first()
    )
    if settings:
        return settings
    settings = models.QualityTenantWorkflowSettings(
        amo_id=amo_id,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(settings)
    db.flush()
    return settings


def _report_tracker_for_audit(
    db: Session,
    *,
    audit: models.QMSAudit,
    report_due_date: date,
    actor_user_id: Optional[str] = None,
) -> models.QualityAuditReportTracker:
    tracker = (
        db.query(models.QualityAuditReportTracker)
        .filter(models.QualityAuditReportTracker.audit_id == audit.id)
        .first()
    )
    settings = _get_or_create_workflow_settings(db, amo_id=str(audit.amo_id), actor_user_id=actor_user_id)
    first_reminder = min(settings.report_reminder_days or [7, 3, 1])
    next_reminder_at = datetime.combine(report_due_date - timedelta(days=first_reminder), time.min, tzinfo=timezone.utc)
    if not tracker:
        tracker = models.QualityAuditReportTracker(
            amo_id=audit.amo_id,
            audit_id=audit.id,
            report_due_date=report_due_date,
            next_reminder_at=next_reminder_at,
            created_by_user_id=actor_user_id,
        )
        db.add(tracker)
        db.flush()
    else:
        tracker.report_due_date = report_due_date
        tracker.next_reminder_at = tracker.next_reminder_at or next_reminder_at
        tracker.updated_at = datetime.now(timezone.utc)
    return tracker


def _post_brief_out(item: models.QualityAuditPostBrief) -> QualityPostBriefOut:
    return QualityPostBriefOut(
        id=item.id,
        amo_id=item.amo_id,
        audit_id=item.audit_id,
        briefing_at=item.briefing_at,
        summary=item.summary,
        attendees=_json_list(item.attendees_json),
        report_due_date=item.report_due_date,
        created_by_user_id=item.created_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _archive_out(item: models.QualityArchivePackage) -> QualityArchivePackageOut:
    return QualityArchivePackageOut(
        id=item.id,
        amo_id=item.amo_id,
        audit_id=item.audit_id,
        package_ref=item.package_ref,
        status=item.status,
        file_ref=item.file_ref,
        metrics_snapshot=_json_dict(item.metrics_snapshot_json),
        generated_by_user_id=item.generated_by_user_id,
        generated_at=item.generated_at,
        created_at=item.created_at,
    )


def _audit_metrics(db: Session, audit: models.QMSAudit) -> dict[str, Any]:
    findings = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.audit_id == audit.id).all()
    finding_ids = [finding.id for finding in findings]
    cars = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.finding_id.in_(finding_ids))
        .all()
        if finding_ids else []
    )
    doc_requests_total = db.query(models.QualityAuditDocumentRequest).filter(models.QualityAuditDocumentRequest.audit_id == audit.id).count()
    doc_requests_open = (
        db.query(models.QualityAuditDocumentRequest)
        .filter(
            models.QualityAuditDocumentRequest.audit_id == audit.id,
            models.QualityAuditDocumentRequest.status.in_(["REQUESTED", "UPLOADED", "REJECTED"]),
        )
        .count()
    )
    checklist_total = db.query(models.QualityAuditChecklistItem).filter(models.QualityAuditChecklistItem.audit_id == audit.id, models.QualityAuditChecklistItem.amo_id == audit.amo_id).count()
    checklist_completed = (
        db.query(models.QualityAuditChecklistItem)
        .filter(
            models.QualityAuditChecklistItem.audit_id == audit.id,
            models.QualityAuditChecklistItem.amo_id == audit.amo_id,
            models.QualityAuditChecklistItem.response_status != "PENDING",
        )
        .count()
    )
    tracker = db.query(models.QualityAuditReportTracker).filter(models.QualityAuditReportTracker.audit_id == audit.id).first()
    today = date.today()
    return {
        "audit_id": audit.id,
        "audit_ref": audit.audit_ref,
        "findings_total": len(findings),
        "findings_open": sum(1 for finding in findings if not finding.closed_at),
        "cars_total": len(cars),
        "cars_open": sum(1 for car in cars if car.status != models.CARStatus.CLOSED),
        "cars_overdue": sum(1 for car in cars if car.status != models.CARStatus.CLOSED and car.due_date and car.due_date < today),
        "document_requests_total": doc_requests_total,
        "document_requests_open": doc_requests_open,
        "checklist_total": checklist_total,
        "checklist_completed": checklist_completed,
        "report_status": tracker.status if tracker else None,
        "report_due_date": tracker.report_due_date if tracker else None,
        "archive_ready": bool(audit.report_file_ref and not any(car.status != models.CARStatus.CLOSED for car in cars)),
    }


def _quality_manager_recipient_ids(db: Session, amo_id: str) -> set[str]:
    roles = {account_models.AccountRole.QUALITY_MANAGER, "QUALITY_MANAGER"}
    recipients: set[str] = set()
    users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True)).all()
    for user in users:
        if getattr(user.role, "value", user.role) in roles:
            recipients.add(user.id)
    return recipients


def _quality_governance_recipient_ids(db: Session, amo_id: str) -> set[str]:
    roles = {
        account_models.AccountRole.AMO_ADMIN,
        account_models.AccountRole.QUALITY_MANAGER,
        account_models.AccountRole.AUDITOR,
        "AMO_ADMIN",
        "QUALITY_MANAGER",
        "AUDITOR",
    }
    recipients: set[str] = set()
    users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True)).all()
    for user in users:
        role_value = getattr(user.role, "value", user.role)
        title = (getattr(user, "position_title", None) or "").upper()
        if role_value in roles or "ACCOUNTABLE MANAGER" in title:
            recipients.add(user.id)
    return recipients


def _car_escalation_recipient_ids(db: Session, car: models.CorrectiveActionRequest) -> set[str]:
    recipients = _quality_governance_recipient_ids(db, str(car.amo_id))
    for value in (car.requested_by_user_id, car.assigned_to_user_id):
        if value:
            recipients.add(value)
    if car.finding_id:
        audit = (
            db.query(models.QMSAudit)
            .join(models.QMSAuditFinding, models.QMSAuditFinding.audit_id == models.QMSAudit.id)
            .filter(models.QMSAuditFinding.id == car.finding_id)
            .first()
        )
        if audit:
            for value in (audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id, audit.auditee_user_id):
                if value:
                    recipients.add(value)
    return recipients


def _create_reminder_if_missing(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    milestone_key: str,
    scheduled_for: datetime,
    due_date: Optional[date],
    recipient_user_id: Optional[str],
    message: str,
    severity: str = "ACTION_REQUIRED",
) -> models.QualityReminderMilestone:
    existing = (
        db.query(models.QualityReminderMilestone)
        .filter(
            models.QualityReminderMilestone.amo_id == amo_id,
            models.QualityReminderMilestone.entity_type == entity_type,
            models.QualityReminderMilestone.entity_id == entity_id,
            models.QualityReminderMilestone.milestone_key == milestone_key,
            models.QualityReminderMilestone.recipient_user_id == recipient_user_id,
        )
        .first()
    )
    if existing:
        return existing
    reminder = models.QualityReminderMilestone(
        amo_id=amo_id,
        entity_type=entity_type,
        entity_id=entity_id,
        milestone_key=milestone_key,
        recipient_user_id=recipient_user_id,
        scheduled_for=scheduled_for,
        due_date=due_date,
        message=message,
        severity=severity,
    )
    db.add(reminder)
    db.flush()
    return reminder


def _seed_car_reminders(db: Session, car: models.CorrectiveActionRequest) -> list[models.QualityReminderMilestone]:
    if not car.due_date:
        return []
    settings = _get_or_create_workflow_settings(db, amo_id=str(car.amo_id), actor_user_id=car.requested_by_user_id)
    created: list[models.QualityReminderMilestone] = []
    today = date.today()
    due_date = car.due_date
    total_days = max((due_date - today).days, 0)
    recipients = _car_escalation_recipient_ids(db, car)
    if car.assigned_to_user_id:
        recipients.add(car.assigned_to_user_id)
    for pct in settings.car_reminder_percentages or [75, 50, 25]:
        days_remaining = max(int(round(total_days * (pct / 100))), 0)
        scheduled_date = due_date - timedelta(days=days_remaining)
        for recipient in recipients:
            created.append(_create_reminder_if_missing(
                db,
                amo_id=str(car.amo_id),
                entity_type="quality_car",
                entity_id=str(car.id),
                milestone_key=f"CAR_DUE_{pct}_PERCENT_REMAINING",
                scheduled_for=datetime.combine(scheduled_date, time.min, tzinfo=timezone.utc),
                due_date=due_date,
                recipient_user_id=recipient,
                message=f"CAR {car.car_number} CAPA is due on {due_date.isoformat()} ({pct}% reminder).",
            ))
    final_days = settings.final_reminder_days_before_due
    final_date = due_date - timedelta(days=final_days)
    for recipient in recipients:
        created.append(_create_reminder_if_missing(
            db,
            amo_id=str(car.amo_id),
            entity_type="quality_car",
            entity_id=str(car.id),
            milestone_key="CAR_FINAL_REMINDER",
            scheduled_for=datetime.combine(final_date, time.min, tzinfo=timezone.utc),
            due_date=due_date,
            recipient_user_id=recipient,
            message=f"Final reminder: CAR {car.car_number} CAPA is due on {due_date.isoformat()}.",
            severity="WARNING",
        ))
        created.append(_create_reminder_if_missing(
            db,
            amo_id=str(car.amo_id),
            entity_type="quality_car",
            entity_id=str(car.id),
            milestone_key="CAR_DUE_DATE",
            scheduled_for=datetime.combine(due_date, time.min, tzinfo=timezone.utc),
            due_date=due_date,
            recipient_user_id=recipient,
            message=f"CAR {car.car_number} CAPA is due today.",
            severity="WARNING",
        ))
    return created


def _seed_report_reminders(db: Session, tracker: models.QualityAuditReportTracker, audit: models.QMSAudit) -> list[models.QualityReminderMilestone]:
    settings = _get_or_create_workflow_settings(db, amo_id=str(audit.amo_id), actor_user_id=tracker.created_by_user_id)
    recipients = {value for value in (audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id) if value}
    recipients.update(_quality_governance_recipient_ids(db, str(audit.amo_id)))
    created: list[models.QualityReminderMilestone] = []
    for days_before in settings.report_reminder_days or [7, 3, 1]:
        scheduled_date = tracker.report_due_date - timedelta(days=days_before)
        for recipient in recipients:
            created.append(_create_reminder_if_missing(
                db,
                amo_id=str(audit.amo_id),
                entity_type="quality_audit_report",
                entity_id=str(tracker.id),
                milestone_key=f"REPORT_DUE_MINUS_{days_before}_DAYS",
                scheduled_for=datetime.combine(scheduled_date, time.min, tzinfo=timezone.utc),
                due_date=tracker.report_due_date,
                recipient_user_id=recipient,
                message=f"Audit report for {audit.audit_ref} is due on {tracker.report_due_date.isoformat()}.",
                severity="ACTION_REQUIRED",
            ))
    return created


def _user_display_name(user: Optional[account_models.User], fallback: Optional[str] = None) -> str:
    if user is None:
        return (fallback or "").strip() or "Unassigned"
    return (
        getattr(user, "full_name", None)
        or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        or getattr(user, "email", None)
        or getattr(user, "staff_code", None)
        or (fallback or "").strip()
        or str(user.id)
    )


def _normalized_email(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _serialize_external_auditees(value: Optional[list[Any]]) -> Optional[str]:
    cleaned: list[dict[str, str | None]] = []
    for row in value or []:
        if hasattr(row, "model_dump"):
            item = row.model_dump()
        elif isinstance(row, dict):
            item = dict(row)
        else:
            continue
        email = _normalized_email(item.get("email"))
        first_name = (item.get("first_name") or "").strip()
        last_name = (item.get("last_name") or "").strip()
        designation = (item.get("designation") or "").strip()
        phone_contact = _normalized_email(item.get("phone_contact"))
        if not (first_name and last_name and email and designation):
            continue
        cleaned.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone_contact": phone_contact,
                "designation": designation,
            }
        )
    return json.dumps(cleaned) if cleaned else None


def _deserialize_external_auditees(raw_value: Optional[str]) -> list[dict[str, Optional[str]]]:
    if not raw_value:
        return []
    try:
        rows = json.loads(raw_value)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Optional[str]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        first_name = (row.get("first_name") or "").strip()
        last_name = (row.get("last_name") or "").strip()
        email = _normalized_email(row.get("email"))
        designation = (row.get("designation") or "").strip()
        phone_contact = _normalized_email(row.get("phone_contact"))
        if not (first_name and last_name and email and designation):
            continue
        result.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone_contact": phone_contact,
                "designation": designation,
            }
        )
    return result


def _external_auditee_summary(external_auditees: list[dict[str, Optional[str]]]) -> tuple[Optional[str], Optional[str]]:
    if not external_auditees:
        return None, None
    first = external_auditees[0]
    label = f"{first.get('first_name', '')} {first.get('last_name', '')}".strip() or None
    return label, _normalized_email(first.get("email"))


def _serialize_schedule(schedule: models.QMSAuditSchedule) -> QMSAuditScheduleOut:
    return QMSAuditScheduleOut.model_validate(schedule, from_attributes=True)


def _looks_like_portal_identifier(value: Optional[str]) -> bool:
    clean = (value or "").strip()
    if not clean:
        return False
    compact = re.sub(r"\s+", "", clean)
    return bool(
        re.match(r"^ID[-_A-Z0-9]{4,}$", compact, re.IGNORECASE)
        or re.match(r"^[a-f0-9]{24,64}$", compact, re.IGNORECASE)
        or re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", compact, re.IGNORECASE)
    )


def _portal_user_name(user: Optional[account_models.User]) -> Optional[str]:
    if user is None:
        return None
    full_name = (getattr(user, "full_name", None) or "").strip()
    first_last = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    for candidate in (full_name, first_last):
        clean = (candidate or "").strip()
        if clean and not _looks_like_portal_identifier(clean):
            return clean
    return None


def _audit_person_display_names(db: Session, audit: models.QMSAudit) -> dict[str, Optional[str]]:
    raw_values = {
        "lead_auditor_name": audit.lead_auditor_user_id,
        "observer_auditor_name": audit.observer_auditor_user_id,
        "assistant_auditor_name": audit.assistant_auditor_user_id,
        "auditee_user_name": audit.auditee_user_id,
    }
    identifiers = {(value or "").strip() for value in raw_values.values() if (value or "").strip()}
    if not identifiers:
        return {key: None for key in raw_values}

    lowered = {value.lower() for value in identifiers}
    users = (
        db.query(account_models.User)
        .filter(account_models.User.amo_id == audit.amo_id)
        .filter(
            or_(
                cast(account_models.User.id, String).in_(identifiers),
                func.lower(account_models.User.staff_code).in_(lowered),
                func.lower(account_models.User.email).in_(lowered),
            )
        )
        .all()
    )

    lookup: dict[str, account_models.User] = {}
    for user in users:
        for key in (getattr(user, "id", None), getattr(user, "staff_code", None), getattr(user, "email", None)):
            clean = (str(key) if key is not None else "").strip().lower()
            if clean:
                lookup[clean] = user

    resolved: dict[str, Optional[str]] = {}
    for output_key, raw_value in raw_values.items():
        clean = (raw_value or "").strip().lower()
        resolved[output_key] = _portal_user_name(lookup.get(clean)) if clean else None
    return resolved


def _serialize_audit(audit: models.QMSAudit, db: Optional[Session] = None) -> QMSAuditOut:
    serialized = QMSAuditOut.model_validate(audit, from_attributes=True)
    if db is None:
        return serialized
    return serialized.model_copy(update=_audit_person_display_names(db, audit))


def _collect_audit_notice_recipients(
    db: Session,
    *,
    lead_auditor_user_id: Optional[str],
    auditee_user_id: Optional[str],
    auditee_email: Optional[str],
    auditee_label: Optional[str],
    external_auditees: Optional[list[dict[str, Optional[str]]]] = None,
    notify_auditors: bool = True,
    notify_auditees: bool = True,
) -> list[dict[str, Optional[str]]]:
    recipients: list[dict[str, Optional[str]]] = []
    seen: set[tuple[Optional[str], Optional[str], Optional[str]]] = set()

    def _add(role: str, *, user: Optional[account_models.User] = None, email: Optional[str] = None, label: Optional[str] = None) -> None:
        normalized_email = _normalized_email(email)
        user_id = getattr(user, "id", None)
        dedupe_key = (role, user_id, (normalized_email or "").lower() or None)
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        recipients.append(
            {
                "role": role,
                "user_id": user_id,
                "email": normalized_email,
                "label": (label or "").strip() or _user_display_name(user, fallback=label),
            }
        )

    lead_user = _load_user(db, lead_auditor_user_id)
    if notify_auditors and lead_user is not None:
        _add(
            "lead_auditor",
            user=lead_user,
            email=getattr(lead_user, "email", None),
            label=_user_display_name(lead_user),
        )

    auditee_user = _load_user(db, auditee_user_id)
    provided_auditee_email = _normalized_email(auditee_email)
    if notify_auditees and auditee_user is not None:
        internal_email = _normalized_email(getattr(auditee_user, "email", None))
        _add(
            "auditee",
            user=auditee_user,
            email=internal_email or provided_auditee_email,
            label=_user_display_name(auditee_user, fallback=auditee_label),
        )
        if provided_auditee_email and provided_auditee_email.lower() != (internal_email or "").lower():
            _add("auditee_external", email=provided_auditee_email, label=auditee_label or provided_auditee_email)
    elif notify_auditees and provided_auditee_email:
        _add("auditee_external", email=provided_auditee_email, label=auditee_label or provided_auditee_email)

    if notify_auditees:
        for item in external_auditees or []:
            label = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or item.get("designation") or item.get("email")
            _add("auditee_external", email=item.get("email"), label=label)

    return recipients


def _send_notice_email(
    db: Session,
    *,
    amo_id: str,
    template_key: str,
    recipient: Optional[str],
    subject: str,
    context: dict,
    correlation_id: Optional[str],
) -> None:
    if not _normalized_email(recipient):
        return
    notification_service.send_email(
        template_key=template_key,
        recipient=recipient,
        subject=subject,
        context=context,
        correlation_id=correlation_id,
        amo_id=amo_id,
        db=db,
    )


def _dispatch_schedule_notice(db: Session, *, schedule: models.QMSAuditSchedule, amo_id: str) -> None:
    lead_user = _load_user(db, schedule.lead_auditor_user_id)
    lead_label = _user_display_name(lead_user)
    recipients = _collect_audit_notice_recipients(
        db,
        lead_auditor_user_id=schedule.lead_auditor_user_id,
        auditee_user_id=schedule.auditee_user_id,
        auditee_email=schedule.auditee_email,
        auditee_label=schedule.auditee,
        external_auditees=_deserialize_external_auditees(schedule.external_auditees_json),
        notify_auditors=bool(schedule.notify_auditors),
        notify_auditees=bool(schedule.notify_auditees),
    )
    for recipient in recipients:
        role = recipient["role"] or "recipient"
        recipient_label = recipient["label"] or recipient["email"] or "recipient"
        if role == "lead_auditor" and recipient["user_id"]:
            _notify_user(
                db,
                recipient["user_id"],
                f"You have been assigned as lead auditor for scheduled audit {schedule.title} due {schedule.next_due_date.isoformat()}.",
                models.QMSNotificationSeverity.INFO,
            )
        elif role.startswith("auditee") and recipient["user_id"]:
            _notify_user(
                db,
                recipient["user_id"],
                f"You have been listed as auditee for scheduled audit {schedule.title} due {schedule.next_due_date.isoformat()}.",
                models.QMSNotificationSeverity.INFO,
            )
        _send_notice_email(
            db,
            amo_id=amo_id,
            template_key="qms_audit_schedule_notice",
            recipient=recipient["email"],
            subject=f"Audit schedule notice · {schedule.title}",
            context={
                "recipient_role": role,
                "recipient_label": recipient_label,
                "title": schedule.title,
                "kind": schedule.kind.value,
                "frequency": schedule.frequency.value,
                "next_due_date": schedule.next_due_date.isoformat(),
                "scope": schedule.scope,
                "criteria": schedule.criteria,
                "auditee": schedule.auditee,
                "external_auditees": _deserialize_external_auditees(schedule.external_auditees_json),
                "lead_auditor": lead_label,
                "reminder_interval_days": schedule.reminder_interval_days,
            },
            correlation_id=str(schedule.id),
        )


def _dispatch_audit_notice(db: Session, *, audit: models.QMSAudit, amo_id: str) -> None:
    planned_start = audit.planned_start.isoformat() if audit.planned_start else None
    planned_end = audit.planned_end.isoformat() if audit.planned_end else None
    lead_user = _load_user(db, audit.lead_auditor_user_id)
    lead_label = _user_display_name(lead_user)
    recipients = _collect_audit_notice_recipients(
        db,
        lead_auditor_user_id=audit.lead_auditor_user_id,
        auditee_user_id=audit.auditee_user_id,
        auditee_email=audit.auditee_email,
        auditee_label=audit.auditee,
        external_auditees=_deserialize_external_auditees(audit.external_auditees_json),
        notify_auditors=bool(audit.notify_auditors),
        notify_auditees=bool(audit.notify_auditees),
    )
    for recipient in recipients:
        role = recipient["role"] or "recipient"
        recipient_label = recipient["label"] or recipient["email"] or "recipient"
        if role == "lead_auditor" and recipient["user_id"]:
            _notify_user(
                db,
                recipient["user_id"],
                f"Audit notice memo issued: {audit.audit_ref} · {audit.title} starts {planned_start or 'TBD'}.",
                models.QMSNotificationSeverity.ACTION_REQUIRED,
            )
        elif role.startswith("auditee") and recipient["user_id"]:
            _notify_user(
                db,
                recipient["user_id"],
                f"Audit notice memo issued to auditee: {audit.audit_ref} · {audit.title} starts {planned_start or 'TBD'}.",
                models.QMSNotificationSeverity.ACTION_REQUIRED,
            )
        _send_notice_email(
            db,
            amo_id=amo_id,
            template_key="qms_audit_notice_memo",
            recipient=recipient["email"],
            subject=f"Audit Notice Memo · {audit.audit_ref}",
            context={
                "recipient_role": role,
                "recipient_label": recipient_label,
                "audit_ref": audit.audit_ref,
                "title": audit.title,
                "planned_start": planned_start,
                "planned_end": planned_end,
                "scope": audit.scope,
                "criteria": audit.criteria,
                "auditee": audit.auditee,
                "external_auditees": _deserialize_external_auditees(audit.external_auditees_json),
                "lead_auditor": lead_label,
                "reminder_interval_days": audit.reminder_interval_days,
            },
            correlation_id=str(audit.id),
        )


def _role_value(current_user: account_models.User) -> str | account_models.AccountRole | None:
    role_value = getattr(current_user, "role", None)
    return getattr(role_value, "value", role_value)


def _is_quality_manager(current_user: account_models.User) -> bool:
    return _role_value(current_user) in {
        account_models.AccountRole.QUALITY_MANAGER,
        "QUALITY_MANAGER",
    }


def _is_system_quality_admin(current_user: account_models.User) -> bool:
    role_value = _role_value(current_user)
    return bool(
        getattr(current_user, "is_superuser", False)
        or getattr(current_user, "is_amo_admin", False)
        or role_value
        in {
            account_models.AccountRole.SUPERUSER,
            account_models.AccountRole.AMO_ADMIN,
            "SUPERUSER",
            "AMO_ADMIN",
        }
    )


def _is_quality_admin(current_user: account_models.User) -> bool:
    return _is_system_quality_admin(current_user) or _is_quality_manager(current_user)


def _is_quality_scheduler(current_user: account_models.User) -> bool:
    role_value = _role_value(current_user)
    return _is_quality_admin(current_user) or role_value in {
        account_models.AccountRole.AUDITOR,
        account_models.AccountRole.QUALITY_INSPECTOR,
        "AUDITOR",
        "QUALITY_INSPECTOR",
    }


def _require_quality_scheduler(current_user: account_models.User) -> None:
    if not _is_quality_scheduler(current_user):
        raise HTTPException(status_code=403, detail="Only Quality team roles can schedule audits or issue CARs")


def _audit_allows_user(db: Session, finding_id: Optional[UUID], user_id: str) -> bool:
    if not finding_id:
        return False
    audit = (
        db.query(models.QMSAudit)
        .join(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.id == finding_id)
        .first()
    )
    if not audit:
        return False
    return user_id in {
        audit.lead_auditor_user_id,
        audit.observer_auditor_user_id,
        audit.assistant_auditor_user_id,
    }


def _audit_allows_user_by_audit(audit: models.QMSAudit, user_id: str) -> bool:
    return user_id in {
        audit.lead_auditor_user_id,
        audit.observer_auditor_user_id,
        audit.assistant_auditor_user_id,
    }


def _audit_lead_allows_user_by_audit(audit: models.QMSAudit, user_id: str) -> bool:
    return bool(user_id and audit.lead_auditor_user_id == user_id)


def _audit_for_finding(db: Session, finding_id: Optional[UUID]) -> Optional[models.QMSAudit]:
    if not finding_id:
        return None
    return (
        db.query(models.QMSAudit)
        .join(models.QMSAuditFinding, models.QMSAuditFinding.audit_id == models.QMSAudit.id)
        .filter(models.QMSAuditFinding.id == finding_id)
        .first()
    )


def _current_user_can_modify_finding(current_user: account_models.User, finding: models.QMSAuditFinding, audit: models.QMSAudit) -> bool:
    if _is_system_quality_admin(current_user):
        return True
    if _audit_lead_allows_user_by_audit(audit, current_user.id):
        return True
    return False


def _require_audit_fieldwork_write_access(current_user: account_models.User, audit: models.QMSAudit) -> None:
    if _is_system_quality_admin(current_user):
        return
    if _audit_allows_user_by_audit(audit, current_user.id):
        return
    if _is_quality_manager(current_user):
        raise HTTPException(status_code=403, detail="Quality Managers may flag fieldwork records for review, but cannot create or modify findings unless assigned to the audit team.")
    raise HTTPException(status_code=403, detail="Only the assigned audit team, AMO Admin, or Superuser may record audit findings.")


def _require_finding_owner_access(current_user: account_models.User, finding: models.QMSAuditFinding, audit: models.QMSAudit) -> None:
    if _current_user_can_modify_finding(current_user, finding, audit):
        return
    if _is_quality_manager(current_user):
        raise HTTPException(status_code=403, detail="Quality Managers may flag audit findings for review, but cannot modify finding details, evidence, or linked CARs unless assigned as the lead auditor.")
    raise HTTPException(status_code=403, detail="Only the lead auditor, AMO Admin, or Superuser may modify this finding.")


def _current_user_can_modify_car(db: Session, current_user: account_models.User, car: models.CorrectiveActionRequest) -> bool:
    if _is_system_quality_admin(current_user):
        return True
    audit = _audit_for_finding(db, car.finding_id)
    if audit:
        return _audit_lead_allows_user_by_audit(audit, current_user.id)
    if _is_quality_manager(current_user):
        return False
    return bool(car.requested_by_user_id and car.requested_by_user_id == current_user.id)


def _require_car_not_escalated(car: models.CorrectiveActionRequest) -> None:
    if car.status == models.CARStatus.ESCALATED:
        raise HTTPException(status_code=423, detail="This CAR has been escalated to the Accountable Manager and is view-only.")


def _require_car_review_access(db: Session, current_user: account_models.User, car: models.CorrectiveActionRequest) -> None:
    if _is_system_quality_admin(current_user):
        return
    audit = _audit_for_finding(db, car.finding_id)
    if audit and _audit_lead_allows_user_by_audit(audit, current_user.id):
        return
    if _is_quality_manager(current_user):
        raise HTTPException(status_code=403, detail="Quality Managers may receive or flag deferrals for review, but cannot accept/reject CARs unless assigned as the lead auditor.")
    raise HTTPException(status_code=403, detail="Only the lead auditor, AMO Admin, or Superuser may review CAR responses or deferrals.")


def _require_audit_access(
    current_user: account_models.User,
    audit: models.QMSAudit,
    *,
    allow_auditee: bool = False,
) -> None:
    if _is_quality_admin(current_user):
        return
    if _audit_allows_user_by_audit(audit, current_user.id):
        return
    if allow_auditee and audit.auditee_user_id == current_user.id:
        return
    raise HTTPException(status_code=403, detail="Insufficient privileges to modify audit data")


def _require_car_write_access(
    db: Session,
    current_user: account_models.User,
    finding_id: Optional[UUID],
    car: Optional[models.CorrectiveActionRequest] = None,
    allow_assignee: bool = False,
) -> None:
    if car and allow_assignee and current_user.id == car.assigned_to_user_id:
        return
    if car and _current_user_can_modify_car(db, current_user, car):
        return
    audit = _audit_for_finding(db, finding_id)
    if audit and (_is_system_quality_admin(current_user) or _audit_lead_allows_user_by_audit(audit, current_user.id)):
        return
    if _is_quality_manager(current_user):
        raise HTTPException(status_code=403, detail="Quality Managers may flag CARs/findings for review, but cannot modify them unless assigned as the lead auditor.")
    raise HTTPException(status_code=403, detail="Only the lead auditor, requester, AMO Admin, or Superuser may modify CARs")


def _assignee_can_request_extension(
    db: Session,
    car: models.CorrectiveActionRequest,
    requested_date: date,
) -> bool:
    if not car.finding_id:
        return False
    finding = (
        db.query(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.id == car.finding_id)
        .first()
    )
    if not finding:
        return False
    baseline = finding.target_close_date
    if baseline is None:
        baseline = compute_target_close_date(finding.level, base=finding.created_at.date())
    return requested_date > baseline


@router.get("/qms/dashboard", response_model=QMSDashboardOut)
def qms_dashboard(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = Query(default=None),
):
    return get_dashboard(db, domain=domain)


@router.get("/qms/cockpit-snapshot", response_model=QMSCockpitSnapshotOut)
def qms_cockpit_snapshot(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = Query(default=None),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return get_cockpit_snapshot(
        db,
        domain=domain,
        amo_id=getattr(current_user, "effective_amo_id", None) or current_user.amo_id,
        department_code="quality",
    )


@router.get("/qms/manpower/availability", response_model=List[QMSManpowerAvailabilityOut])
def list_manpower_availability(
    department: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = getattr(current_user, "effective_amo_id", None) or current_user.amo_id
    qs = db.query(models.UserAvailability).filter(models.UserAvailability.amo_id == amo_id)
    if department:
        dept = db.query(account_models.Department.id).filter(
            account_models.Department.amo_id == amo_id,
            account_models.Department.code == department,
        ).first()
        if dept:
            qs = qs.join(account_models.User, account_models.User.id == models.UserAvailability.user_id).filter(account_models.User.department_id == dept.id)
    return qs.order_by(models.UserAvailability.updated_at.desc()).all()


@router.post("/qms/manpower/availability", response_model=QMSManpowerAvailabilityOut, status_code=status.HTTP_201_CREATED)
def upsert_manpower_availability(
    payload: QMSManpowerAvailabilityUpsert,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not _is_quality_scheduler(current_user):
        raise HTTPException(status_code=403, detail="Insufficient privileges to set manpower availability")

    amo_id = getattr(current_user, "effective_amo_id", None) or current_user.amo_id
    user = db.query(account_models.User).filter(account_models.User.id == payload.user_id, account_models.User.amo_id == amo_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in tenant scope")

    item = models.UserAvailability(
        amo_id=amo_id,
        user_id=payload.user_id,
        status=models.UserAvailabilityStatus(payload.status),
        effective_from=payload.effective_from or datetime.now(timezone.utc),
        effective_to=payload.effective_to,
        note=payload.note,
        updated_by_user_id=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# -----------------------------
# Quality workflow controls
# -----------------------------


@router.get("/workflow/settings", response_model=QualityWorkflowSettingsOut)
def get_quality_workflow_settings(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    settings = _get_or_create_workflow_settings(
        db,
        amo_id=str(_current_amo_id(current_user)),
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)


@router.patch("/workflow/settings", response_model=QualityWorkflowSettingsOut)
def update_quality_workflow_settings(
    payload: QualityWorkflowSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not _is_quality_admin(current_user):
        raise HTTPException(status_code=403, detail="Only Quality Managers or AMO Admins can update Quality workflow settings")
    amo_id = str(_current_amo_id(current_user))
    settings = _get_or_create_workflow_settings(db, amo_id=amo_id, actor_user_id=current_user.id)
    data = payload.model_dump(exclude_unset=True)
    before = _settings_out(settings).model_dump(mode="json")
    if data.get("auto_escalation_enabled") is False and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Tenant admins cannot disable automatic escalation. Only platform superuser may disable it for a tenant.")
    if "report_due_days" in data and data["report_due_days"] is not None:
        settings.report_due_days = int(data["report_due_days"])
    if "report_reminder_days" in data and data["report_reminder_days"] is not None:
        values = sorted({int(v) for v in data["report_reminder_days"] if int(v) >= 0}, reverse=True)
        settings.report_reminder_days_json = json.dumps(values or [7, 3, 1])
    if "car_reminder_percentages" in data and data["car_reminder_percentages"] is not None:
        values = sorted({int(v) for v in data["car_reminder_percentages"] if 0 < int(v) < 100}, reverse=True)
        settings.car_reminder_percentages_json = json.dumps(values or [75, 50, 25])
    if "final_reminder_days_before_due" in data and data["final_reminder_days_before_due"] is not None:
        settings.final_reminder_days_before_due = int(data["final_reminder_days_before_due"])
    if "auto_escalation_enabled" in data and data["auto_escalation_enabled"] is not None:
        settings.auto_escalation_enabled = bool(data["auto_escalation_enabled"])
    settings.updated_by_user_id = current_user.id
    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=current_user.id,
        entity_type="quality_workflow_settings",
        entity_id=str(settings.id),
        action="update",
        before=before,
        after=_settings_out(settings).model_dump(mode="json"),
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical="auto_escalation_enabled" in data,
    )
    db.commit()
    db.refresh(settings)
    return _settings_out(settings)


@router.post("/audits/{audit_id}/document-requests", response_model=QualityDocumentRequestOut, status_code=status.HTTP_201_CREATED)
def create_audit_document_request(
    audit_id: UUID,
    payload: QualityDocumentRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    item = models.QualityAuditDocumentRequest(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        title=payload.title.strip(),
        description=payload.description,
        due_date=payload.due_date,
        requested_by_user_id=current_user.id,
    )
    db.add(item)
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="quality_document_request", entity_id=str(item.id), action="create", after={"audit_ref": audit.audit_ref, "title": item.title}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    db.refresh(item)
    return item


@router.get("/audits/{audit_id}/document-requests", response_model=List[QualityDocumentRequestOut])
def list_audit_document_requests(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    return db.query(models.QualityAuditDocumentRequest).filter(models.QualityAuditDocumentRequest.audit_id == audit_id).order_by(models.QualityAuditDocumentRequest.created_at.desc()).all()


@router.patch("/audits/{audit_id}/document-requests/{request_id}", response_model=QualityDocumentRequestOut)
def update_audit_document_request(
    audit_id: UUID,
    request_id: UUID,
    payload: QualityDocumentRequestUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    item = db.query(models.QualityAuditDocumentRequest).filter(models.QualityAuditDocumentRequest.id == request_id, models.QualityAuditDocumentRequest.audit_id == audit_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Document request not found")
    if not (_is_quality_admin(current_user) or _audit_allows_user_by_audit(audit, current_user.id) or audit.auditee_user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Insufficient privileges to update this document request")
    data = payload.model_dump(exclude_unset=True)
    review_change = False
    for field, value in data.items():
        if field == "status" and value in {"ACCEPTED", "REJECTED", "WAIVED"}:
            _require_audit_access(current_user, audit)
            item.reviewed_by_user_id = current_user.id
            item.reviewed_at = datetime.now(timezone.utc)
            review_change = True
        if field == "file_ref" and value:
            item.uploaded_by_user_id = current_user.id
            item.uploaded_at = datetime.now(timezone.utc)
            if "status" not in data:
                item.status = "UPLOADED"
        setattr(item, field, value)
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="quality_document_request", entity_id=str(item.id), action="review" if review_change else "update", after={"status": item.status}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=review_change)
    db.commit()
    db.refresh(item)
    return item


@router.post("/audits/{audit_id}/checklist-items", response_model=QualityChecklistItemOut, status_code=status.HTTP_201_CREATED)
def create_audit_checklist_item(
    audit_id: UUID,
    payload: QualityChecklistItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    section = (payload.section or "").strip() or None
    checklist_ref = (payload.checklist_ref or "").strip() or None
    requirement_ref = (payload.requirement_ref or "").strip() or None
    prompt = (payload.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="Checklist prompt is required.")
    max_sort_order = (
        db.query(func.max(models.QualityAuditChecklistItem.sort_order))
        .filter(
            models.QualityAuditChecklistItem.audit_id == audit.id,
            models.QualityAuditChecklistItem.amo_id == audit.amo_id,
        )
        .scalar()
    )
    if payload.sort_order is None or payload.sort_order < 0:
        sort_order = int(max_sort_order or 0) + 1
    else:
        sort_order = max(0, int(payload.sort_order))
    item = models.QualityAuditChecklistItem(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        section=section,
        checklist_ref=checklist_ref,
        requirement_ref=requirement_ref,
        prompt=prompt,
        objective_evidence=(payload.objective_evidence or "").strip() or None,
        assigned_to_user_id=(payload.assigned_to_user_id or "").strip() or None,
        sort_order=sort_order,
        created_by_user_id=current_user.id,
    )
    db.add(item)
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="quality_checklist_item", entity_id=str(item.id), action="create", after={"audit_ref": audit.audit_ref, "prompt": item.prompt[:120]}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    db.refresh(item)
    return item


@router.get("/audits/{audit_id}/checklist-items", response_model=List[QualityChecklistItemOut])
def list_audit_checklist_items(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    return (
        db.query(models.QualityAuditChecklistItem)
        .filter(
            models.QualityAuditChecklistItem.audit_id == audit_id,
            models.QualityAuditChecklistItem.amo_id == audit.amo_id,
        )
        .order_by(
            models.QualityAuditChecklistItem.section.asc().nullslast(),
            models.QualityAuditChecklistItem.sort_order.asc(),
            models.QualityAuditChecklistItem.created_at.asc(),
        )
        .all()
    )


@router.patch("/audits/{audit_id}/checklist-items/{item_id}", response_model=QualityChecklistItemOut)
def update_audit_checklist_item(
    audit_id: UUID,
    item_id: UUID,
    payload: QualityChecklistItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    item = (
        db.query(models.QualityAuditChecklistItem)
        .filter(
            models.QualityAuditChecklistItem.id == item_id,
            models.QualityAuditChecklistItem.audit_id == audit_id,
            models.QualityAuditChecklistItem.amo_id == audit.amo_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    data = payload.model_dump(exclude_unset=True)
    original_status = item.response_status
    for field, value in data.items():
        if field in {"section", "checklist_ref", "requirement_ref", "prompt", "objective_evidence", "assigned_to_user_id"}:
            value = (value or "").strip() or None
        if field == "prompt" and not value:
            raise HTTPException(status_code=422, detail="Checklist prompt is required.")
        if field == "sort_order" and value is not None:
            value = max(0, int(value))
        setattr(item, field, value)
    next_status = data.get("response_status", original_status)
    if "response_status" in data:
        if next_status == "PENDING":
            item.completed_by_user_id = None
            item.completed_at = None
        elif next_status in {"COMPLIANT", "NON_CONFORMING", "OBSERVATION", "NOT_APPLICABLE"}:
            item.completed_by_user_id = current_user.id
            item.completed_at = datetime.now(timezone.utc)
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="quality_checklist_item", entity_id=str(item.id), action="update", after={"response_status": item.response_status, "finding_id": str(item.finding_id) if item.finding_id else None}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    db.refresh(item)
    return item


@router.post("/audits/{audit_id}/fieldwork/complete", response_model=QualityReportTrackerOut)
def complete_audit_fieldwork(
    audit_id: UUID,
    payload: QualityFieldworkComplete,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    settings = _get_or_create_workflow_settings(db, amo_id=str(audit.amo_id), actor_user_id=current_user.id)
    actual_end = payload.actual_end or date.today()
    audit.actual_end = actual_end
    if audit.status == models.QMSAuditStatus.PLANNED:
        audit.status = models.QMSAuditStatus.IN_PROGRESS
    report_due = actual_end + timedelta(days=settings.report_due_days)
    tracker = _report_tracker_for_audit(db, audit=audit, report_due_date=report_due, actor_user_id=current_user.id)
    _seed_report_reminders(db, tracker, audit)
    if payload.post_brief_summary:
        brief = db.query(models.QualityAuditPostBrief).filter(models.QualityAuditPostBrief.audit_id == audit.id).first()
        if not brief:
            brief = models.QualityAuditPostBrief(amo_id=audit.amo_id, audit_id=audit.id, created_by_user_id=current_user.id, report_due_date=report_due, summary=payload.post_brief_summary, attendees_json=json.dumps(payload.attendees or []))
            db.add(brief)
        else:
            brief.summary = payload.post_brief_summary
            brief.attendees_json = json.dumps(payload.attendees or [])
            brief.report_due_date = report_due
    for recipient in {audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id} - {None}:
        _notify_user(db, recipient, f"Fieldwork completed for audit {audit.audit_ref}. Report is due by {report_due.isoformat()}.", models.QMSNotificationSeverity.ACTION_REQUIRED)
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="qms_audit", entity_id=str(audit.id), action="complete_fieldwork", after={"actual_end": actual_end.isoformat(), "report_due_date": report_due.isoformat()}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(tracker)
    return tracker


@router.post("/audits/{audit_id}/post-brief", response_model=QualityPostBriefOut, status_code=status.HTTP_201_CREATED)
def upsert_audit_post_brief(
    audit_id: UUID,
    payload: QualityPostBriefCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    settings = _get_or_create_workflow_settings(db, amo_id=str(audit.amo_id), actor_user_id=current_user.id)
    base_date = audit.actual_end or date.today()
    report_due = payload.report_due_date or (base_date + timedelta(days=settings.report_due_days))
    brief = db.query(models.QualityAuditPostBrief).filter(models.QualityAuditPostBrief.audit_id == audit.id).first()
    if not brief:
        brief = models.QualityAuditPostBrief(amo_id=audit.amo_id, audit_id=audit.id, created_by_user_id=current_user.id, report_due_date=report_due, summary=payload.summary, briefing_at=payload.briefing_at or datetime.now(timezone.utc), attendees_json=json.dumps(payload.attendees or []))
        db.add(brief)
    else:
        brief.summary = payload.summary
        brief.briefing_at = payload.briefing_at or brief.briefing_at
        brief.attendees_json = json.dumps(payload.attendees or [])
        brief.report_due_date = report_due
    tracker = _report_tracker_for_audit(db, audit=audit, report_due_date=report_due, actor_user_id=current_user.id)
    _seed_report_reminders(db, tracker, audit)
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="quality_post_brief", entity_id=str(brief.id), action="upsert", after={"report_due_date": report_due.isoformat()}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(brief)
    return _post_brief_out(brief)


@router.get("/audits/{audit_id}/post-brief", response_model=QualityPostBriefOut)
def get_audit_post_brief(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    brief = db.query(models.QualityAuditPostBrief).filter(models.QualityAuditPostBrief.audit_id == audit_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Post-brief not recorded")
    return _post_brief_out(brief)


@router.get("/audits/{audit_id}/report-tracker", response_model=QualityReportTrackerOut)
def get_audit_report_tracker(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    tracker = db.query(models.QualityAuditReportTracker).filter(models.QualityAuditReportTracker.audit_id == audit_id).first()
    if not tracker:
        raise HTTPException(status_code=404, detail="Report tracker has not been created. Complete fieldwork or create a post-brief first.")
    return tracker


@router.get("/audits/{audit_id}/metrics", response_model=QualityAuditMetricsOut)
def get_audit_metrics(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    return QualityAuditMetricsOut(**_audit_metrics(db, audit))


@router.post("/audits/{audit_id}/archive-package", response_model=QualityArchivePackageOut, status_code=status.HTTP_201_CREATED)
def create_audit_archive_package(
    audit_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    metrics = _audit_metrics(db, audit)
    if not metrics["archive_ready"]:
        raise HTTPException(status_code=409, detail="Audit is not archive-ready. Confirm report upload and close all CARs first.")
    package_ref = f"ARCH-{audit.audit_ref.replace('/', '-')}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    item = models.QualityArchivePackage(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        package_ref=package_ref,
        metrics_snapshot_json=json.dumps({k: (str(v) if isinstance(v, (UUID, date, datetime)) else v) for k, v in metrics.items()}),
        generated_by_user_id=current_user.id,
    )
    db.add(item)
    audit.retention_until = audit.retention_until or (date.today() + timedelta(days=365 * 5))
    audit_services.log_event(db, amo_id=audit.amo_id, actor_user_id=current_user.id, entity_type="quality_archive_package", entity_id=str(item.id), action="create", after={"package_ref": package_ref, "metrics": json.loads(item.metrics_snapshot_json)}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(item)
    return _archive_out(item)


@router.get("/audits/{audit_id}/archive-packages", response_model=List[QualityArchivePackageOut])
def list_audit_archive_packages(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    items = db.query(models.QualityArchivePackage).filter(models.QualityArchivePackage.audit_id == audit_id).order_by(models.QualityArchivePackage.generated_at.desc()).all()
    return [_archive_out(item) for item in items]


@router.post("/cars/{car_id}/extension-requests", response_model=QualityCARExtensionRequestOut, status_code=status.HTTP_201_CREATED)
def request_car_extension(
    car_id: UUID,
    payload: QualityCARExtensionRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = _get_car_for_amo(db, amo_id=_current_amo_id(current_user), car_id=car_id)
    _require_car_not_escalated(car)
    if current_user.id != car.assigned_to_user_id and not _current_user_can_modify_car(db, current_user, car):
        raise HTTPException(status_code=403, detail="Only the CAR assignee, lead auditor, AMO Admin, or Superuser may request an extension.")
    if car.due_date and payload.requested_due_date <= car.due_date:
        raise HTTPException(status_code=400, detail="Requested extension date must be later than the current CAR due date.")
    existing = db.query(models.QualityCARExtensionRequest).filter(models.QualityCARExtensionRequest.car_id == car.id, models.QualityCARExtensionRequest.status == "PENDING").first()
    if existing:
        raise HTTPException(status_code=409, detail="A pending extension request already exists for this CAR")
    item = models.QualityCARExtensionRequest(amo_id=car.amo_id, car_id=car.id, requested_due_date=payload.requested_due_date, reason=payload.reason, requested_by_user_id=current_user.id)
    db.add(item)
    add_car_action(db, car, models.CARActionType.COMMENT, f"Extension requested to {payload.requested_due_date.isoformat()}: {payload.reason}", current_user.id)
    for recipient in _car_escalation_recipient_ids(db, car):
        if recipient != current_user.id:
            _notify_user(db, recipient, f"Extension approval requested for CAR {car.car_number} to {payload.requested_due_date.isoformat()}.", models.QMSNotificationSeverity.ACTION_REQUIRED)
    audit_services.log_event(db, amo_id=car.amo_id, actor_user_id=current_user.id, entity_type="quality_car_extension_request", entity_id=str(item.id), action="create", after={"car_number": car.car_number, "requested_due_date": payload.requested_due_date.isoformat()}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(item)
    return item


@router.get("/cars/{car_id}/extension-requests", response_model=List[QualityCARExtensionRequestOut])
def list_car_extension_requests(
    car_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = _get_car_for_amo(db, amo_id=_current_amo_id(current_user), car_id=car_id)
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)
    return db.query(models.QualityCARExtensionRequest).filter(models.QualityCARExtensionRequest.car_id == car.id).order_by(models.QualityCARExtensionRequest.created_at.desc()).all()


@router.post("/cars/{car_id}/extension-requests/{extension_id}/forward-to-qm", response_model=QualityCARExtensionRequestOut)
def forward_car_extension_to_qm(
    car_id: UUID,
    extension_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = _get_car_for_amo(db, amo_id=_current_amo_id(current_user), car_id=car_id)
    _require_car_not_escalated(car)
    _require_car_review_access(db, current_user, car)
    item = db.query(models.QualityCARExtensionRequest).filter(models.QualityCARExtensionRequest.id == extension_id, models.QualityCARExtensionRequest.car_id == car.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Extension request not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending extension requests can be forwarded")
    recipients = _quality_manager_recipient_ids(db, car.amo_id)
    if not recipients:
        raise HTTPException(status_code=404, detail="No active Quality Manager found for this AMO")
    for recipient in recipients:
        if recipient != current_user.id:
            _notify_user(db, recipient, f"Deferral review requested for CAR {car.car_number}: extension to {item.requested_due_date.isoformat()}.", models.QMSNotificationSeverity.ACTION_REQUIRED)
    add_car_action(db, car, models.CARActionType.COMMENT, f"Deferral request forwarded to Quality Manager for review: {item.requested_due_date.isoformat()}", current_user.id)
    audit_services.log_event(db, amo_id=car.amo_id, actor_user_id=current_user.id, entity_type="quality_car_extension_request", entity_id=str(item.id), action="forward_to_qm", after={"car_number": car.car_number, "requested_due_date": item.requested_due_date.isoformat()}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(item)
    return item


@router.post("/cars/{car_id}/extension-requests/{extension_id}/review", response_model=QualityCARExtensionRequestOut)
def review_car_extension_request(
    car_id: UUID,
    extension_id: UUID,
    payload: QualityCARExtensionReview,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = _get_car_for_amo(db, amo_id=_current_amo_id(current_user), car_id=car_id)
    _require_car_not_escalated(car)
    _require_car_review_access(db, current_user, car)
    item = db.query(models.QualityCARExtensionRequest).filter(models.QualityCARExtensionRequest.id == extension_id, models.QualityCARExtensionRequest.car_id == car.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Extension request not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="Extension request has already been reviewed")
    item.status = "APPROVED" if payload.approved else "REJECTED"
    item.review_note = payload.review_note
    item.reviewed_by_user_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    if payload.approved:
        old_due = car.due_date
        car.due_date = item.requested_due_date
        car.target_closure_date = item.requested_due_date
        _seed_car_reminders(db, car)
        action_message = f"Extension approved from {old_due} to {item.requested_due_date.isoformat()}"
    else:
        action_message = f"Extension rejected for requested date {item.requested_due_date.isoformat()}"
    add_car_action(db, car, models.CARActionType.STATUS_CHANGE, action_message, current_user.id)
    _notify_user(db, item.requested_by_user_id, f"{action_message} for CAR {car.car_number}.", models.QMSNotificationSeverity.ACTION_REQUIRED)
    audit_services.log_event(db, amo_id=car.amo_id, actor_user_id=current_user.id, entity_type="quality_car_extension_request", entity_id=str(item.id), action="approve" if payload.approved else "reject", after={"status": item.status, "car_due_date": str(car.due_date)}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(item)
    return item


@router.get("/cars/{car_id}/reminder-plan", response_model=List[QualityReminderMilestoneOut])
def get_car_reminder_plan(
    car_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = _get_car_for_amo(db, amo_id=_current_amo_id(current_user), car_id=car_id)
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)
    reminders = _seed_car_reminders(db, car)
    db.commit()
    if not reminders:
        reminders = db.query(models.QualityReminderMilestone).filter(models.QualityReminderMilestone.entity_type == "quality_car", models.QualityReminderMilestone.entity_id == str(car.id)).all()
    return sorted(reminders, key=lambda row: row.scheduled_for)


@router.post("/reminders/run")
def run_quality_workflow_reminders(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not _is_quality_admin(current_user):
        raise HTTPException(status_code=403, detail="Only Quality Managers or AMO Admins can run reminder dispatch")
    amo_id = str(_current_amo_id(current_user))
    now = datetime.now(timezone.utc)
    due_reminders = (
        db.query(models.QualityReminderMilestone)
        .filter(models.QualityReminderMilestone.amo_id == amo_id, models.QualityReminderMilestone.sent_at.is_(None), models.QualityReminderMilestone.scheduled_for <= now)
        .order_by(models.QualityReminderMilestone.scheduled_for.asc())
        .limit(500)
        .all()
    )
    sent = 0
    escalated = 0
    settings = _get_or_create_workflow_settings(db, amo_id=amo_id, actor_user_id=current_user.id)
    for reminder in due_reminders:
        severity = models.QMSNotificationSeverity.WARNING if reminder.severity == "WARNING" else models.QMSNotificationSeverity.ACTION_REQUIRED
        _notify_user(db, reminder.recipient_user_id, reminder.message, severity)
        reminder.sent_at = now
        sent += 1
        if settings.auto_escalation_enabled and reminder.due_date and reminder.due_date < date.today():
            reminder.escalated_at = now
            escalated += 1
            if reminder.entity_type == "quality_car":
                car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == UUID(str(reminder.entity_id))).first()
                if car and car.status != models.CARStatus.CLOSED:
                    car.status = models.CARStatus.ESCALATED
                    car.escalated_at = car.escalated_at or now
                    for recipient in _car_escalation_recipient_ids(db, car):
                        _notify_user(db, recipient, f"Escalation: CAR {car.car_number} is overdue against due date {reminder.due_date.isoformat()}.", models.QMSNotificationSeverity.WARNING)
    audit_services.log_event(db, amo_id=amo_id, actor_user_id=current_user.id, entity_type="quality_reminders", entity_id=amo_id, action="dispatch_due", after={"sent": sent, "escalated": escalated}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=escalated > 0)
    db.commit()
    return {"sent": sent, "escalated": escalated, "checked_at": now.isoformat()}


# -----------------------------
# Documents
# -----------------------------
@router.post("/qms/documents", response_model=QMSDocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: QMSDocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _current_amo_id(current_user)
    doc = models.QMSDocument(
        amo_id=amo_id,
        domain=payload.domain,
        doc_type=payload.doc_type,
        doc_code=payload.doc_code.strip(),
        title=payload.title.strip(),
        description=payload.description,
        restricted_access=payload.restricted_access,
        created_by_user_id=get_actor(),
        updated_by_user_id=get_actor(),
    )
    db.add(doc)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_document",
        entity_id=str(doc.id),
        action="create",
        after={"doc_code": doc.doc_code, "title": doc.title, "status": doc.status.value},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/qms/documents", response_model=List[QMSDocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
    domain: Optional[QMSDomain] = None,
    doc_type: Optional[models.QMSDocType] = None,
    status_: Optional[models.QMSDocStatus] = None,
    q: Optional[str] = None,
):
    qs = db.query(models.QMSDocument).filter(models.QMSDocument.amo_id == _current_amo_id(current_user))

    if domain:
        qs = qs.filter(models.QMSDocument.domain == domain)
    if doc_type:
        qs = qs.filter(models.QMSDocument.doc_type == doc_type)
    if status_:
        qs = qs.filter(models.QMSDocument.status == status_)
    if q:
        like = f"%{q.strip()}%"
        qs = qs.filter((models.QMSDocument.title.ilike(like)) | (models.QMSDocument.doc_code.ilike(like)))

    return qs.order_by(models.QMSDocument.updated_at.desc()).all()


@router.get("/qms/documents/{doc_id}", response_model=QMSDocumentOut)
def get_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == doc_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/qms/documents/{doc_id}", response_model=QMSDocumentOut)
def update_document(
    doc_id: UUID,
    payload: QMSDocumentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _enforce_aerodoc_control(current_user)
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == doc_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    before = {"status": doc.status.value, "title": doc.title, "doc_code": doc.doc_code}

    if payload.title is not None:
        doc.title = payload.title.strip()
    if payload.description is not None:
        doc.description = payload.description
    if payload.restricted_access is not None:
        doc.restricted_access = payload.restricted_access
    if payload.status is not None:
        doc.status = payload.status

    doc.updated_by_user_id = get_actor()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_document",
        entity_id=str(doc.id),
        action="update",
        before=before,
        after={"status": doc.status.value, "title": doc.title},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/qms/documents/{doc_id}/revisions", response_model=QMSDocumentRevisionOut, status_code=status.HTTP_201_CREATED)
def add_revision(
    doc_id: UUID,
    payload: QMSDocumentRevisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _enforce_aerodoc_control(current_user)
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == doc_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.is_temporary and not payload.temporary_expires_on:
        raise HTTPException(status_code=400, detail="temporary_expires_on is required for temporary revisions")

    rev = models.QMSDocumentRevision(
        amo_id=doc.amo_id,
        document_id=doc.id,
        issue_no=payload.issue_no,
        rev_no=payload.rev_no,
        issued_date=payload.issued_date,
        entered_date=payload.entered_date,
        pages_affected=payload.pages_affected,
        tracking_serial=payload.tracking_serial,
        change_summary=payload.change_summary,
        is_temporary=payload.is_temporary,
        temporary_expires_on=payload.temporary_expires_on,
        file_ref=payload.file_ref,
        version_semver=payload.version_semver,
        lifecycle_status=payload.lifecycle_status,
        sha256=payload.sha256,
        primary_storage_provider=payload.primary_storage_provider,
        primary_storage_key=payload.primary_storage_key,
        primary_storage_etag=payload.primary_storage_etag,
        byte_size=payload.byte_size,
        mime_type=payload.mime_type,
        approved_by_authority=payload.approved_by_authority,
        authority_ref=payload.authority_ref,
        approved_by_user_id=payload.approved_by_user_id,
        approved_at=payload.approved_at,
        created_by_user_id=get_actor(),
    )
    db.add(rev)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_document_revision",
        entity_id=str(rev.id),
        action="create",
        after={"doc_id": str(doc.id), "issue_no": rev.issue_no, "rev_no": rev.rev_no},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(rev)
    return rev


@router.get("/qms/documents/{doc_id}/revisions", response_model=List[QMSDocumentRevisionOut])
def list_revisions(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return (
        db.query(models.QMSDocumentRevision)
        .filter(
            models.QMSDocumentRevision.document_id == doc_id,
            models.QMSDocumentRevision.amo_id == _current_amo_id(current_user),
        )
        .order_by(models.QMSDocumentRevision.created_at.desc())
        .all()
    )


@router.post("/qms/documents/{doc_id}/publish/{revision_id}", response_model=QMSDocumentOut)
def publish_revision(
    doc_id: UUID,
    revision_id: UUID,
    payload: QMSPublishRevision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == doc_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rev = (
        db.query(models.QMSDocumentRevision)
        .filter(
            models.QMSDocumentRevision.id == revision_id,
            models.QMSDocumentRevision.document_id == doc_id,
            models.QMSDocumentRevision.amo_id == _current_amo_id(current_user),
        )
        .first()
    )
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")

    before_status = doc.status.value
    doc.current_issue_no = rev.issue_no
    doc.current_rev_no = rev.rev_no
    doc.effective_date = payload.effective_date
    doc.current_file_ref = payload.current_file_ref or rev.file_ref
    doc.status = models.QMSDocStatus.ACTIVE
    doc.updated_by_user_id = get_actor()

    try:
        apply_transition(
            db,
            actor_user_id=current_user.id,
            entity_type="qms_document",
            entity_id=str(doc.id),
            from_state=before_status,
            to_state=doc.status.value,
            before_obj={
                "status": before_status,
                "amo_id": current_user.amo_id,
            },
            after_obj={
                "status": doc.status.value,
                "current_issue_no": doc.current_issue_no,
                "current_rev_no": doc.current_rev_no,
                "approved_by_authority": rev.approved_by_authority,
                "authority_ref": rev.authority_ref,
                "approved_by_user_id": rev.approved_by_user_id,
                "approved_at": str(rev.approved_at) if rev.approved_at else None,
                "amo_id": current_user.amo_id,
            },
            correlation_id=str(uuid.uuid4()),
            critical=True,
        )
    except TransitionError as exc:
        return JSONResponse(status_code=400, content={"error": exc.code, "detail": exc.detail})

    ack_distributions = (
        db.query(models.QMSDocumentDistribution)
        .filter(
            models.QMSDocumentDistribution.document_id == doc.id,
            models.QMSDocumentDistribution.requires_ack.is_(True),
            models.QMSDocumentDistribution.holder_user_id.is_not(None),
        )
        .all()
    )
    for dist in ack_distributions:
        task_services.create_task(
            db,
            amo_id=current_user.amo_id,
            title="Acknowledge document distribution",
            description=f"Please acknowledge receipt of document {doc.doc_code}.",
            owner_user_id=dist.holder_user_id,
            due_at=_date_to_datetime(payload.effective_date),
            entity_type="qms_document_distribution",
            entity_id=str(dist.id),
            priority=3,
        )
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/qms/distributions", response_model=QMSDistributionOut, status_code=status.HTTP_201_CREATED)
def create_distribution(
    payload: QMSDistributionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == payload.document_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    dist = models.QMSDocumentDistribution(
        amo_id=doc.amo_id,
        document_id=payload.document_id,
        revision_id=payload.revision_id,
        copy_number=payload.copy_number,
        holder_label=payload.holder_label.strip(),
        holder_user_id=payload.holder_user_id,
        dist_format=payload.dist_format,
        requires_ack=payload.requires_ack,
    )
    db.add(dist)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_document_distribution",
        entity_id=str(dist.id),
        action="create",
        after={
            "document_id": str(dist.document_id),
            "revision_id": str(dist.revision_id) if dist.revision_id else None,
            "holder_label": dist.holder_label,
            "requires_ack": dist.requires_ack,
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(dist)
    return dist


@router.get("/qms/distributions", response_model=List[QMSDistributionOut])
def list_distributions(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
    document_id: Optional[UUID] = None,
    holder_user_id: Optional[str] = None,
    outstanding_only: bool = False,
):
    qs = db.query(models.QMSDocumentDistribution).filter(
        models.QMSDocumentDistribution.amo_id == _current_amo_id(current_user)
    )
    if document_id:
        qs = qs.filter(models.QMSDocumentDistribution.document_id == document_id)
    if holder_user_id:
        qs = qs.filter(models.QMSDocumentDistribution.holder_user_id == holder_user_id)
    if outstanding_only:
        qs = qs.filter(
            models.QMSDocumentDistribution.requires_ack.is_(True),
            models.QMSDocumentDistribution.acked_at.is_(None),
        )
    return qs.order_by(models.QMSDocumentDistribution.distributed_at.desc()).all()


@router.post("/qms/distributions/{dist_id}/ack", response_model=QMSDistributionOut)
def acknowledge_distribution(
    dist_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    dist = db.query(models.QMSDocumentDistribution).filter(models.QMSDocumentDistribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution record not found")
    if not dist.requires_ack:
        return dist
    if dist.acked_at:
        return dist

    dist.acked_at = func.now()
    dist.acked_by_user_id = get_actor()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_document_distribution",
        entity_id=str(dist.id),
        action="acknowledge",
        after={"acked_at": str(dist.acked_at)},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(dist)
    return dist


# -----------------------------
# Manual Change Requests
# -----------------------------
@router.post("/qms/change-requests", response_model=QMSChangeRequestOut, status_code=status.HTTP_201_CREATED)
def create_change_request(payload: QMSChangeRequestCreate, db: Session = Depends(get_db)):
    cr = models.QMSManualChangeRequest(
        domain=payload.domain,
        petitioner_name=payload.petitioner_name.strip(),
        petitioner_email=payload.petitioner_email,
        petitioner_phone=payload.petitioner_phone,
        petitioner_department=payload.petitioner_department,
        manual_title=payload.manual_title.strip(),
        manual_reference=payload.manual_reference,
        manual_copy_no=payload.manual_copy_no,
        manual_rev=payload.manual_rev,
        manual_location=payload.manual_location,
        media_source=payload.media_source,
        remarks=payload.remarks,
        change_request_text=payload.change_request_text,
        created_by_user_id=get_actor(),
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


@router.get("/qms/change-requests", response_model=List[QMSChangeRequestOut])
def list_change_requests(db: Session = Depends(get_db), domain: Optional[QMSDomain] = None):
    qs = db.query(models.QMSManualChangeRequest)
    if domain:
        qs = qs.filter(models.QMSManualChangeRequest.domain == domain)
    return qs.order_by(models.QMSManualChangeRequest.submitted_at.desc()).all()


@router.patch("/qms/change-requests/{cr_id}", response_model=QMSChangeRequestOut)
def update_change_request(cr_id: UUID, payload: QMSChangeRequestUpdate, db: Session = Depends(get_db)):
    cr = db.query(models.QMSManualChangeRequest).filter(models.QMSManualChangeRequest.id == cr_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Change request not found")

    for field in ("status", "manual_owner_decision", "qa_decision", "librarian_decision", "review_feedback"):
        val = getattr(payload, field)
        if val is not None:
            setattr(cr, field, val)

    db.commit()
    db.refresh(cr)
    return cr



# -----------------------------
# Audit scopes and reference families
# -----------------------------
@router.get("/audits/scopes", response_model=List[QMSAuditScopeOut])
def list_audit_scopes(
    active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _current_amo_id(current_user)
    ensure_qms_audit_scope_schema(db)
    query = db.query(models.QMSAuditScope).filter(models.QMSAuditScope.amo_id == amo_id)
    if active is not None:
        query = query.filter(models.QMSAuditScope.is_active == active)
    return query.order_by(models.QMSAuditScope.sort_order.asc(), models.QMSAuditScope.code.asc()).all()


@router.post("/audits/scopes", response_model=QMSAuditScopeOut, status_code=status.HTTP_201_CREATED)
def create_audit_scope(
    payload: QMSAuditScopeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_scope_admin(current_user)
    amo_id = _current_amo_id(current_user)
    ensure_qms_audit_scope_schema(db)
    code = _normalize_scope_code(payload.code)
    if not code:
        raise HTTPException(status_code=400, detail="Audit scope code is required")
    exists = db.query(models.QMSAuditScope).filter(models.QMSAuditScope.amo_id == amo_id, models.QMSAuditScope.code == code).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"Audit scope {code} already exists for this tenant")
    scope = models.QMSAuditScope(
        amo_id=amo_id,
        code=code,
        name=payload.name.strip(),
        description=payload.description,
        party_level=payload.party_level,
        default_kind=payload.default_kind,
        is_active=payload.is_active,
        is_system_default=False,
        sort_order=payload.sort_order,
        created_by_user_id=current_user.id,
    )
    db.add(scope)
    db.flush()
    audit_services.log_event(db, amo_id=amo_id, actor_user_id=current_user.id, entity_type="qms_audit_scope", entity_id=str(scope.id), action="create", after={"code": scope.code, "name": scope.name, "party_level": scope.party_level}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(scope)
    return scope


@router.patch("/audits/scopes/{scope_id}", response_model=QMSAuditScopeOut)
def update_audit_scope(
    scope_id: UUID,
    payload: QMSAuditScopeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_scope_admin(current_user)
    amo_id = _current_amo_id(current_user)
    ensure_qms_audit_scope_schema(db)
    scope = db.query(models.QMSAuditScope).filter(models.QMSAuditScope.id == scope_id, models.QMSAuditScope.amo_id == amo_id).first()
    if not scope:
        raise HTTPException(status_code=404, detail="Audit scope not found")
    before = {"code": scope.code, "name": scope.name, "party_level": scope.party_level, "default_kind": getattr(scope.default_kind, "value", scope.default_kind), "is_active": scope.is_active}
    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] is not None:
        next_code = _normalize_scope_code(changes["code"])
        if not next_code:
            raise HTTPException(status_code=400, detail="Audit scope code is required")
        duplicate = db.query(models.QMSAuditScope).filter(models.QMSAuditScope.amo_id == amo_id, models.QMSAuditScope.code == next_code, models.QMSAuditScope.id != scope.id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail=f"Audit scope {next_code} already exists for this tenant")
        # Existing audit references are immutable records. New schedules/audits use the new code.
        scope.code = next_code
    if "name" in changes and changes["name"] is not None:
        scope.name = changes["name"].strip()
    if "description" in changes:
        scope.description = changes["description"]
    if "party_level" in changes and changes["party_level"] is not None:
        scope.party_level = changes["party_level"]
    if "default_kind" in changes and changes["default_kind"] is not None:
        scope.default_kind = changes["default_kind"]
    if "is_active" in changes and changes["is_active"] is not None:
        scope.is_active = changes["is_active"]
    if "sort_order" in changes and changes["sort_order"] is not None:
        scope.sort_order = changes["sort_order"]
    audit_services.log_event(db, amo_id=amo_id, actor_user_id=current_user.id, entity_type="qms_audit_scope", entity_id=str(scope.id), action="update", before=before, after={"code": scope.code, "name": scope.name, "party_level": scope.party_level, "default_kind": getattr(scope.default_kind, "value", scope.default_kind), "is_active": scope.is_active}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request), critical=True)
    db.commit()
    db.refresh(scope)
    return scope


# -----------------------------
# Audits / Findings / CAP
# -----------------------------
@router.post("/audits", response_model=QMSAuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(
    payload: QMSAuditCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    ensure_qms_audit_reference_schema(db)
    _require_quality_scheduler(current_user)
    scoped_amo_id = _current_amo_id(current_user)
    _validate_one_calendar_year(start=payload.planned_start, end=payload.planned_end)
    audit_scope = _resolve_audit_scope(
        db,
        amo_id=scoped_amo_id,
        audit_scope_id=payload.audit_scope_id,
        audit_scope_code=payload.audit_scope_code,
        kind=payload.kind,
    )
    audit_ref, unit_code, ref_year, ref_sequence = _generate_audit_reference(
        db,
        amo_id=scoped_amo_id,
        target_date=payload.planned_start,
        audit_scope_code=audit_scope.code,
    )
    external_auditees = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (payload.external_auditees or [])]
    external_auditee_name, external_auditee_email = _external_auditee_summary(external_auditees)
    derived_auditee = payload.auditee or (external_auditee_name if payload.kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY} else None)
    derived_email = payload.auditee_email or (external_auditee_email if payload.kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY} else None)
    audit = models.QMSAudit(
        amo_id=scoped_amo_id,
        domain=payload.domain,
        kind=payload.kind,
        audit_ref=audit_ref,
        audit_scope_id=audit_scope.id,
        audit_scope_code=audit_scope.code,
        reference_family="QAR",
        unit_code=unit_code,
        ref_year=ref_year,
        ref_sequence=ref_sequence,
        title=payload.title.strip(),
        scope=payload.scope,
        criteria=payload.criteria,
        auditee=derived_auditee,
        auditee_email=derived_email,
        auditee_user_id=payload.auditee_user_id,
        external_auditees_json=_serialize_external_auditees(external_auditees),
        lead_auditor_user_id=payload.lead_auditor_user_id,
        observer_auditor_user_id=payload.observer_auditor_user_id,
        assistant_auditor_user_id=payload.assistant_auditor_user_id,
        notify_auditors=payload.notify_auditors,
        notify_auditees=payload.notify_auditees,
        reminder_interval_days=payload.reminder_interval_days,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        created_by_user_id=get_actor(),
    )
    db.add(audit)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="create",
        after={"audit_ref": audit.audit_ref, "status": audit.status.value, "title": audit.title},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    _dispatch_audit_notice(db, audit=audit, amo_id=str(current_user.amo_id))
    db.commit()
    db.refresh(audit)
    return _serialize_audit(audit, db)


@router.get("/audits", response_model=List[QMSAuditOut])
def list_audits(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = None,
    status_: Optional[models.QMSAuditStatus] = None,
    kind: Optional[models.QMSAuditKind] = None,
    limit: int = Query(default=250, ge=1, le=1000),
    current_user: account_models.User = Depends(get_current_active_user),
):
    ensure_qms_audit_reference_schema(db)
    qs = db.query(models.QMSAudit).filter(models.QMSAudit.amo_id == _current_amo_id(current_user))
    if domain:
        qs = qs.filter(models.QMSAudit.domain == domain)
    if status_:
        qs = qs.filter(models.QMSAudit.status == status_)
    if kind:
        qs = qs.filter(models.QMSAudit.kind == kind)
    audits = qs.order_by(models.QMSAudit.planned_start.desc().nullslast(), models.QMSAudit.created_at.desc()).limit(limit).all()
    return [_serialize_audit(audit, db) for audit in audits]


@router.get("/audits/findings", response_model=List[QMSFindingOut])
def list_findings_bulk(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = None,
    audit_ids: Optional[List[UUID]] = Query(default=None),
    current_user: account_models.User = Depends(get_current_active_user),
):
    scoped_amo_id = _current_amo_id(current_user)
    qs = (
        db.query(models.QMSAuditFinding)
        .join(models.QMSAudit, models.QMSAudit.id == models.QMSAuditFinding.audit_id)
        .filter(models.QMSAudit.amo_id == scoped_amo_id)
    )
    if domain:
        qs = qs.filter(models.QMSAudit.domain == domain)
    if audit_ids:
        qs = qs.filter(models.QMSAuditFinding.audit_id.in_(audit_ids))
    return (
        qs.order_by(models.QMSAuditFinding.created_at.desc())
        .all()
    )


@router.get("/audits/register", response_model=QMSAuditRegisterResponse)
def get_audit_register(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = None,
    current_user: account_models.User = Depends(get_current_active_user),
):
    ensure_qms_audit_reference_schema(db)
    scoped_amo_id = _current_amo_id(current_user)
    audit_query = db.query(models.QMSAudit).filter(models.QMSAudit.amo_id == scoped_amo_id)
    if domain:
        audit_query = audit_query.filter(models.QMSAudit.domain == domain)
    audits = audit_query.order_by(models.QMSAudit.created_at.desc()).all()
    audit_ids = [audit.id for audit in audits]
    if not audit_ids:
        return QMSAuditRegisterResponse(rows=[])

    findings = (
        db.query(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.audit_id.in_(audit_ids))
        .order_by(models.QMSAuditFinding.created_at.desc())
        .all()
    )
    finding_ids = [finding.id for finding in findings]
    cars = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.amo_id == scoped_amo_id)
        .filter(models.CorrectiveActionRequest.finding_id.in_(finding_ids) if finding_ids else False)
        .order_by(models.CorrectiveActionRequest.created_at.desc())
        .all()
    )

    audit_by_id = {audit.id: audit for audit in audits}
    cars_by_finding: dict[UUID, list[models.CorrectiveActionRequest]] = {}
    for car in cars:
        if not car.finding_id:
            continue
        cars_by_finding.setdefault(car.finding_id, []).append(car)

    rows = [
        QMSAuditRegisterRowOut(
            audit=audit_by_id[finding.audit_id],
            finding=finding,
            linked_cars=cars_by_finding.get(finding.id, []),
        )
        for finding in findings
        if finding.audit_id in audit_by_id
    ]
    return QMSAuditRegisterResponse(rows=rows)


@router.get("/audits/schedules", response_model=List[QMSAuditScheduleOut])
def list_audit_schedules(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = None,
    active: Optional[bool] = None,
    current_user: account_models.User = Depends(get_current_active_user),
):
    scoped_amo_id = _current_amo_id(current_user)
    qs = db.query(models.QMSAuditSchedule).filter(models.QMSAuditSchedule.amo_id == scoped_amo_id)
    if domain:
        qs = qs.filter(models.QMSAuditSchedule.domain == domain)
    if active is not None:
        qs = qs.filter(models.QMSAuditSchedule.is_active.is_(active))
    schedules = qs.order_by(models.QMSAuditSchedule.next_due_date.asc()).all()
    return [_serialize_schedule(schedule) for schedule in schedules]


@router.get("/audits/personnel/options", response_model=List[QMSPersonOptionOut])
def list_audit_personnel_options(
    search: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _current_amo_id(current_user)
    if not amo_id:
        raise HTTPException(status_code=400, detail="AMO context is required")

    qs = (
        db.query(account_models.User)
        .filter(account_models.User.amo_id == amo_id)
        .filter(account_models.User.is_active.is_(True))
    )
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

    results: list[QMSPersonOptionOut] = []
    for user in users:
        full_name = (getattr(user, "full_name", None) or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or getattr(user, "email", None) or getattr(user, "staff_code", None) or str(user.id))
        role_value = getattr(user, "role", None)
        role_value = getattr(role_value, "value", role_value)
        results.append(
            QMSPersonOptionOut(
                id=str(user.id),
                staff_code=getattr(user, "staff_code", None),
                full_name=full_name,
                email=getattr(user, "email", None),
                role=str(role_value) if role_value else None,
                department_id=getattr(user, "department_id", None),
                position_title=getattr(user, "position_title", None),
            )
        )
    return results


@router.post("/audits/schedules", response_model=QMSAuditScheduleOut, status_code=status.HTTP_201_CREATED)
def create_audit_schedule(
    payload: QMSAuditScheduleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    # Heal legacy table width and audit-scope columns before schedule creation.
    # This prevents PostgreSQL from rejecting BI_ANNUAL and other full enum
    # values on older databases whose frequency column was created as VARCHAR(7).
    ensure_qms_audit_scope_schema(db)
    scoped_amo_id = _current_amo_id(current_user)
    _validate_one_calendar_year(start=payload.next_due_date, end=None, duration_days=payload.duration_days)
    audit_scope = _resolve_audit_scope(
        db,
        amo_id=scoped_amo_id,
        audit_scope_id=payload.audit_scope_id,
        audit_scope_code=payload.audit_scope_code,
        kind=payload.kind,
    )
    external_auditees = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (payload.external_auditees or [])]
    external_auditee_name, external_auditee_email = _external_auditee_summary(external_auditees)
    derived_auditee = payload.auditee or (external_auditee_name if payload.kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY} else None)
    derived_email = payload.auditee_email or (external_auditee_email if payload.kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY} else None)
    schedule = models.QMSAuditSchedule(
        amo_id=scoped_amo_id,
        domain=payload.domain,
        kind=payload.kind,
        frequency=payload.frequency,
        title=payload.title.strip(),
        audit_scope_id=audit_scope.id,
        audit_scope_code=audit_scope.code,
        scope=payload.scope,
        criteria=payload.criteria,
        auditee=derived_auditee,
        auditee_email=derived_email,
        auditee_user_id=payload.auditee_user_id,
        external_auditees_json=_serialize_external_auditees(external_auditees),
        lead_auditor_user_id=payload.lead_auditor_user_id,
        observer_auditor_user_id=payload.observer_auditor_user_id,
        assistant_auditor_user_id=payload.assistant_auditor_user_id,
        notify_auditors=payload.notify_auditors,
        notify_auditees=payload.notify_auditees,
        reminder_interval_days=payload.reminder_interval_days,
        duration_days=payload.duration_days,
        next_due_date=payload.next_due_date,
        created_by_user_id=get_actor(),
    )
    db.add(schedule)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="create",
        after={
            "frequency": schedule.frequency.value,
            "next_due_date": str(schedule.next_due_date),
            "title": schedule.title,
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    _dispatch_schedule_notice(db, schedule=schedule, amo_id=str(current_user.amo_id))
    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(schedule)


@router.patch("/audits/schedules/{schedule_id}", response_model=QMSAuditScheduleOut)
def update_audit_schedule(
    schedule_id: UUID,
    payload: QMSAuditScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    ensure_qms_audit_scope_schema(db)
    scoped_amo_id = _current_amo_id(current_user)
    schedule = (
        db.query(models.QMSAuditSchedule)
        .filter(models.QMSAuditSchedule.id == schedule_id)
        .filter(models.QMSAuditSchedule.amo_id == scoped_amo_id)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    if not _external_audit_is_editable(schedule.kind):
        raise HTTPException(status_code=403, detail="Internal and first-party audit schedules are locked after creation. Create a new schedule or use the scope setup page for future changes.")

    before = {
        "title": schedule.title,
        "kind": schedule.kind.value,
        "audit_scope_code": schedule.audit_scope_code,
        "frequency": schedule.frequency.value,
        "next_due_date": str(schedule.next_due_date),
        "lead_auditor_user_id": schedule.lead_auditor_user_id,
        "auditee_user_id": schedule.auditee_user_id,
        "auditee_email": schedule.auditee_email,
        "is_active": schedule.is_active,
        "notify_auditors": schedule.notify_auditors,
        "notify_auditees": schedule.notify_auditees,
        "reminder_interval_days": schedule.reminder_interval_days,
    }

    changes = payload.model_dump(exclude_unset=True)
    next_start = changes.get("next_due_date", schedule.next_due_date)
    next_duration = changes.get("duration_days", schedule.duration_days)
    _validate_one_calendar_year(start=next_start, end=None, duration_days=next_duration)
    if "audit_scope_id" in changes or "audit_scope_code" in changes or "kind" in changes:
        resolved_scope = _resolve_audit_scope(
            db,
            amo_id=scoped_amo_id,
            audit_scope_id=changes.get("audit_scope_id") or schedule.audit_scope_id,
            audit_scope_code=changes.get("audit_scope_code") or schedule.audit_scope_code,
            kind=changes.get("kind") or schedule.kind,
        )
        schedule.audit_scope_id = resolved_scope.id
        schedule.audit_scope_code = resolved_scope.code
    if "title" in changes:
        schedule.title = (changes["title"] or "").strip()
    if "kind" in changes and changes["kind"] is not None:
        schedule.kind = changes["kind"]
    if "frequency" in changes and changes["frequency"] is not None:
        schedule.frequency = changes["frequency"]
    if "scope" in changes:
        schedule.scope = changes["scope"]
    if "criteria" in changes:
        schedule.criteria = changes["criteria"]
    if "auditee" in changes:
        schedule.auditee = changes["auditee"]
    if "auditee_email" in changes:
        schedule.auditee_email = changes["auditee_email"]
    if "auditee_user_id" in changes:
        schedule.auditee_user_id = changes["auditee_user_id"]
    if "lead_auditor_user_id" in changes:
        schedule.lead_auditor_user_id = changes["lead_auditor_user_id"]
    if "observer_auditor_user_id" in changes:
        schedule.observer_auditor_user_id = changes["observer_auditor_user_id"]
    if "assistant_auditor_user_id" in changes:
        schedule.assistant_auditor_user_id = changes["assistant_auditor_user_id"]
    if "notify_auditors" in changes and changes["notify_auditors"] is not None:
        schedule.notify_auditors = changes["notify_auditors"]
    if "notify_auditees" in changes and changes["notify_auditees"] is not None:
        schedule.notify_auditees = changes["notify_auditees"]
    if "reminder_interval_days" in changes and changes["reminder_interval_days"] is not None:
        schedule.reminder_interval_days = changes["reminder_interval_days"]
    if "duration_days" in changes and changes["duration_days"] is not None:
        schedule.duration_days = changes["duration_days"]
    if "next_due_date" in changes and changes["next_due_date"] is not None:
        schedule.next_due_date = changes["next_due_date"]
    if "is_active" in changes and changes["is_active"] is not None:
        schedule.is_active = changes["is_active"]

    if "external_auditees" in changes:
        external_auditees = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (changes.get("external_auditees") or [])]
        schedule.external_auditees_json = _serialize_external_auditees(external_auditees)
        external_auditee_name, external_auditee_email = _external_auditee_summary(external_auditees)
        if schedule.kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY}:
            schedule.auditee = changes.get("auditee") if "auditee" in changes else (schedule.auditee or external_auditee_name)
            schedule.auditee_email = changes.get("auditee_email") if "auditee_email" in changes else (schedule.auditee_email or external_auditee_email)

    if schedule.kind in {models.QMSAuditKind.EXTERNAL, models.QMSAuditKind.THIRD_PARTY} and schedule.external_auditees:
        external_auditee_name, external_auditee_email = _external_auditee_summary(schedule.external_auditees)
        if not schedule.auditee:
            schedule.auditee = external_auditee_name
        if not schedule.auditee_email:
            schedule.auditee_email = external_auditee_email

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="update",
        before=before,
        after={
            "title": schedule.title,
            "kind": schedule.kind.value,
            "audit_scope_code": schedule.audit_scope_code,
            "frequency": schedule.frequency.value,
            "next_due_date": str(schedule.next_due_date),
            "lead_auditor_user_id": schedule.lead_auditor_user_id,
            "is_active": schedule.is_active,
            "notify_auditors": schedule.notify_auditors,
            "notify_auditees": schedule.notify_auditees,
            "reminder_interval_days": schedule.reminder_interval_days,
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )

    if (
        before["lead_auditor_user_id"] != schedule.lead_auditor_user_id
        or before["auditee_user_id"] != schedule.auditee_user_id
        or before["auditee_email"] != schedule.auditee_email
        or before["next_due_date"] != str(schedule.next_due_date)
        or before["title"] != schedule.title
        or before["notify_auditors"] != schedule.notify_auditors
        or before["notify_auditees"] != schedule.notify_auditees
        or before["reminder_interval_days"] != schedule.reminder_interval_days
    ):
        _dispatch_schedule_notice(db, schedule=schedule, amo_id=str(current_user.amo_id))

    db.commit()
    db.refresh(schedule)
    return _serialize_schedule(schedule)


@router.delete("/audits/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audit_schedule(
    schedule_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    schedule = (
        db.query(models.QMSAuditSchedule)
        .filter(models.QMSAuditSchedule.id == schedule_id)
        .filter(models.QMSAuditSchedule.amo_id == _current_amo_id(current_user))
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Audit schedule not found")

    before = {
        "title": schedule.title,
        "frequency": schedule.frequency.value,
        "next_due_date": str(schedule.next_due_date),
    }

    db.delete(schedule)
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule_id),
        action="delete",
        before=before,
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.commit()
    return None


@router.post("/audits/schedules/{schedule_id}/run", response_model=QMSAuditOut)
def run_audit_schedule(
    schedule_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    scoped_amo_id = _current_amo_id(current_user)
    schedule = (
        db.query(models.QMSAuditSchedule)
        .filter(models.QMSAuditSchedule.id == schedule_id)
        .filter(models.QMSAuditSchedule.amo_id == scoped_amo_id)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Audit schedule not found")
    if not schedule.is_active:
        raise HTTPException(status_code=400, detail="Audit schedule is inactive")

    planned_start = schedule.next_due_date
    planned_end = planned_start + timedelta(days=max(schedule.duration_days, 1) - 1)
    _validate_one_calendar_year(start=planned_start, end=planned_end)
    audit_scope_code = schedule.audit_scope_code or _scope_default_code_for_kind(schedule.kind)
    audit_ref, unit_code, ref_year, ref_sequence = _generate_audit_reference(
        db,
        amo_id=scoped_amo_id,
        target_date=planned_start,
        audit_scope_code=audit_scope_code,
    )
    audit = models.QMSAudit(
        amo_id=scoped_amo_id,
        domain=schedule.domain,
        kind=schedule.kind,
        audit_ref=audit_ref,
        audit_scope_id=schedule.audit_scope_id,
        audit_scope_code=audit_scope_code,
        reference_family="QAR",
        unit_code=unit_code,
        ref_year=ref_year,
        ref_sequence=ref_sequence,
        title=schedule.title,
        scope=schedule.scope,
        criteria=schedule.criteria,
        auditee=schedule.auditee,
        auditee_email=schedule.auditee_email,
        auditee_user_id=schedule.auditee_user_id,
        external_auditees_json=schedule.external_auditees_json,
        lead_auditor_user_id=schedule.lead_auditor_user_id,
        observer_auditor_user_id=schedule.observer_auditor_user_id,
        assistant_auditor_user_id=schedule.assistant_auditor_user_id,
        notify_auditors=schedule.notify_auditors,
        notify_auditees=schedule.notify_auditees,
        reminder_interval_days=schedule.reminder_interval_days,
        planned_start=planned_start,
        planned_end=planned_end,
        created_by_user_id=get_actor(),
    )
    db.add(audit)
    db.flush()

    schedule.last_run_at = datetime.now(timezone.utc)
    if schedule.frequency == models.QMSAuditScheduleFrequency.ONE_TIME:
        schedule.is_active = False
    else:
        schedule.next_due_date = _advance_schedule_date(schedule, schedule.next_due_date)

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="create",
        after={"audit_ref": audit.audit_ref, "status": audit.status.value, "title": audit.title},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit_schedule",
        entity_id=str(schedule.id),
        action="run",
        after={
            "audit_id": str(audit.id),
            "audit_ref": audit.audit_ref,
            "next_due_date": str(schedule.next_due_date),
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    _dispatch_audit_notice(db, audit=audit, amo_id=str(current_user.amo_id))
    db.commit()
    db.refresh(audit)
    return _serialize_audit(audit, db)


@router.post("/audits/reminders/run")
def run_audit_reminders(
    request: Request,
    upcoming_days: int = 7,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if upcoming_days < 1 or upcoming_days > 90:
        raise HTTPException(status_code=400, detail="Upcoming days must be between 1 and 90")
    today = date.today()
    upcoming_end = today + timedelta(days=upcoming_days)

    amo_id = _current_amo_id(current_user)
    audits_q = db.query(models.QMSAudit).filter(
        models.QMSAudit.status == models.QMSAuditStatus.PLANNED,
        models.QMSAudit.planned_start.isnot(None),
        models.QMSAudit.planned_start <= upcoming_end,
    )
    if amo_id:
        audits_q = audits_q.filter(models.QMSAudit.amo_id == amo_id)
    audits = audits_q.all()

    day_of_sent = 0
    upcoming_sent = 0

    for audit in audits:
        planned_start = audit.planned_start
        if not planned_start:
            continue

        if planned_start == today:
            already = audit.day_of_notice_sent_at and audit.day_of_notice_sent_at.date() == today
            if not already:
                message = f"Audit {audit.audit_ref} ({audit.title}) is scheduled for today."
                for target in (
                    audit.auditee_user_id,
                    audit.lead_auditor_user_id,
                    audit.observer_auditor_user_id,
                    audit.assistant_auditor_user_id,
                ):
                    _notify_user(db, target, message, models.QMSNotificationSeverity.ACTION_REQUIRED)
                audit.day_of_notice_sent_at = datetime.now(timezone.utc)
                audit_services.log_event(
                    db,
                    amo_id=current_user.amo_id,
                    actor_user_id=current_user.id,
                    entity_type="qms_audit",
                    entity_id=str(audit.id),
                    action="notify_day_of",
                    after={"planned_start": str(planned_start)},
                    correlation_id=str(uuid.uuid4()),
                    metadata=_audit_metadata(request),
                )
                day_of_sent += 1
            continue

        if planned_start > today and audit.upcoming_notice_sent_at is None:
            message = (
                f"Upcoming audit {audit.audit_ref} ({audit.title}) is scheduled for "
                f"{planned_start.isoformat()}."
            )
            for target in (
                audit.auditee_user_id,
                audit.lead_auditor_user_id,
                audit.observer_auditor_user_id,
                audit.assistant_auditor_user_id,
            ):
                _notify_user(db, target, message, models.QMSNotificationSeverity.INFO)
            audit.upcoming_notice_sent_at = datetime.now(timezone.utc)
            audit_services.log_event(
                db,
                amo_id=current_user.amo_id,
                actor_user_id=current_user.id,
                entity_type="qms_audit",
                entity_id=str(audit.id),
                action="notify_upcoming",
                after={"planned_start": str(planned_start)},
                correlation_id=str(uuid.uuid4()),
                metadata=_audit_metadata(request),
            )
            upcoming_sent += 1

    db.commit()
    return {"day_of_sent": day_of_sent, "upcoming_sent": upcoming_sent}




def _build_audit_workflow_summary(db: Session, audit: models.QMSAudit) -> QMSAuditWorkflowSummaryOut:
    findings = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.audit_id == audit.id).all()
    finding_ids = [finding.id for finding in findings]
    cars = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.finding_id.in_(finding_ids))
        .all()
        if finding_ids
        else []
    )
    findings_open = sum(1 for finding in findings if not finding.closed_at)
    cars_open = sum(1 for car in cars if car.status not in {models.CARStatus.CLOSED, models.CARStatus.CANCELLED})
    nc_findings = [
        finding
        for finding in findings
        if getattr(getattr(finding, "finding_type", None), "value", getattr(finding, "finding_type", None)) == "NON_CONFORMITY"
        or getattr(getattr(finding, "level", None), "value", getattr(finding, "level", None)) in {"LEVEL_1", "LEVEL_2", "LEVEL_3"}
    ]

    checklist_uploaded = bool(audit.checklist_file_ref)
    checklist_total = (
        db.query(models.QualityAuditChecklistItem)
        .filter(models.QualityAuditChecklistItem.audit_id == audit.id, models.QualityAuditChecklistItem.amo_id == audit.amo_id)
        .count()
    )
    checklist_completed = (
        db.query(models.QualityAuditChecklistItem)
        .filter(
            models.QualityAuditChecklistItem.audit_id == audit.id,
            models.QualityAuditChecklistItem.amo_id == audit.amo_id,
            models.QualityAuditChecklistItem.response_status != "PENDING",
        )
        .count()
    )
    report_tracker = db.query(models.QualityAuditReportTracker).filter(models.QualityAuditReportTracker.audit_id == audit.id).first()
    report_uploaded = bool(audit.report_file_ref)
    report_complete = report_uploaded or (report_tracker is not None and report_tracker.status in {"SUBMITTED", "ACCEPTED"})
    archive_count = db.query(models.QualityArchivePackage).filter(models.QualityArchivePackage.audit_id == audit.id).count()

    car_attachment_total = 0
    if cars:
        car_attachment_total = (
            db.query(models.CARAttachment)
            .filter(models.CARAttachment.car_id.in_([car.id for car in cars]))
            .count()
        )
    evidence_total = int(bool(audit.checklist_file_ref)) + int(bool(audit.report_file_ref)) + car_attachment_total

    war_room_complete = bool(
        audit.planned_start
        and audit.planned_end
        and audit.lead_auditor_user_id
        and (audit.auditee or audit.auditee_email or audit.auditee_user_id)
    )
    checklist_complete = checklist_uploaded or checklist_total > 0
    findings_complete = bool(audit.actual_start or audit.actual_end or findings or checklist_completed > 0)
    cars_complete = cars_open == 0 and (not nc_findings or len(cars) > 0)
    evidence_complete = evidence_total > 0
    closeout_complete = audit.status == models.QMSAuditStatus.CLOSED

    stage_defs = [
        {
            "id": "war-room",
            "label": "War room",
            "complete": war_room_complete,
            "helper": "Schedule, lead auditor, and auditee are set.",
            "metric": f"{audit.audit_ref} · {audit.status}",
        },
        {
            "id": "checklist",
            "label": "Checklist",
            "complete": checklist_complete,
            "helper": "A controlled checklist file is uploaded or portal checklist rows exist.",
            "metric": "File uploaded" if checklist_uploaded else f"{checklist_total} portal item(s)",
        },
        {
            "id": "findings",
            "label": "Findings",
            "complete": findings_complete,
            "helper": "Fieldwork has started or checklist/finding evidence has been captured.",
            "metric": f"{len(findings)} finding(s); {checklist_completed}/{checklist_total} checklist complete",
        },
        {
            "id": "cars",
            "label": "CARs",
            "complete": cars_complete,
            "helper": "NC findings have linked CARs where required and no CAR remains open.",
            "metric": f"{cars_open} open CAR(s)" if cars else ("CARs not required" if not nc_findings else "CARs required"),
        },
        {
            "id": "evidence",
            "label": "Evidence",
            "complete": evidence_complete,
            "helper": "Checklist, report, or CAR attachments are available as audit evidence.",
            "metric": f"{evidence_total} evidence item(s)",
        },
        {
            "id": "report",
            "label": "Report",
            "complete": report_complete,
            "helper": "Issued report is uploaded or tracker is submitted/accepted.",
            "metric": "Uploaded" if report_uploaded else (report_tracker.status if report_tracker else "Pending"),
        },
        {
            "id": "closeout",
            "label": "Closeout",
            "complete": closeout_complete,
            "helper": "Audit register status is closed.",
            "metric": f"{archive_count} archive package(s)" if archive_count else audit.status,
        },
    ]

    first_incomplete = next((entry for entry in stage_defs if not entry["complete"]), stage_defs[-1])
    current_stage_id = first_incomplete["id"]

    stages: list[QMSAuditWorkflowStageOut] = []
    for entry in stage_defs:
        stages.append(
            QMSAuditWorkflowStageOut(
                id=entry["id"],
                label=entry["label"],
                complete=bool(entry["complete"]),
                active=entry["id"] == current_stage_id,
                helper=entry["helper"],
                metric=entry["metric"],
            )
        )

    percent_complete = int(round((sum(1 for stage in stages if stage.complete) / 7) * 100))
    latest_ack = next((finding for finding in sorted(findings, key=lambda row: row.created_at, reverse=True) if finding.acknowledged_by_name or finding.acknowledged_by_email), None)

    return QMSAuditWorkflowSummaryOut(
        audit_id=audit.id,
        current_stage_id=current_stage_id,
        current_stage_label=next(stage.label for stage in stages if stage.id == current_stage_id),
        percent_complete=percent_complete,
        findings_total=len(findings),
        findings_open=findings_open,
        cars_total=len(cars),
        cars_open=cars_open,
        checklist_uploaded=checklist_uploaded,
        report_uploaded=report_uploaded,
        acknowledged_by_name=getattr(latest_ack, "acknowledged_by_name", None),
        acknowledged_by_email=getattr(latest_ack, "acknowledged_by_email", None),
        created_at=audit.created_at,
        stages=stages,
    )




@router.get("/audits/{audit_id}/workspace", response_model=QMSAuditWorkspaceOut)
def get_audit_workspace(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    workflow = _build_audit_workflow_summary(db, audit)
    return QMSAuditWorkspaceOut(audit=_serialize_audit(audit, db), workflow=workflow)

@router.get("/audits/{audit_id}/workflow-check", response_model=QMSAuditWorkspaceOut)
def get_audit_workflow_check(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    workflow = _build_audit_workflow_summary(db, audit)
    return QMSAuditWorkspaceOut(audit=_serialize_audit(audit, db), workflow=workflow)


@router.post("/audits/{audit_id}/issue-notice", response_model=QMSAuditNoticeDispatchOut)
def issue_audit_notice(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _dispatch_audit_notice(db, audit=audit, amo_id=str(_current_amo_id(current_user)))
    sent_at = datetime.now(timezone.utc)
    audit.upcoming_notice_sent_at = audit.upcoming_notice_sent_at or sent_at
    db.add(audit)
    audit_services.log_event(
        db,
        amo_id=_current_amo_id(current_user),
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="issue_notice",
        after={"sent_at": sent_at.isoformat()},
        correlation_id=str(uuid.uuid4()),
        metadata={"module": "quality"},
    )
    db.commit()
    return QMSAuditNoticeDispatchOut(audit_id=audit.id, dispatched=True, sent_at=sent_at, message="Audit notice dispatched.")


@router.get("/audits/{audit_id}/evidence-pack")
@router.get("/audits/{audit_id}/evidence-pack")
def export_audit_evidence_pack(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    if not _is_quality_admin(current_user) and not _audit_allows_user_by_audit(audit, current_user.id):
        raise HTTPException(status_code=403, detail="Insufficient privileges to export audit evidence packs")
    return build_evidence_pack(
        "qms_audit",
        audit_id,
        db,
        actor_user_id=current_user.id,
        correlation_id=str(uuid.uuid4()),
        amo_id=current_user.amo_id,
    )


@router.post("/audits/{audit_id}/checklist", response_model=QMSAuditOut)
def upload_audit_checklist(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)

    original_name = _sanitize_checklist_filename(file.filename)
    ext = Path(original_name).suffix.lower()
    if ext not in AUDIT_CHECKLIST_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Checklist extension is not allowed. Upload PDF, DOC, or DOCX only.")
    mime_type = _normalized_upload_mime(file)
    if mime_type not in AUDIT_CHECKLIST_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Checklist MIME type is not allowed. Upload PDF, DOC, or DOCX only.")

    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    target_dir = AUDIT_CHECKLIST_DIR / str(audit.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / unique_name

    size_bytes = 0
    try:
        with target_path.open("wb") as handle:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_AUDIT_CHECKLIST_BYTES:
                    raise HTTPException(status_code=413, detail="Checklist exceeds the 15MB limit.")
                handle.write(chunk)
        if size_bytes <= 0:
            raise HTTPException(status_code=422, detail="Checklist file is empty.")
    except HTTPException:
        target_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Checklist upload could not be saved.") from exc

    audit.checklist_file_ref = str(target_path)
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="upload_checklist",
        after={"checklist_file_name": original_name, "size_bytes": size_bytes, "mime_type": mime_type},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request) if request else None,
    )
    db.commit()
    db.refresh(audit)
    return _serialize_audit(audit, db)


@router.get("/audits/{audit_id}/checklist", response_class=FileResponse)
def download_audit_checklist(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    if not audit or not audit.checklist_file_ref:
        raise HTTPException(status_code=404, detail="Checklist not found")
    _require_audit_access(current_user, audit, allow_auditee=True)
    file_path = Path(audit.checklist_file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Checklist file missing on server.")
    return FileResponse(
        path=file_path,
        filename=_audit_download_filename(audit, "checklist", file_path),
        media_type=_audit_file_media_type(file_path),
    )


@router.post("/audits/{audit_id}/report", response_model=QMSAuditOut)
def upload_audit_report(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)

    original_name = Path(file.filename or "report").name
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    target_dir = AUDIT_REPORT_DIR / str(audit.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / unique_name

    with target_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    size_bytes = target_path.stat().st_size
    if size_bytes > MAX_AUDIT_REPORT_BYTES:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="Report exceeds the 25MB limit.")

    audit.report_file_ref = str(target_path)
    tracker = db.query(models.QualityAuditReportTracker).filter(models.QualityAuditReportTracker.audit_id == audit.id).first()
    if tracker:
        tracker.report_submitted_at = datetime.now(timezone.utc)
        tracker.status = "SUBMITTED"
        tracker.next_reminder_at = None
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="upload_report",
        after={"report_file_ref": audit.report_file_ref},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(audit)
    return _serialize_audit(audit, db)


@router.get("/audits/{audit_id}/report", response_class=FileResponse)
def download_audit_report(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    if not audit or not audit.report_file_ref:
        raise HTTPException(status_code=404, detail="Report not found")
    _require_audit_access(current_user, audit, allow_auditee=True)
    file_path = Path(audit.report_file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report file missing on server.")
    return FileResponse(
        path=file_path,
        filename=_audit_download_filename(audit, "report", file_path),
        media_type=_audit_file_media_type(file_path),
    )


@router.post("/audits/{audit_id}/report/share")
def share_audit_report(
    audit_id: UUID,
    request: Request,
    payload: Optional[dict[str, Any]] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    if not audit.report_file_ref:
        raise HTTPException(status_code=409, detail="Upload the issued audit report before sharing it.")

    data = payload or {}
    raw_groups = data.get("recipient_groups") or []
    if not isinstance(raw_groups, list):
        raise HTTPException(status_code=422, detail="recipient_groups must be a list")

    allowed_groups = {
        "accountable_manager",
        "quality_manager",
        "department_heads",
        "audited_department",
        "shop_personnel",
        "facility_personnel",
    }
    recipient_groups = [str(group).strip() for group in raw_groups if str(group).strip() in allowed_groups]
    if not recipient_groups:
        raise HTTPException(status_code=422, detail="Select at least one valid recipient group")

    message = str(data.get("message") or f"Audit report issued for {audit.audit_ref}. Review the report and monitor assigned CAR closeout actions.").strip()[:1000]
    recipient_ids: set[str] = set()

    def add_user_ids(rows: list[account_models.User]) -> None:
        for user in rows:
            if user and user.id and user.id != current_user.id and getattr(user, "is_active", True):
                recipient_ids.add(user.id)

    base_user_query = db.query(account_models.User).filter(
        account_models.User.amo_id == audit.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )

    if "accountable_manager" in recipient_groups:
        add_user_ids(
            base_user_query.filter(
                or_(
                    account_models.User.role == account_models.AccountRole.AMO_ADMIN,
                    account_models.User.position_title.ilike("%accountable manager%"),
                )
            ).all()
        )

    if "quality_manager" in recipient_groups:
        add_user_ids(base_user_query.filter(account_models.User.role == account_models.AccountRole.QUALITY_MANAGER).all())

    if "department_heads" in recipient_groups:
        add_user_ids(
            base_user_query.filter(
                or_(
                    account_models.User.position_title.ilike("%head%"),
                    account_models.User.position_title.ilike("%manager%"),
                    account_models.User.role.in_(
                        [
                            account_models.AccountRole.PLANNING_ENGINEER,
                            account_models.AccountRole.PRODUCTION_ENGINEER,
                            account_models.AccountRole.STORES_MANAGER,
                        ]
                    ),
                )
            ).all()
        )

    if "audited_department" in recipient_groups and audit.auditee_user_id:
        auditee = _load_user(db, audit.auditee_user_id)
        if auditee and auditee.department_id:
            add_user_ids(base_user_query.filter(account_models.User.department_id == auditee.department_id).all())
        elif auditee:
            recipient_ids.add(auditee.id)

    department_terms: list[str] = []
    if "shop_personnel" in recipient_groups:
        department_terms.extend(["shop", "production", "maintenance", "engineering"])
    if "facility_personnel" in recipient_groups:
        department_terms.extend(["facility", "facilities", "hangar"])
    if department_terms:
        dept_filter = or_(
            *[account_models.Department.name.ilike(f"%{term}%") for term in department_terms],
            *[account_models.Department.code.ilike(f"%{term}%") for term in department_terms],
        )
        add_user_ids(
            base_user_query.join(
                account_models.Department, account_models.Department.id == account_models.User.department_id
            ).filter(dept_filter).all()
        )

    # Always include the named audit participants when the report is distributed from the audit hub.
    for participant_id in (
        audit.lead_auditor_user_id,
        audit.observer_auditor_user_id,
        audit.assistant_auditor_user_id,
        audit.auditee_user_id,
    ):
        if participant_id and participant_id != current_user.id:
            recipient_ids.add(participant_id)

    action_url = _audit_workspace_notification_url(db, audit, tab="report")
    for user_id in sorted(recipient_ids):
        _notify_user(
            db,
            user_id,
            message,
            models.QMSNotificationSeverity.ACTION_REQUIRED,
            action_url=action_url,
            action_label="Open audit report",
            entity_type="qms_audit",
            entity_id=audit.id,
        )

    audit_services.log_event(
        db,
        amo_id=audit.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="share_report",
        after={"recipient_groups": recipient_groups, "shared": len(recipient_ids)},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.commit()
    return {
        "audit_id": str(audit.id),
        "recipient_groups": recipient_groups,
        "recipient_user_ids": sorted(recipient_ids),
        "shared": len(recipient_ids),
    }


@router.delete("/audits/{audit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audit(
    audit_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    before = {"audit_ref": audit.audit_ref, "title": audit.title, "status": audit.status.value}
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="delete",
        before=before,
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.delete(audit)
    db.commit()
    return None


@router.patch("/audits/{audit_id}", response_model=QMSAuditOut)
def update_audit(
    audit_id: UUID,
    payload: QMSAuditUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    before_status = audit.status.value
    before = {
        "status": before_status,
        "title": audit.title,
        "audit_ref": audit.audit_ref,
        "audit_scope_code": audit.audit_scope_code,
        "planned_start": str(audit.planned_start) if audit.planned_start else None,
    }
    changes = payload.model_dump(exclude_unset=True)

    protected_identity_fields = {
        "title", "kind", "scope", "criteria", "auditee", "auditee_email", "auditee_user_id",
        "external_auditees", "lead_auditor_user_id", "observer_auditor_user_id", "assistant_auditor_user_id",
        "planned_start", "planned_end", "audit_scope_id", "audit_scope_code",
        "notify_auditors", "notify_auditees", "reminder_interval_days",
    }
    if not _external_audit_is_editable(audit.kind) and any(field in changes for field in protected_identity_fields):
        raise HTTPException(status_code=403, detail="Internal and first-party audit identity/schedule fields are locked after creation. Close, cancel, or create a new audit instead of editing the record.")

    prospective_kind = changes.get("kind", audit.kind)
    prospective_start = changes.get("planned_start", audit.planned_start)
    prospective_end = changes.get("planned_end", audit.planned_end)
    _validate_one_calendar_year(start=prospective_start, end=prospective_end)

    reference_needs_regeneration = False
    if "kind" in changes and changes["kind"] is not None:
        audit.kind = changes["kind"]
        reference_needs_regeneration = True
    if "audit_scope_id" in changes or "audit_scope_code" in changes or reference_needs_regeneration:
        resolved_scope = _resolve_audit_scope(
            db,
            amo_id=audit.amo_id,
            audit_scope_id=changes.get("audit_scope_id") or audit.audit_scope_id,
            audit_scope_code=changes.get("audit_scope_code") or audit.audit_scope_code,
            kind=audit.kind,
        )
        if resolved_scope.code != audit.audit_scope_code:
            reference_needs_regeneration = True
        audit.audit_scope_id = resolved_scope.id
        audit.audit_scope_code = resolved_scope.code

    planned_start_changed = False
    if "title" in changes and changes["title"] is not None:
        audit.title = changes["title"].strip()
    for field in (
        "status", "scope", "criteria", "auditee", "auditee_email",
        "planned_start", "planned_end", "actual_start", "actual_end",
        "report_file_ref", "checklist_file_ref", "auditee_user_id",
        "lead_auditor_user_id", "observer_auditor_user_id", "assistant_auditor_user_id",
        "notify_auditors", "notify_auditees", "reminder_interval_days",
    ):
        if field in changes and changes[field] is not None:
            setattr(audit, field, changes[field])
            if field == "planned_start":
                planned_start_changed = True
                reference_needs_regeneration = True

    if reference_needs_regeneration and _external_audit_is_editable(audit.kind):
        audit_ref, unit_code, ref_year, ref_sequence = _generate_audit_reference(
            db,
            amo_id=audit.amo_id,
            target_date=audit.planned_start,
            audit_scope_code=audit.audit_scope_code or _scope_default_code_for_kind(audit.kind),
        )
        audit.audit_ref = audit_ref
        audit.unit_code = unit_code
        audit.ref_year = ref_year
        audit.ref_sequence = ref_sequence

    if planned_start_changed:
        audit.upcoming_notice_sent_at = None
        audit.day_of_notice_sent_at = None

    if payload.status == QMSAuditStatus.CLOSED:
        findings = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.audit_id == audit.id).all()
        nc_findings = [f for f in findings if f.finding_type == models.QMSFindingType.NON_CONFORMITY]
        if not nc_findings:
            if not audit.report_file_ref or not audit.checklist_file_ref:
                raise HTTPException(status_code=400, detail="Audit report and checklist are required to close an audit with no NC findings")
        else:
            finding_ids = [f.id for f in nc_findings]
            cars = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.finding_id.in_(finding_ids)).all()
            car_by_finding = {car.finding_id: car for car in cars}
            missing = [str(fid) for fid in finding_ids if fid not in car_by_finding]
            if missing:
                raise HTTPException(status_code=400, detail="All NC findings must have an issued CAR before audit closure")
            for car in cars:
                if car.root_cause_status != "ACCEPTED" or car.capa_status != "ACCEPTED":
                    raise HTTPException(status_code=400, detail="All CAR root cause and CAPA reviews must be accepted before audit closure")
                if car.evidence_required and not car.evidence_verified_at:
                    raise HTTPException(status_code=400, detail="Evidence verification is required for all CARs before audit closure")

    if payload.status == QMSAuditStatus.CLOSED and audit.retention_until is None:
        if audit.actual_end:
            audit.retention_until = date(audit.actual_end.year + 5, audit.actual_end.month, audit.actual_end.day)
        elif audit.planned_end:
            audit.retention_until = date(audit.planned_end.year + 5, audit.planned_end.month, audit.planned_end.day)
        note_msg = f"Audit {audit.audit_ref} closed. Please send closure pack to {audit.auditee_email or 'auditee'}."
        _notify_user(db, audit.lead_auditor_user_id, note_msg, models.QMSNotificationSeverity.INFO)

    if payload.status is not None and payload.status.value != before_status:
        try:
            apply_transition(
                db,
                actor_user_id=current_user.id,
                entity_type="qms_audit",
                entity_id=str(audit.id),
                from_state=before_status,
                to_state=payload.status.value,
                before_obj={"status": before_status, "audit_id": str(audit.id), "amo_id": current_user.amo_id},
                after_obj={"status": payload.status.value, "audit_id": str(audit.id), "title": audit.title, "retention_until": str(audit.retention_until) if audit.retention_until else None, "amo_id": current_user.amo_id},
                correlation_id=str(uuid.uuid4()),
                critical=payload.status == QMSAuditStatus.CLOSED,
            )
        except TransitionError as exc:
            return JSONResponse(status_code=400, content={"error": exc.code, "detail": exc.detail})
    else:
        audit_services.log_event(
            db,
            amo_id=current_user.amo_id,
            actor_user_id=current_user.id,
            entity_type="qms_audit",
            entity_id=str(audit.id),
            action="update",
            before=before,
            after={"status": audit.status.value, "title": audit.title, "audit_ref": audit.audit_ref, "audit_scope_code": audit.audit_scope_code},
            correlation_id=str(uuid.uuid4()),
            metadata=_audit_metadata(request),
            critical=reference_needs_regeneration,
        )
    db.commit()
    db.refresh(audit)
    return audit


def _next_audit_finding_ref(db: Session, audit: models.QMSAudit) -> str:
    prefix = (audit.audit_ref or "QAR").strip() or "QAR"
    max_seq = 0
    refs = (
        db.query(models.QMSAuditFinding.finding_ref)
        .filter(models.QMSAuditFinding.audit_id == audit.id)
        .all()
    )
    for (ref,) in refs:
        match = re.search(r"(?:F|FIND)[-/]?(\d+)$", ref or "", re.IGNORECASE)
        if match:
            try:
                max_seq = max(max_seq, int(match.group(1)))
            except ValueError:
                continue
    return f"{prefix}-F-{max_seq + 1:03d}"[:64]


def _car_priority_for_finding_level(level: FindingLevel) -> models.CARPriority:
    if level == FindingLevel.LEVEL_1:
        return models.CARPriority.CRITICAL
    if level == FindingLevel.LEVEL_2:
        return models.CARPriority.HIGH
    return models.CARPriority.MEDIUM


def _ensure_car_for_finding(
    db: Session,
    *,
    audit: models.QMSAudit,
    finding: models.QMSAuditFinding,
    requested_by_user_id: Optional[str],
) -> Optional[models.CorrectiveActionRequest]:
    if finding.level == FindingLevel.LEVEL_4 or finding.finding_type != models.QMSFindingType.NON_CONFORMITY:
        return None
    existing = (
        db.query(models.CorrectiveActionRequest)
        .filter(
            models.CorrectiveActionRequest.amo_id == audit.amo_id,
            models.CorrectiveActionRequest.finding_id == finding.id,
        )
        .first()
    )
    if existing:
        return existing
    title_ref = finding.finding_ref or str(finding.id)
    summary_parts = [finding.description.strip()]
    if finding.requirement_ref:
        summary_parts.append(f"Requirement/reference: {finding.requirement_ref.strip()}")
    if finding.objective_evidence:
        summary_parts.append(f"Objective evidence: {finding.objective_evidence.strip()}")
    car = create_car(
        db,
        program=models.CARProgram.QUALITY,
        title=f"CAR for {title_ref}",
        summary="\n\n".join(part for part in summary_parts if part),
        priority=_car_priority_for_finding_level(finding.level),
        requested_by_user_id=requested_by_user_id,
        assigned_to_user_id=audit.auditee_user_id,
        due_date=finding.target_close_date,
        target_closure_date=finding.target_close_date,
        finding_id=finding.id,
        amo_id=audit.amo_id,
    )
    car.evidence_required = True
    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.ASSIGNMENT,
        message=f"Auto-generated from audit finding {title_ref}.",
        actor_user_id=requested_by_user_id,
    )
    if audit.auditee_user_id:
        _notify_user(
            db,
            audit.auditee_user_id,
            f"CAR {car.car_number} was issued for audit finding {title_ref}.",
            models.QMSNotificationSeverity.ACTION_REQUIRED,
            action_url=_safe_notification_action_url(build_car_invite_link(car)),
            action_label="Open CAR response",
            entity_type="car",
            entity_id=car.id,
        )
    return car


@router.post("/audits/{audit_id}/findings", response_model=QMSFindingOut, status_code=status.HTTP_201_CREATED)
def add_finding(
    audit_id: UUID,
    payload: QMSFindingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_fieldwork_write_access(current_user, audit)

    level = normalize_finding_level(payload.severity, payload.level, payload.finding_type)
    finding_type = models.QMSFindingType.OBSERVATION if level == FindingLevel.LEVEL_4 else models.QMSFindingType.NON_CONFORMITY

    target_close_date = payload.target_close_date
    if target_close_date is None and level != FindingLevel.LEVEL_4:
        target_close_date = compute_target_close_date(level)

    finding = models.QMSAuditFinding(
        amo_id=audit.amo_id,
        audit_id=audit_id,
        finding_ref=payload.finding_ref or _next_audit_finding_ref(db, audit),
        finding_type=finding_type,
        severity=payload.severity,
        level=level,
        requirement_ref=payload.requirement_ref,
        description=payload.description,
        objective_evidence=payload.objective_evidence,
        safety_sensitive=payload.safety_sensitive,
        target_close_date=target_close_date,
        created_by_user_id=current_user.id,
    )
    db.add(finding)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
        action="create",
        after={
            "audit_id": str(audit.id),
            "severity": finding.severity.value,
            "level": finding.level.value,
            "target_close_date": str(finding.target_close_date),
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    if level != FindingLevel.LEVEL_4:
        task_owner = audit.lead_auditor_user_id or current_user.id
        task_services.create_task(
            db,
            amo_id=current_user.amo_id,
            title="Respond to finding",
            description=f"Finding {finding.finding_ref or finding.id} requires response.",
            owner_user_id=task_owner,
            supervisor_user_id=audit.observer_auditor_user_id,
            due_at=_date_to_datetime(finding.target_close_date),
            entity_type="qms_finding",
            entity_id=str(finding.id),
            priority=2,
        )
    # Level 1-3 NCRs open CAPA control. Level 4 observations remain monitored unless escalated.
    if level != FindingLevel.LEVEL_4 and audit.status in (models.QMSAuditStatus.PLANNED, models.QMSAuditStatus.IN_PROGRESS):
        audit.status = models.QMSAuditStatus.CAP_OPEN

    linked_car = _ensure_car_for_finding(db, audit=audit, finding=finding, requested_by_user_id=current_user.id)
    if linked_car:
        audit_services.log_event(
            db,
            amo_id=current_user.amo_id,
            actor_user_id=current_user.id,
            entity_type="qms_car",
            entity_id=str(linked_car.id),
            action="auto_create_from_finding",
            after={"finding_id": str(finding.id), "car_number": linked_car.car_number},
            correlation_id=str(uuid.uuid4()),
            metadata=_audit_metadata(request),
            critical=finding.level == FindingLevel.LEVEL_1,
        )

    # Build the API response before commit/session expiry.  This avoids an
    # automatic relationship refresh against legacy CAP tables that may not be
    # present in partially migrated local databases.
    response = _serialize_finding(finding)
    db.commit()

    return response


@router.get("/audits/{audit_id}/findings", response_model=List[QMSFindingOut])
def list_findings(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    return (
        db.query(models.QMSAuditFinding)
        .filter(
            models.QMSAuditFinding.audit_id == audit_id,
            models.QMSAuditFinding.amo_id == audit.amo_id,
        )
        .order_by(models.QMSAuditFinding.created_at.desc())
        .all()
    )


@router.patch("/audits/{audit_id}/findings/{finding_id}", response_model=QMSFindingOut)
@router.patch("/findings/{finding_id}", response_model=QMSFindingOut)
def update_finding(
    finding_id: UUID,
    payload: QMSFindingUpdate,
    request: Request,
    audit_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding, audit = _get_finding_and_audit_for_amo(
        db,
        current_user=current_user,
        finding_id=finding_id,
        audit_id=audit_id,
    )
    _require_finding_owner_access(current_user, finding, audit)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return _serialize_finding(finding)

    before = {
        "finding_ref": finding.finding_ref,
        "finding_type": finding.finding_type.value if finding.finding_type else None,
        "severity": finding.severity.value if finding.severity else None,
        "level": finding.level.value if finding.level else None,
        "requirement_ref": finding.requirement_ref,
        "description": finding.description,
        "target_close_date": str(finding.target_close_date) if finding.target_close_date else None,
    }

    if "severity" in data or "level" in data or "finding_type" in data:
        severity = data.get("severity", finding.severity)
        requested_type = data.get("finding_type", finding.finding_type)
        level = normalize_finding_level(severity, data.get("level", finding.level), requested_type)
        finding.level = level
        finding.finding_type = models.QMSFindingType.OBSERVATION if level == FindingLevel.LEVEL_4 else models.QMSFindingType.NON_CONFORMITY
        finding.severity = severity
        if "target_close_date" not in data and finding.target_close_date is None and level != FindingLevel.LEVEL_4:
            finding.target_close_date = compute_target_close_date(level, base=finding.created_at.date())

    for field in ("finding_ref", "requirement_ref", "description", "objective_evidence", "safety_sensitive", "target_close_date"):
        if field in data:
            value = data[field]
            if isinstance(value, str):
                value = value.strip() or None
            if field == "description" and not value:
                raise HTTPException(status_code=400, detail="Finding description cannot be empty")
            setattr(finding, field, value)

    linked_car = _ensure_car_for_finding(db, audit=audit, finding=finding, requested_by_user_id=current_user.id)
    if linked_car and finding.level != FindingLevel.LEVEL_4:
        linked_car.priority = _car_priority_for_finding_level(finding.level)
        linked_car.due_date = finding.target_close_date
        linked_car.target_closure_date = finding.target_close_date

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
        action="update",
        before=before,
        after={
            "finding_ref": finding.finding_ref,
            "level": finding.level.value if finding.level else None,
            "finding_type": finding.finding_type.value if finding.finding_type else None,
            "target_close_date": str(finding.target_close_date) if finding.target_close_date else None,
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=finding.level == FindingLevel.LEVEL_1,
    )
    response = _serialize_finding(finding)
    db.commit()
    return response


@router.delete("/audits/{audit_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_finding(
    finding_id: UUID,
    request: Request,
    audit_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding, audit = _get_finding_and_audit_for_amo(
        db,
        current_user=current_user,
        finding_id=finding_id,
        audit_id=audit_id,
    )
    _require_finding_owner_access(current_user, finding, audit)

    linked_cars = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.finding_id == finding.id).all()
    locked = [car.car_number for car in linked_cars if car.status in {models.CARStatus.ESCALATED, models.CARStatus.CLOSED, models.CARStatus.PENDING_VERIFICATION}]
    if locked:
        raise HTTPException(status_code=409, detail=f"Finding cannot be deleted because linked CAR(s) are locked: {', '.join(locked)}")
    for car in linked_cars:
        db.delete(car)

    attachments = db.query(models.QMSFindingAttachment).filter(models.QMSFindingAttachment.finding_id == finding.id).all()
    for attachment in attachments:
        try:
            Path(attachment.file_ref).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(attachment)

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
        action="delete",
        before={"finding_ref": finding.finding_ref, "description": finding.description, "level": finding.level.value if finding.level else None},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.delete(finding)
    db.commit()
    return None


@router.post("/audits/{audit_id}/findings/{finding_id}/review-flag", response_model=QMSFindingOut)
@router.post("/findings/{finding_id}/review-flag", response_model=QMSFindingOut)
def flag_finding_for_review(
    finding_id: UUID,
    payload: QMSFindingReviewFlag,
    request: Request,
    audit_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding, audit = _get_finding_and_audit_for_amo(
        db,
        current_user=current_user,
        finding_id=finding_id,
        audit_id=audit_id,
    )
    _require_audit_access(current_user, audit)
    if not (_is_quality_manager(current_user) or _is_system_quality_admin(current_user) or _audit_allows_user_by_audit(audit, current_user.id)):
        raise HTTPException(status_code=403, detail="Insufficient privileges to flag finding for review")

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Review flag reason is required")
    addressees = {audit.lead_auditor_user_id, finding.created_by_user_id}
    for recipient in addressees:
        if recipient and recipient != current_user.id:
            _notify_user(
                db,
                recipient,
                f"Finding {finding.finding_ref or finding.id} was flagged for review: {reason}",
                models.QMSNotificationSeverity.ACTION_REQUIRED,
            )
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
        action="flag_for_review",
        after={"reason": reason, "audit_id": str(audit.id)},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.commit()
    return _serialize_finding(finding)


@router.get("/audits/{audit_id}/finding-attachments", response_model=List[QMSFindingAttachmentOut])
def list_audit_finding_attachments(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    attachments = (
        db.query(models.QMSFindingAttachment)
        .join(models.QMSAuditFinding, models.QMSAuditFinding.id == models.QMSFindingAttachment.finding_id)
        .filter(
            models.QMSAuditFinding.audit_id == audit.id,
            models.QMSAuditFinding.amo_id == audit.amo_id,
        )
        .order_by(models.QMSFindingAttachment.uploaded_at.desc())
        .all()
    )
    return [_serialize_finding_attachment(attachment) for attachment in attachments]


@router.get("/findings/{finding_id}/attachments", response_model=List[QMSFindingAttachmentOut])
def list_finding_attachments(
    finding_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_audit_access(current_user, audit)
    attachments = (
        db.query(models.QMSFindingAttachment)
        .filter(models.QMSFindingAttachment.finding_id == finding.id)
        .order_by(models.QMSFindingAttachment.uploaded_at.desc())
        .all()
    )
    return [_serialize_finding_attachment(attachment) for attachment in attachments]


@router.post("/findings/{finding_id}/attachments", response_model=QMSFindingAttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_finding_attachment(
    finding_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_finding_owner_access(current_user, finding, audit)

    target_path, original_name, sha256, size_bytes = _store_finding_attachment(finding.id, file)
    attachment = models.QMSFindingAttachment(
        finding_id=finding.id,
        filename=original_name,
        file_ref=str(target_path),
        content_type=_normalized_upload_mime(file) or file.content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        uploaded_by_user_id=current_user.id,
    )
    db.add(attachment)
    db.flush()
    audit_services.log_event(
        db,
        amo_id=audit.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding_attachment",
        entity_id=str(attachment.id),
        action="uploaded",
        after={"finding_id": str(finding.id), "filename": original_name, "sha256": sha256},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(attachment)
    return _serialize_finding_attachment(attachment)


@router.get("/findings/{finding_id}/attachments/{attachment_id}/download", response_class=FileResponse)
def download_finding_attachment(
    finding_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_audit_access(current_user, audit)
    attachment = (
        db.query(models.QMSFindingAttachment)
        .filter(
            models.QMSFindingAttachment.id == attachment_id,
            models.QMSFindingAttachment.finding_id == finding.id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Finding evidence not found")
    file_path = Path(attachment.file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Finding evidence file missing on server.")
    return FileResponse(path=file_path, filename=attachment.filename, media_type=attachment.content_type or "application/octet-stream")


@router.delete("/findings/{finding_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_finding_attachment(
    finding_id: UUID,
    attachment_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_finding_owner_access(current_user, finding, audit)
    attachment = (
        db.query(models.QMSFindingAttachment)
        .filter(
            models.QMSFindingAttachment.id == attachment_id,
            models.QMSFindingAttachment.finding_id == finding.id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Finding evidence not found")
    try:
        Path(attachment.file_ref).unlink(missing_ok=True)
    except Exception:
        pass
    audit_services.log_event(
        db,
        amo_id=audit.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding_attachment",
        entity_id=str(attachment.id),
        action="deleted",
        before={"finding_id": str(finding.id), "filename": attachment.filename, "sha256": attachment.sha256},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.delete(attachment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/findings/{finding_id}/close", response_model=QMSFindingOut)
def close_finding(
    finding_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_finding_owner_access(current_user, finding, audit)
    if not finding.closed_at:
        before_state = "OPEN"
        finding.closed_at = func.now()
        try:
            apply_transition(
                db,
                actor_user_id=current_user.id,
                entity_type="qms_finding",
                entity_id=str(finding.id),
                from_state=before_state,
                to_state="CLOSED",
                before_obj={
                    "status": before_state,
                    "amo_id": current_user.amo_id,
                },
                after_obj={
                    "status": "CLOSED",
                    "closed_at": str(finding.closed_at),
                    "objective_evidence": finding.objective_evidence,
                    "verified_at": str(finding.verified_at) if finding.verified_at else None,
                    "amo_id": current_user.amo_id,
                },
                correlation_id=str(uuid.uuid4()),
                critical=True,
            )
        except TransitionError as exc:
            return JSONResponse(status_code=400, content={"error": exc.code, "detail": exc.detail})
        task_services.close_tasks_for_entity(
            db,
            amo_id=current_user.amo_id,
            entity_type="qms_finding",
            entity_id=str(finding.id),
            actor_user_id=current_user.id,
        )
        db.commit()
        db.refresh(finding)
    return finding


@router.post("/findings/{finding_id}/verify", response_model=QMSFindingOut)
def verify_finding(
    finding_id: UUID,
    payload: QMSFindingVerify,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_finding_owner_access(current_user, finding, audit)

    if payload.objective_evidence is not None:
        finding.objective_evidence = payload.objective_evidence

    finding.verified_at = payload.verified_at or func.now()
    finding.verified_by_user_id = get_actor()

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
        action="verify",
        after={
            "verified_at": str(finding.verified_at),
            "verified_by_user_id": finding.verified_by_user_id,
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )

    db.commit()
    db.refresh(finding)
    return finding


@router.post("/findings/{finding_id}/ack", response_model=QMSFindingOut)
def acknowledge_finding(
    finding_id: UUID,
    payload: QMSFindingAcknowledge,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = _get_finding_for_amo(db, amo_id=_current_amo_id(current_user), finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=finding.audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)

    finding.acknowledged_at = payload.acknowledged_at or func.now()
    finding.acknowledged_by_user_id = current_user.id
    finding.acknowledged_by_name = payload.acknowledged_by_name or current_user.full_name
    finding.acknowledged_by_email = payload.acknowledged_by_email or current_user.email

    if audit:
        note_msg = f"Finding {finding.finding_ref or finding.id} acknowledged by {finding.acknowledged_by_name}."
        for auditor_id in (
            audit.lead_auditor_user_id,
            audit.observer_auditor_user_id,
            audit.assistant_auditor_user_id,
        ):
            _notify_user(db, auditor_id, note_msg, models.QMSNotificationSeverity.INFO)

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_finding",
        entity_id=str(finding.id),
        action="acknowledge",
        after={
            "acknowledged_at": str(finding.acknowledged_at),
            "acknowledged_by_user_id": finding.acknowledged_by_user_id,
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )

    db.commit()
    db.refresh(finding)
    return finding


@router.put("/findings/{finding_id}/cap", response_model=QMSCAPOut)
def upsert_cap(
    finding_id: UUID,
    payload: QMSCAPUpsert,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    finding = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    cap = db.query(models.QMSCorrectiveAction).filter(models.QMSCorrectiveAction.finding_id == finding_id).first()
    created_cap = False
    if not cap:
        cap = models.QMSCorrectiveAction(amo_id=finding.amo_id, finding_id=finding_id)
        db.add(cap)
        created_cap = True

    before_status = cap.status.value if cap.status else None
    before = {"status": before_status}
    for field in (
        "root_cause", "containment_action", "corrective_action", "preventive_action",
        "responsible_user_id", "due_date", "evidence_ref", "verified_at", "verified_by_user_id", "status",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(cap, field, val)

    if created_cap:
        db.flush()
        task_services.create_task(
            db,
            amo_id=current_user.amo_id,
            title="Complete CAPA actions + evidence",
            description=f"Complete corrective actions for finding {finding.finding_ref or finding.id}.",
            owner_user_id=cap.responsible_user_id or current_user.id,
            supervisor_user_id=None,
            due_at=_date_to_datetime(cap.due_date),
            entity_type="qms_cap",
            entity_id=str(cap.id),
            priority=2,
        )

    if payload.status in (models.QMSCAPStatus.CLOSED, models.QMSCAPStatus.REJECTED):
        audit = db.query(models.QMSAudit).filter(models.QMSAudit.id == finding.audit_id).first()
        if audit:
            note_msg = (
                f"CAP {payload.status.value} for audit {audit.audit_ref} ({audit.title})."
            )
            for auditor_id in (
                audit.lead_auditor_user_id,
                audit.observer_auditor_user_id,
                audit.assistant_auditor_user_id,
            ):
                _notify_user(db, auditor_id, note_msg, models.QMSNotificationSeverity.WARNING)

    if payload.status == models.QMSCAPStatus.IN_PROGRESS and cap.evidence_ref:
        audit = db.query(models.QMSAudit).filter(models.QMSAudit.id == finding.audit_id).first()
        verifier_id = audit.lead_auditor_user_id if audit else None
        task_services.create_task(
            db,
            amo_id=current_user.amo_id,
            title="Verify CAPA",
            description=f"Verify CAPA evidence for finding {finding.finding_ref or finding.id}.",
            owner_user_id=verifier_id or current_user.id,
            supervisor_user_id=None,
            due_at=None,
            entity_type="qms_cap",
            entity_id=str(cap.id),
            priority=2,
        )

    if payload.status is not None and payload.status.value != before.get("status"):
        try:
            apply_transition(
                db,
                actor_user_id=current_user.id,
                entity_type="qms_cap",
                entity_id=str(cap.id),
                from_state=before_status or models.QMSCAPStatus.OPEN.value,
                to_state=payload.status.value,
                before_obj={
                    "status": before_status,
                    "amo_id": current_user.amo_id,
                },
                after_obj={
                    "status": payload.status.value,
                    "containment_action": cap.containment_action,
                    "corrective_action": cap.corrective_action,
                    "evidence_ref": cap.evidence_ref,
                    "verified_at": str(cap.verified_at) if cap.verified_at else None,
                    "amo_id": current_user.amo_id,
                },
                correlation_id=str(uuid.uuid4()),
                critical=payload.status == models.QMSCAPStatus.CLOSED,
            )
        except TransitionError as exc:
            return JSONResponse(status_code=400, content={"error": exc.code, "detail": exc.detail})
        if payload.status == models.QMSCAPStatus.CLOSED:
            task_services.close_tasks_for_entity(
                db,
                amo_id=current_user.amo_id,
                entity_type="qms_cap",
                entity_id=str(cap.id),
                actor_user_id=current_user.id,
            )
    else:
        audit_services.log_event(
            db,
            amo_id=current_user.amo_id,
            actor_user_id=current_user.id,
            entity_type="qms_cap",
            entity_id=str(cap.id),
            action="update",
            before=before,
            after={"status": cap.status.value, "finding_id": str(finding_id)},
            correlation_id=str(uuid.uuid4()),
            metadata=_audit_metadata(request),
        )
    db.commit()
    db.refresh(cap)
    return cap


# -----------------------------
# Corrective Action Requests (CAR)
# -----------------------------


def _quality_car_value(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw or "").replace("_", " ").strip()


def _quality_car_title(value: Any) -> str:
    text_value = _quality_car_value(value)
    return text_value.title() if text_value else ""


def _latest_active_car_response(car: models.CorrectiveActionRequest) -> Optional[models.CARResponse]:
    responses = [response for response in getattr(car, "responses", []) if _quality_car_value(getattr(response, "status", "")).upper() != "RECALLED"]
    if not responses:
        return None
    return sorted(responses, key=lambda response: response.submitted_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[0]


def _decorate_car_register_items(db: Session, cars: list[models.CorrectiveActionRequest]) -> list[models.CorrectiveActionRequest]:
    """Attach display-only register fields used by the frontend spreadsheet view.

    These values are intentionally computed server-side so the register does not
    guess audit/finding/user context from the CAR title.
    """
    if not cars:
        return cars

    user_ids: set[str] = set()
    for car in cars:
        for user_id in (car.requested_by_user_id, car.assigned_to_user_id):
            if user_id:
                user_ids.add(user_id)
        finding = getattr(car, "finding", None)
        audit = getattr(finding, "audit", None) if finding else None
        for user_id in (
            getattr(audit, "lead_auditor_user_id", None),
            getattr(audit, "observer_auditor_user_id", None),
            getattr(audit, "assistant_auditor_user_id", None),
            getattr(audit, "auditee_user_id", None),
            getattr(finding, "created_by_user_id", None) if finding else None,
        ):
            if user_id:
                user_ids.add(user_id)

    users = {}
    departments = {}
    if user_ids:
        user_rows = db.query(account_models.User).filter(account_models.User.id.in_(list(user_ids))).all()
        users = {user.id: user for user in user_rows}
        dept_ids = {user.department_id for user in user_rows if getattr(user, "department_id", None)}
        if dept_ids:
            dept_rows = db.query(account_models.Department).filter(account_models.Department.id.in_(list(dept_ids))).all()
            departments = {dept.id: dept for dept in dept_rows}

    today = date.today()
    for car in cars:
        finding = getattr(car, "finding", None)
        audit = getattr(finding, "audit", None) if finding else None
        assigned_user = users.get(car.assigned_to_user_id) if car.assigned_to_user_id else None
        requested_user = users.get(car.requested_by_user_id) if car.requested_by_user_id else None
        auditor_user = users.get(getattr(audit, "lead_auditor_user_id", None)) if audit else None
        if auditor_user is None:
            auditor_user = requested_user
        department = departments.get(getattr(assigned_user, "department_id", None)) if assigned_user else None
        latest_response = _latest_active_car_response(car)

        issued_date = car.created_at.date() if car.created_at else None
        closed_date = car.closed_at.date() if car.closed_at else None
        due_date = car.due_date or car.target_closure_date

        remarks: list[str] = []
        if car.root_cause_status:
            remarks.append(f"ROOT CAUSE: {_quality_car_value(car.root_cause_status).upper()}")
        if car.capa_status:
            remarks.append(f"CAP: {_quality_car_value(car.capa_status).upper()}")
        if car.evidence_verified_at:
            remarks.append("EVIDENCE: VERIFIED")
        if car.root_cause_review_note:
            remarks.append(str(car.root_cause_review_note).strip())
        if car.capa_review_note and car.capa_review_note != car.root_cause_review_note:
            remarks.append(str(car.capa_review_note).strip())

        car.audit_id = getattr(audit, "id", None)
        car.audit_ref = getattr(audit, "audit_ref", None)
        car.audit_title = getattr(audit, "title", None)
        car.finding_ref = getattr(finding, "finding_ref", None)
        car.finding_description = getattr(finding, "description", None) or car.summary
        car.date_issued = issued_date
        car.date_closed = closed_date
        if issued_date and closed_date:
            car.days_out = (closed_date - issued_date).days
        elif issued_date:
            car.days_out = (today - issued_date).days
        else:
            car.days_out = None
        car.days_remaining_past = (due_date - today).days if due_date else None
        car.auditor_remarks = "\n".join([line for line in remarks if line]) or None
        car.register_root_cause = car.root_cause_text or car.root_cause or getattr(latest_response, "root_cause", None)
        car.register_cap = car.capa_text or car.corrective_action or getattr(latest_response, "corrective_action", None) or getattr(latest_response, "containment_action", None)
        car.register_pap = car.preventive_action or getattr(latest_response, "preventive_action", None)
        car.auditor_name = getattr(auditor_user, "full_name", None) or getattr(auditor_user, "email", None)
        car.requested_by_name = getattr(requested_user, "full_name", None) or getattr(requested_user, "email", None)
        car.responsible_department = getattr(department, "name", None) or getattr(department, "code", None)
        car.responsible_personnel = getattr(assigned_user, "full_name", None) or getattr(assigned_user, "email", None) or car.submitted_by_name
        car.car_category_limit = _quality_car_value(getattr(finding, "level", None)).upper() or _quality_car_title(car.priority)
        car.car_sequence_no = str(len([candidate for candidate in cars if getattr(candidate, "audit_ref", None) == getattr(car, "audit_ref", None) and candidate.created_at <= car.created_at])) if getattr(car, "audit_ref", None) and car.created_at else None

    return cars


def _quality_car_register_query(
    db: Session,
    current_user: account_models.User,
    program: Optional[models.CARProgram] = None,
    status_: Optional[models.CARStatus] = None,
    assigned_to_user_id: Optional[str] = None,
    audit_id: Optional[UUID] = None,
    search: Optional[str] = None,
):
    qs = (
        db.query(models.CorrectiveActionRequest)
        .outerjoin(models.QMSAuditFinding, models.QMSAuditFinding.id == models.CorrectiveActionRequest.finding_id)
        .outerjoin(models.QMSAudit, models.QMSAudit.id == models.QMSAuditFinding.audit_id)
        .filter(models.CorrectiveActionRequest.amo_id == _current_amo_id(current_user))
    )
    if program:
        qs = qs.filter(models.CorrectiveActionRequest.program == program)
    if status_:
        qs = qs.filter(models.CorrectiveActionRequest.status == status_)
    if assigned_to_user_id:
        qs = qs.filter(models.CorrectiveActionRequest.assigned_to_user_id == assigned_to_user_id)
    if audit_id:
        qs = qs.filter(models.QMSAuditFinding.audit_id == audit_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        qs = qs.filter(
            or_(
                models.CorrectiveActionRequest.car_number.ilike(like),
                models.CorrectiveActionRequest.title.ilike(like),
                models.CorrectiveActionRequest.summary.ilike(like),
                models.CorrectiveActionRequest.root_cause_text.ilike(like),
                models.CorrectiveActionRequest.capa_text.ilike(like),
                models.CorrectiveActionRequest.preventive_action.ilike(like),
                models.CorrectiveActionRequest.submitted_by_name.ilike(like),
                models.QMSAuditFinding.finding_ref.ilike(like),
                models.QMSAuditFinding.description.ilike(like),
                models.QMSAudit.audit_ref.ilike(like),
                models.QMSAudit.title.ilike(like),
            )
        )
    return qs


@router.post("/cars", response_model=CAROut, status_code=status.HTTP_201_CREATED)
def create_car_request(
    payload: CARCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_quality_scheduler(current_user)
    _require_car_write_access(db, current_user, payload.finding_id)
    finding = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.id == payload.finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if finding.finding_type != models.QMSFindingType.NON_CONFORMITY:
        raise HTTPException(status_code=400, detail="CARs may only be issued for non-conformity findings")
    existing_car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.finding_id == payload.finding_id).first()
    if existing_car:
        raise HTTPException(status_code=409, detail="A CAR already exists for this finding")
    try:
        car = create_car(
            db=db,
            program=payload.program,
            title=payload.title.strip(),
            summary=payload.summary.strip(),
            priority=payload.priority,
            requested_by_user_id=get_actor(),
            assigned_to_user_id=payload.assigned_to_user_id,
            due_date=payload.due_date,
            target_closure_date=payload.target_closure_date,
            finding_id=payload.finding_id,
            amo_id=_current_amo_id(current_user),
        )
        car.evidence_required = payload.evidence_required
        _seed_car_reminders(db, car)
        invite_url = build_car_invite_link(car, request_origin=_public_request_origin(request))
        if car.assigned_to_user_id:
            _notify_user(
                db,
                car.assigned_to_user_id,
                f"CAR {car.car_number} assigned to you. Submit response.",
                models.QMSNotificationSeverity.ACTION_REQUIRED,
                action_url=invite_url,
                action_label="Open CAR response",
                entity_type="car",
                entity_id=car.id,
            )
        audit = getattr(finding, "audit", None)
        if audit and _normalized_email(getattr(audit, "auditee_email", None)):
            _send_notice_email(
                db,
                amo_id=_current_amo_id(current_user),
                template_key="qms_car_auditee_invite",
                recipient=audit.auditee_email,
                subject=f"CAR/CAPA response required · {car.car_number}",
                context={
                    "car_number": car.car_number,
                    "title": car.title,
                    "summary": car.summary,
                    "priority": car.priority.value if hasattr(car.priority, "value") else str(car.priority),
                    "due_date": car.due_date.isoformat() if car.due_date else None,
                    "audit_ref": getattr(audit, "audit_ref", None),
                    "audit_title": getattr(audit, "title", None),
                    "auditee": getattr(audit, "auditee", None),
                    "invite_url": invite_url,
                },
                correlation_id=str(car.id),
            )
        audit_services.log_event(
            db,
            amo_id=current_user.amo_id,
            actor_user_id=current_user.id,
            entity_type="qms_car",
            entity_id=str(car.id),
            action="create",
            after={"car_number": car.car_number, "status": car.status.value},
            correlation_id=str(uuid.uuid4()),
            metadata=_audit_metadata(request),
        )
        db.commit()
        db.refresh(car)
        return car
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            raise HTTPException(
                status_code=503,
                detail="CARs are unavailable because the database schema is missing. Run alembic upgrade heads.",
            ) from exc
        raise


@router.get("/cars", response_model=List[CAROut])
def list_cars(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
    program: Optional[models.CARProgram] = None,
    status_: Optional[models.CARStatus] = None,
    assigned_to_user_id: Optional[str] = None,
    audit_id: Optional[UUID] = None,
    limit: int = Query(default=500, ge=1, le=1000),
):
    try:
        qs = db.query(models.CorrectiveActionRequest).filter(
            models.CorrectiveActionRequest.amo_id == _current_amo_id(current_user)
        )
        if program:
            qs = qs.filter(models.CorrectiveActionRequest.program == program)
        if status_:
            qs = qs.filter(models.CorrectiveActionRequest.status == status_)
        if assigned_to_user_id:
            qs = qs.filter(models.CorrectiveActionRequest.assigned_to_user_id == assigned_to_user_id)
        if audit_id:
            qs = qs.join(models.QMSAuditFinding, models.QMSAuditFinding.id == models.CorrectiveActionRequest.finding_id).filter(models.QMSAuditFinding.audit_id == audit_id)
        cars = qs.order_by(models.CorrectiveActionRequest.created_at.desc()).limit(limit).all()
        return _decorate_car_register_items(db, cars)
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            return []
        raise




@router.get("/cars/register", response_model=CARRegisterResponse)
def list_car_register(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
    program: Optional[models.CARProgram] = None,
    status_: Optional[models.CARStatus] = None,
    assigned_to_user_id: Optional[str] = None,
    audit_id: Optional[UUID] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Spreadsheet-ready corrective action register.

    The classic `/quality/cars` endpoint remains a lightweight list. This route
    returns enriched server-derived context so the UI can render the full CAR
    index without guessing audit/finding/personnel details from text labels.
    """
    try:
        qs = _quality_car_register_query(
            db=db,
            current_user=current_user,
            program=program,
            status_=status_,
            assigned_to_user_id=assigned_to_user_id,
            audit_id=audit_id,
            search=search,
        )
        total = qs.count()
        items = (
            qs.order_by(models.QMSAudit.audit_ref.asc().nullslast(), models.CorrectiveActionRequest.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return CARRegisterResponse(
            items=_decorate_car_register_items(db, items),
            total=total,
            limit=limit,
            offset=offset,
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            return CARRegisterResponse(items=[], total=0, limit=limit, offset=offset)
        raise

@router.get("/cars/assignees", response_model=List[CARAssigneeOut])
def list_car_assignees(
    db: Session = Depends(get_db),
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    current_user: account_models.User = Depends(get_current_active_user),
):
    q = (
        db.query(account_models.User, account_models.Department)
        .outerjoin(account_models.Department, account_models.User.department_id == account_models.Department.id)
        .filter(account_models.User.amo_id == current_user.amo_id)
        .filter(account_models.User.is_active.is_(True))
    )
    if department_id:
        q = q.filter(account_models.User.department_id == department_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(
            (account_models.User.full_name.ilike(like))
            | (account_models.User.email.ilike(like))
            | (account_models.User.staff_code.ilike(like))
        )
    q = q.order_by(account_models.User.full_name.asc())
    results = []
    for user, dept in q.all():
        results.append(
            CARAssigneeOut(
                id=user.id,
                full_name=user.full_name,
                email=user.email,
                staff_code=user.staff_code,
                role=user.role,
                department_id=user.department_id,
                department_code=dept.code if dept else None,
                department_name=dept.name if dept else None,
            )
        )
    return results


@router.patch("/cars/{car_id}", response_model=CAROut)
def update_car(
    car_id: UUID,
    payload: CARUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_not_escalated(car)
    before = {"status": car.status.value, "title": car.title}
    is_assignee = current_user.id == car.assigned_to_user_id
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=is_assignee)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return car

    previous_assignee = car.assigned_to_user_id
    changed_status = False
    assignee_allowed = {
        "root_cause",
        "corrective_action",
        "preventive_action",
        "target_closure_date",
    }

    if is_assignee and not _is_quality_admin(current_user) and not _audit_allows_user(
        db, car.finding_id, current_user.id
    ):
        disallowed = set(data) - assignee_allowed
        if disallowed:
            raise HTTPException(
                status_code=403,
                detail="Assignees may only update root cause, CAP/PAP, or request extra time.",
            )
        if "target_closure_date" in data:
            requested_date = data["target_closure_date"]
            if requested_date is None or not _assignee_can_request_extension(db, car, requested_date):
                raise HTTPException(
                    status_code=403,
                    detail="Additional time can only be requested when exceeding the level due date.",
                )
            car.target_closure_date = requested_date
            add_car_action(
                db=db,
                car=car,
                action_type=models.CARActionType.COMMENT,
                message=f"Assignee requested extension to {requested_date.isoformat()}",
                actor_user_id=get_actor(),
            )
        updated_fields = {}
        for field in ("root_cause", "corrective_action", "preventive_action"):
            if field in data:
                setattr(car, field, data[field])
                updated_fields[field] = data[field]
        if updated_fields:
            response = models.CARResponse(
                car_id=car.id,
                containment_action=car.containment_action,
                root_cause=car.root_cause,
                corrective_action=car.corrective_action,
                preventive_action=car.preventive_action,
                evidence_ref=car.evidence_ref,
                submitted_by_name=current_user.full_name,
                submitted_by_email=current_user.email,
                status=models.CARResponseStatus.SUBMITTED,
            )
            db.add(response)
    else:
        for field, val in data.items():
            if field == "status":
                changed_status = True
                car_transitions.transition_car(
                    db,
                    amo_id=str(current_user.amo_id),
                    actor_user_id=str(current_user.id),
                    car=car,
                    target_status=str(val.value if hasattr(val, "value") else val),
                    evidence_ref=(data.get("evidence_ref") or car.evidence_ref),
                )
                continue
            setattr(car, field, val)

    if changed_status:
        add_car_action(
            db=db,
            car=car,
            action_type=models.CARActionType.STATUS_CHANGE,
            message=f"Status changed to {car.status}",
            actor_user_id=get_actor(),
        )

    if "assigned_to_user_id" in data and car.assigned_to_user_id != previous_assignee:
        if car.assigned_to_user_id:
            invite_url = build_car_invite_link(car, request_origin=_public_request_origin(request))
            _notify_user(
                db,
                car.assigned_to_user_id,
                f"CAR {car.car_number} assigned to you. Submit response.",
                models.QMSNotificationSeverity.ACTION_REQUIRED,
                action_url=invite_url,
                action_label="Open CAR response",
                entity_type="car",
                entity_id=car.id,
            )

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="update",
        before=before,
        after={"status": car.status.value},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=changed_status and car.status in (models.CARStatus.CLOSED, models.CARStatus.CANCELLED),
    )
    db.commit()
    db.refresh(car)
    return car


@router.delete("/cars/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car(
    car_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_not_escalated(car)
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="delete",
        before={"status": car.status.value, "car_number": car.car_number},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    _require_car_write_access(db, current_user, car.finding_id, car=car)
    db.delete(car)
    db.commit()
    return None


@router.get("/cars/{car_id}/print", response_class=FileResponse)
def print_car_form(
    car_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)

    assigned_name = None
    requested_name = None
    if car.assigned_to_user_id:
        assigned_user = (
            db.query(account_models.User)
            .filter(account_models.User.id == car.assigned_to_user_id)
            .first()
        )
        assigned_name = assigned_user.full_name if assigned_user else None
    if car.requested_by_user_id:
        requested_user = (
            db.query(account_models.User)
            .filter(account_models.User.id == car.requested_by_user_id)
            .first()
        )
        requested_name = requested_user.full_name if requested_user else None

    try:
        file_path = generate_car_form_pdf(
            car=car,
            invite_url=build_car_invite_link(car, request_origin=_public_request_origin(request)),
            requested_by_name=requested_name,
            assigned_to_name=assigned_name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="export",
        after={"format": "pdf", "car_number": car.car_number},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.commit()

    return FileResponse(
        path=file_path,
        filename=f"{car.car_number}.pdf",
        media_type="application/pdf",
    )


@router.get("/cars/{car_id}/evidence-pack")
def export_car_evidence_pack(
    car_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)
    return build_evidence_pack(
        "qms_car",
        car_id,
        db,
        actor_user_id=current_user.id,
        correlation_id=str(uuid.uuid4()),
        amo_id=current_user.amo_id,
    )


@router.post("/cars/{car_id}/escalate", response_model=CAROut)
def escalate_car(
    car_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car)
    if car.status == models.CARStatus.ESCALATED:
        raise HTTPException(status_code=409, detail="CAR is already escalated")

    car.status = models.CARStatus.ESCALATED
    car.escalated_at = func.now()
    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.ESCALATION,
        message="Escalated due to inactivity or overdue status",
        actor_user_id=get_actor(),
    )
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="escalate",
        after={"status": car.status.value, "escalated_at": str(car.escalated_at)},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
        critical=True,
    )
    db.commit()
    db.refresh(car)
    return car


@router.post("/cars/{car_id}/reminders", response_model=CAROut)
def reschedule_car_reminder(
    car_id: UUID,
    request: Request,
    reminder_interval_days: int = 7,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_not_escalated(car)
    _require_car_write_access(db, current_user, car.finding_id, car=car)
    if reminder_interval_days < 1 or reminder_interval_days > 90:
        raise HTTPException(status_code=400, detail="Reminder interval must be between 1 and 90 days")
    schedule_next_reminder(car, reminder_interval_days)
    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.REMINDER,
        message=f"Reminder window set to every {reminder_interval_days} days",
        actor_user_id=get_actor(),
    )
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="update_reminder",
        after={
            "reminder_interval_days": car.reminder_interval_days,
            "next_reminder_at": str(car.next_reminder_at),
        },
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(car)
    return car


def _public_request_origin(request: Request | None) -> Optional[str]:
    if request is None:
        return None
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_host:
        return f"{forwarded_proto or request.url.scheme}://{forwarded_host}"
    return str(request.base_url).rstrip("/")


CAR_INVITE_MAX_SUBMISSIONS = 2
CAR_INVITE_REVIEW_OPENED_PREFIX = "Auditor opened submitted CAR response"
CAR_INVITE_RECALLED_PREFIX = "Auditee recalled CAR response"


def _car_invite_responses(db: Session, car_id: UUID) -> list[models.CARResponse]:
    return (
        db.query(models.CARResponse)
        .filter(models.CARResponse.car_id == car_id)
        .order_by(models.CARResponse.submitted_at.desc())
        .all()
    )


def _car_invite_latest_response(db: Session, car_id: UUID) -> Optional[models.CARResponse]:
    return (
        db.query(models.CARResponse)
        .filter(models.CARResponse.car_id == car_id)
        .order_by(models.CARResponse.submitted_at.desc())
        .first()
    )


def _car_invite_latest_active_response(db: Session, car_id: UUID) -> Optional[models.CARResponse]:
    return _latest_reviewable_car_response(db, car_id)


def _latest_action_at_after(
    db: Session,
    car_id: UUID,
    message_prefix: str,
    since: Optional[datetime],
) -> Optional[datetime]:
    query = (
        db.query(func.max(models.CARActionLog.created_at))
        .filter(
            models.CARActionLog.car_id == car_id,
            models.CARActionLog.message.ilike(f"{message_prefix}%"),
        )
    )
    if since is not None:
        query = query.filter(models.CARActionLog.created_at >= since)
    return query.scalar()


def _car_response_was_recalled(db: Session, car_id: UUID, response: Optional[models.CARResponse]) -> bool:
    if response is None:
        return False
    return _latest_action_at_after(db, car_id, CAR_INVITE_RECALLED_PREFIX, response.submitted_at) is not None


def _car_submission_was_opened(db: Session, car_id: UUID, response: Optional[models.CARResponse]) -> bool:
    if response is None:
        return False
    return _latest_action_at_after(db, car_id, CAR_INVITE_REVIEW_OPENED_PREFIX, response.submitted_at) is not None


def _car_has_evidence(db: Session, car: models.CorrectiveActionRequest) -> bool:
    if (car.evidence_ref or "").strip():
        return True
    return db.query(models.CARAttachment.id).filter(models.CARAttachment.car_id == car.id).first() is not None


def _car_submission_attempt_count(db: Session, car_id: UUID) -> int:
    # Count only responses that were actually left for auditor action. A recalled-before-open response
    # is removed in recall_car_invite_submission, so it does not consume an attempt.
    return db.query(models.CARResponse).filter(models.CARResponse.car_id == car_id).count()


def _latest_reviewable_car_response(db: Session, car_id: UUID) -> Optional[models.CARResponse]:
    latest = _car_invite_latest_response(db, car_id)
    if latest is None or _car_response_was_recalled(db, car_id, latest):
        return None
    return latest


def _mark_audit_in_progress_or_cap_open(db: Session, car: models.CorrectiveActionRequest) -> None:
    if not getattr(car, "finding_id", None):
        return
    audit = (
        db.query(models.QMSAudit)
        .join(models.QMSAuditFinding, models.QMSAuditFinding.audit_id == models.QMSAudit.id)
        .filter(models.QMSAuditFinding.id == car.finding_id)
        .first()
    )
    if audit and audit.status not in {models.QMSAuditStatus.CLOSED, models.QMSAuditStatus.CAP_OPEN}:
        audit.status = models.QMSAuditStatus.CAP_OPEN


def _sync_car_review_state(db: Session, car: models.CorrectiveActionRequest, *, actor_user_id: Optional[str]) -> tuple[models.CARStatus, str]:
    """Apply the CAR state machine after auditee submission, recall, evidence changes, or review.

    This is intentionally centralised so the audit workspace, CAR register, invite page, and
    workflow-check cannot disagree about the same CAR/finding state.
    """
    if car.status in {models.CARStatus.CLOSED, models.CARStatus.ESCALATED, models.CARStatus.CANCELLED}:
        return car.status, "locked"

    has_evidence = _car_has_evidence(db, car)
    latest = _latest_reviewable_car_response(db, car.id)

    if car.root_cause_status == "REJECTED" or car.capa_status == "REJECTED":
        if latest is not None:
            latest.status = models.CARResponseStatus.CAP_REJECTED
        car.status = models.CARStatus.IN_PROGRESS
        _mark_audit_in_progress_or_cap_open(db, car)
        return car.status, "returned"

    if car.root_cause_status == "ACCEPTED" and car.capa_status == "NEEDS_EVIDENCE":
        if latest is not None:
            latest.status = models.CARResponseStatus.ROOT_CAUSE_ACCEPTED
        car.status = models.CARStatus.IN_PROGRESS
        _mark_audit_in_progress_or_cap_open(db, car)
        return car.status, "needs_evidence"

    if car.root_cause_status == "ACCEPTED" and car.capa_status == "ACCEPTED":
        if latest is not None:
            latest.status = models.CARResponseStatus.CAP_ACCEPTED
        if car.evidence_required and not has_evidence:
            car.status = models.CARStatus.IN_PROGRESS
            _mark_audit_in_progress_or_cap_open(db, car)
            return car.status, "accepted_pending_evidence"
        _close_accepted_car_workflow(db, car, actor_user_id=actor_user_id)
        return car.status, "closed"

    if latest is not None or car.submitted_at:
        car.status = models.CARStatus.PENDING_VERIFICATION
        _mark_audit_in_progress_or_cap_open(db, car)
        return car.status, "submitted"

    if car.status == models.CARStatus.DRAFT:
        car.status = models.CARStatus.OPEN
    _mark_audit_in_progress_or_cap_open(db, car)
    return car.status, "open"


def _car_invite_state(db: Session, car: models.CorrectiveActionRequest) -> dict[str, Any]:
    responses = _car_invite_responses(db, car.id)
    attempts = _car_submission_attempt_count(db, car.id)
    latest = _latest_reviewable_car_response(db, car.id)
    latest_submitted_at = latest.submitted_at if latest is not None else car.submitted_at
    review_opened_at = _latest_action_at_after(db, car.id, CAR_INVITE_REVIEW_OPENED_PREFIX, latest_submitted_at)
    closed_statuses = {models.CARStatus.CLOSED, models.CARStatus.ESCALATED, models.CARStatus.CANCELLED}
    locked_reason: Optional[str] = None
    if car.status == models.CARStatus.CLOSED:
        locked_reason = "This CAR is closed. No further changes are allowed."
    elif car.status == models.CARStatus.ESCALATED:
        locked_reason = "This CAR has been escalated and is view-only."
    elif car.status == models.CARStatus.CANCELLED:
        locked_reason = "This CAR has been cancelled."

    active_submission = bool(latest and car.status == models.CARStatus.PENDING_VERIFICATION)
    if active_submission and review_opened_at is not None:
        locked_reason = locked_reason or "The auditor has opened this submission for review. It is read-only until returned."
    elif active_submission:
        locked_reason = locked_reason or "This response has been submitted. You may recall it until the auditor opens it."
    elif attempts >= CAR_INVITE_MAX_SUBMISSIONS and car.status not in closed_statuses:
        locked_reason = locked_reason or "The maximum number of CAR submissions has been reached. Contact the audit team."

    can_recall = bool(active_submission and review_opened_at is None and car.status not in closed_statuses)
    can_edit = bool(car.status not in closed_statuses and not active_submission and attempts < CAR_INVITE_MAX_SUBMISSIONS)
    can_submit = can_edit
    return {
        "submission_count": attempts,
        "remaining_submissions": max(CAR_INVITE_MAX_SUBMISSIONS - attempts, 0),
        "latest_submission_at": latest_submitted_at,
        "review_opened_at": review_opened_at,
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_recall": can_recall,
        "locked_reason": locked_reason,
    }


def _require_public_car_invite_editable(db: Session, car: models.CorrectiveActionRequest) -> None:
    state = _car_invite_state(db, car)
    if not state["can_edit"]:
        raise HTTPException(status_code=409, detail=state["locked_reason"] or "This CAR invite is not editable.")


def _serialize_car_response(
    db: Session,
    car_id: UUID,
    response: models.CARResponse,
    *,
    is_latest: bool = False,
) -> dict[str, Any]:
    review_opened_at = _latest_action_at_after(db, car_id, CAR_INVITE_REVIEW_OPENED_PREFIX, response.submitted_at)
    recalled_at = _latest_action_at_after(db, car_id, CAR_INVITE_RECALLED_PREFIX, response.submitted_at)
    return {
        "id": response.id,
        "car_id": response.car_id,
        "containment_action": response.containment_action,
        "root_cause": response.root_cause,
        "corrective_action": response.corrective_action,
        "preventive_action": response.preventive_action,
        "evidence_ref": response.evidence_ref,
        "submitted_by_name": response.submitted_by_name,
        "submitted_by_email": response.submitted_by_email,
        "submitted_at": response.submitted_at,
        "status": str(response.status.value if hasattr(response.status, "value") else response.status),
        "is_latest": is_latest,
        "review_opened_at": review_opened_at,
        "recalled_at": recalled_at,
    }


def _car_invite_payload(car: models.CorrectiveActionRequest, request: Request | None = None, db: Optional[Session] = None) -> dict[str, Any]:
    finding = getattr(car, "finding", None)
    audit = getattr(finding, "audit", None) if finding is not None else None
    request_origin = _public_request_origin(request)
    url = build_car_invite_link(car, request_origin=request_origin)
    state = _car_invite_state(db, car) if db is not None else {
        "submission_count": 0,
        "remaining_submissions": CAR_INVITE_MAX_SUBMISSIONS,
        "latest_submission_at": getattr(car, "submitted_at", None),
        "review_opened_at": None,
        "can_edit": car.status not in {models.CARStatus.CLOSED, models.CARStatus.ESCALATED, models.CARStatus.CANCELLED},
        "can_submit": car.status not in {models.CARStatus.CLOSED, models.CARStatus.ESCALATED, models.CARStatus.CANCELLED},
        "can_recall": False,
        "locked_reason": None,
    }
    related_cars: list[dict[str, Any]] = []
    if db is not None and getattr(car, "finding_id", None):
        related_query = (
            db.query(models.CorrectiveActionRequest, models.QMSAuditFinding)
            .join(models.QMSAuditFinding, models.QMSAuditFinding.id == models.CorrectiveActionRequest.finding_id)
            .filter(models.QMSAuditFinding.audit_id == getattr(finding, "audit_id", None))
        )
        if getattr(car, "assigned_to_user_id", None):
            related_query = related_query.filter(models.CorrectiveActionRequest.assigned_to_user_id == car.assigned_to_user_id)
        else:
            related_query = related_query.filter(models.CorrectiveActionRequest.id == car.id)
        for related_car, related_finding in related_query.order_by(models.CorrectiveActionRequest.created_at.asc()).limit(25).all():
            related_cars.append({
                "car_id": related_car.id,
                "invite_token": related_car.invite_token,
                "car_number": related_car.car_number,
                "title": related_car.title,
                "finding_ref": getattr(related_finding, "finding_ref", None),
                "finding_description": getattr(related_finding, "description", None),
                "status": related_car.status,
                "due_date": related_car.due_date,
                "priority": related_car.priority,
            })
    return {
        "car_id": car.id,
        "invite_token": car.invite_token,
        "invite_url": url,
        "car_form_download_url": f"/quality/cars/invite/{car.invite_token}/form",
        "next_reminder_at": car.next_reminder_at,
        "car_number": car.car_number,
        "title": car.title,
        "summary": car.summary,
        "priority": car.priority,
        "status": car.status,
        "due_date": car.due_date,
        "target_closure_date": car.target_closure_date,
        "evidence_required": bool(getattr(car, "evidence_required", True)),
        "evidence_received_at": getattr(car, "evidence_received_at", None),
        "evidence_verified_at": getattr(car, "evidence_verified_at", None),
        "submitted_at": getattr(car, "submitted_at", None),
        "containment_action": getattr(car, "containment_action", None),
        "root_cause": getattr(car, "root_cause", None) or getattr(car, "root_cause_text", None),
        "corrective_action": getattr(car, "corrective_action", None) or getattr(car, "capa_text", None),
        "preventive_action": getattr(car, "preventive_action", None),
        "evidence_ref": getattr(car, "evidence_ref", None),
        "submitted_by_name": getattr(car, "submitted_by_name", None),
        "submitted_by_email": getattr(car, "submitted_by_email", None),
        "root_cause_status": getattr(car, "root_cause_status", None),
        "capa_status": getattr(car, "capa_status", None),
        "root_cause_review_note": getattr(car, "root_cause_review_note", None),
        "capa_review_note": getattr(car, "capa_review_note", None),
        "finding_id": getattr(finding, "id", None),
        "finding_ref": getattr(finding, "finding_ref", None),
        "finding_description": getattr(finding, "description", None),
        "audit_id": getattr(audit, "id", None),
        "audit_ref": getattr(audit, "audit_ref", None),
        "audit_title": getattr(audit, "title", None),
        "auditee": getattr(audit, "auditee", None),
        "auditee_email": getattr(audit, "auditee_email", None),
        "related_cars": related_cars,
        **state,
    }


@router.get("/cars/{car_id}/invite", response_model=CARInviteOut)
def get_car_invite(car_id: UUID, request: Request, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    return _car_invite_payload(car, request=request, db=db)


@public_router.get("/cars/invite/{invite_token}", response_model=CARInviteOut)
def get_car_invite_by_token(invite_token: str, request: Request, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    return _car_invite_payload(car, request=request, db=db)


def _limit_car_invite_text(value: object, *, max_length: int = 500) -> object:
    if isinstance(value, str):
        return value.strip()[:max_length]
    return value


@public_router.patch("/cars/invite/{invite_token}", response_model=CAROut)
def submit_car_from_invite(invite_token: str, payload: CARInviteUpdate, request: Request, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    _require_public_car_invite_editable(db, car)

    text_fields = {
        "containment_action",
        "root_cause",
        "corrective_action",
        "preventive_action",
        "evidence_ref",
        "root_cause_text",
        "capa_text",
    }
    for field in (
        "containment_action",
        "root_cause",
        "corrective_action",
        "preventive_action",
        "evidence_ref",
        "target_closure_date",
        "due_date",
        "submitted_by_name",
        "submitted_by_email",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(car, field, _limit_car_invite_text(val) if field in text_fields else val)

    if payload.root_cause_text is not None:
        car.root_cause_text = _limit_car_invite_text(payload.root_cause_text)
    if payload.capa_text is not None:
        car.capa_text = _limit_car_invite_text(payload.capa_text)

    if not (car.root_cause_text or car.root_cause):
        raise HTTPException(status_code=400, detail="Root cause is required for CAR response")
    if not (car.capa_text or car.corrective_action):
        raise HTTPException(status_code=400, detail="CAPA is required for CAR response")

    attachment_count = db.query(models.CARAttachment).filter(models.CARAttachment.car_id == car.id).count()
    if car.evidence_required and not car.evidence_ref and attachment_count == 0:
        raise HTTPException(status_code=400, detail="Evidence is required before submitting CAR response")

    # If the previous submission was recalled before auditor review, remove it so the
    # corrected submission replaces it. That keeps the review queue clean and prevents
    # the same CAR from appearing twice.
    latest_existing = _car_invite_latest_response(db, car.id)
    if latest_existing is not None and _car_response_was_recalled(db, car.id, latest_existing) and not _car_submission_was_opened(db, car.id, latest_existing):
        db.delete(latest_existing)
        db.flush()

    submitted_at = datetime.now(timezone.utc)
    car.submitted_at = submitted_at
    car.root_cause_status = "SUBMITTED"
    car.capa_status = "SUBMITTED"
    if _car_has_evidence(db, car):
        car.evidence_received_at = submitted_at

    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.COMMENT,
        message="Auditee submitted CAR response via invite link",
        actor_user_id=None,
    )

    response = models.CARResponse(
        car_id=car.id,
        containment_action=car.containment_action,
        root_cause=car.root_cause_text or car.root_cause,
        corrective_action=car.capa_text or car.corrective_action,
        preventive_action=car.preventive_action,
        evidence_ref=car.evidence_ref,
        submitted_by_name=car.submitted_by_name,
        submitted_by_email=car.submitted_by_email,
        submitted_at=submitted_at,
        status=models.CARResponseStatus.SUBMITTED,
    )
    db.add(response)
    db.flush()
    _sync_car_review_state(db, car, actor_user_id=None)

    if car.finding_id:
        audit = (
            db.query(models.QMSAudit)
            .join(models.QMSAuditFinding)
            .filter(models.QMSAuditFinding.id == car.finding_id)
            .first()
        )
    else:
        audit = None

    note_msg = f"CAR response submitted for {car.car_number} ({car.title})."
    audit_action_url = _audit_workspace_notification_url(db, audit, tab="cars", car_id=car.id)
    invite_action_url = _safe_notification_action_url(build_car_invite_link(car, request_origin=_public_request_origin(request)))
    if audit:
        note_msg = f"{note_msg} Audit {audit.audit_ref}."
        for auditor_id in (
            audit.lead_auditor_user_id,
            audit.observer_auditor_user_id,
            audit.assistant_auditor_user_id,
        ):
            _notify_user(
                db,
                auditor_id,
                note_msg,
                models.QMSNotificationSeverity.ACTION_REQUIRED,
                action_url=audit_action_url,
                action_label="Review response",
                entity_type="car",
                entity_id=car.id,
            )
    _notify_user(
        db,
        car.assigned_to_user_id,
        f"Your CAR response was submitted for {car.car_number}. You may recall it until the auditor opens it.",
        models.QMSNotificationSeverity.ACTION_REQUIRED,
        action_url=invite_action_url,
        action_label="Open / recall submission",
        entity_type="car",
        entity_id=car.id,
    )

    db.commit()
    db.refresh(car)
    return car


@public_router.post("/cars/invite/{invite_token}/recall", response_model=CARInviteOut)
def recall_car_invite_submission(invite_token: str, request: Request, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    state = _car_invite_state(db, car)
    if not state["can_recall"]:
        raise HTTPException(status_code=409, detail=state["locked_reason"] or "This submission can no longer be recalled.")

    latest = _car_invite_latest_response(db, car.id)
    if latest is not None and not _car_submission_was_opened(db, car.id, latest):
        db.delete(latest)
        db.flush()

    car.status = models.CARStatus.IN_PROGRESS
    car.submitted_at = None
    car.root_cause_status = "PENDING"
    car.capa_status = "PENDING"
    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.COMMENT,
        message=f"{CAR_INVITE_RECALLED_PREFIX} before auditor review",
        actor_user_id=None,
    )
    audit = None
    if car.finding_id:
        audit = (
            db.query(models.QMSAudit)
            .join(models.QMSAuditFinding)
            .filter(models.QMSAuditFinding.id == car.finding_id)
            .first()
        )
    audit_action_url = _audit_workspace_notification_url(db, audit, tab="cars", car_id=car.id)
    if audit:
        recall_msg = f"CAR response recalled for {car.car_number} ({car.title}). Audit {audit.audit_ref}."
        for auditor_id in (
            audit.lead_auditor_user_id,
            audit.observer_auditor_user_id,
            audit.assistant_auditor_user_id,
        ):
            _notify_user(
                db,
                auditor_id,
                recall_msg,
                models.QMSNotificationSeverity.WARNING,
                action_url=audit_action_url,
                action_label="Open CAR review",
                entity_type="car",
                entity_id=car.id,
            )
    _notify_user(
        db,
        car.assigned_to_user_id,
        f"Submission recalled for {car.car_number}. You can update the response and submit again.",
        models.QMSNotificationSeverity.INFO,
        action_url=_safe_notification_action_url(build_car_invite_link(car, request_origin=_public_request_origin(request))),
        action_label="Continue response",
        entity_type="car",
        entity_id=car.id,
    )
    db.commit()
    db.refresh(car)
    return _car_invite_payload(car, request=request, db=db)


@public_router.get("/cars/invite/{invite_token}/attachments", response_model=List[CARAttachmentOut])
def list_car_invite_attachments(invite_token: str, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    return [_serialize_attachment(invite_token, attachment) for attachment in car.attachments]


@public_router.post(
    "/cars/invite/{invite_token}/attachments",
    response_model=CARAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_car_invite_attachment(
    invite_token: str,
    file: UploadFile = File(...),
    description: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    _require_public_car_invite_editable(db, car)

    target_path, original_name, sha256, size_bytes = _store_car_attachment(car.id, file)

    clean_description = (description or "").strip()[:500] or None
    attachment = models.CARAttachment(
        car_id=car.id,
        filename=original_name,
        description=clean_description,
        file_ref=str(target_path),
        content_type=file.content_type,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    db.add(attachment)
    car.evidence_received_at = func.now()
    db.commit()
    db.refresh(attachment)
    return _serialize_attachment(invite_token, attachment)


@public_router.patch(
    "/cars/invite/{invite_token}/attachments/{attachment_id}",
    response_model=CARAttachmentOut,
)
def update_car_invite_attachment(
    invite_token: str,
    attachment_id: UUID,
    payload: CARAttachmentUpdate,
    db: Session = Depends(get_db),
):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    _require_public_car_invite_editable(db, car)
    attachment = (
        db.query(models.CARAttachment)
        .filter(models.CARAttachment.id == attachment_id, models.CARAttachment.car_id == car.id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    attachment.description = (payload.description or "").strip()[:500] or None
    db.commit()
    db.refresh(attachment)
    return _serialize_attachment(invite_token, attachment)


@public_router.delete(
    "/cars/invite/{invite_token}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_car_invite_attachment(
    invite_token: str,
    attachment_id: UUID,
    db: Session = Depends(get_db),
):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    _require_public_car_invite_editable(db, car)
    attachment = (
        db.query(models.CARAttachment)
        .filter(models.CARAttachment.id == attachment_id, models.CARAttachment.car_id == car.id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        Path(attachment.file_ref).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(attachment)
    remaining_attachment = (
        db.query(models.CARAttachment.id)
        .filter(models.CARAttachment.car_id == car.id, models.CARAttachment.id != attachment_id)
        .first()
    )
    if not remaining_attachment and not car.evidence_ref:
        car.evidence_received_at = None
    db.commit()
    return None


@public_router.get(
    "/cars/invite/{invite_token}/attachments/{attachment_id}/download",
    response_class=FileResponse,
)
def download_car_invite_attachment(
    invite_token: str,
    attachment_id: UUID,
    db: Session = Depends(get_db),
):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    attachment = (
        db.query(models.CARAttachment)
        .filter(
            models.CARAttachment.id == attachment_id,
            models.CARAttachment.car_id == car.id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = Path(attachment.file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing on server.")
    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.content_type or "application/octet-stream",
    )


@public_router.get("/cars/invite/{invite_token}/form", response_class=FileResponse)
def download_car_invite_form(invite_token: str, request: Request, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    try:
        payload = _car_invite_payload(car, request=request, db=db)
        output_path = generate_car_form_pdf(car, invite_url=str(payload.get("invite_url") or ""))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        path=output_path,
        filename=f"{car.car_number}_CAR_form.pdf",
        media_type="application/pdf",
    )


@public_router.get("/cars/invite/{invite_token}/actions", response_model=List[CARActionOut])
def list_car_invite_actions(invite_token: str, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    return (
        db.query(models.CARActionLog)
        .filter(models.CARActionLog.car_id == car.id)
        .order_by(models.CARActionLog.created_at.desc())
        .all()
    )


@router.get("/cars/{car_id}/attachments", response_model=List[CARAttachmentOut])
def list_car_attachments(
    car_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)
    return [
        CARAttachmentOut(
            id=a.id,
            car_id=a.car_id,
            filename=a.filename,
            description=getattr(a, "description", None),
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            sha256=a.sha256,
            uploaded_at=a.uploaded_at,
            download_url=f"/quality/cars/{car.id}/attachments/{a.id}/download",
        )
        for a in car.attachments
    ]


@router.get("/cars/attachments/bulk", response_model=List[CARAttachmentOut])
def list_car_attachments_bulk(
    car_ids: Optional[List[UUID]] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    scoped_amo_id = _current_amo_id(current_user)
    cars_query = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.amo_id == scoped_amo_id)
    if car_ids:
        cars_query = cars_query.filter(models.CorrectiveActionRequest.id.in_(car_ids))
    cars = cars_query.all()
    return [
        CARAttachmentOut(
            id=str(a.id),
            car_id=str(car.id),
            filename=a.filename,
            description=getattr(a, "description", None),
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            sha256=a.sha256,
            uploaded_at=a.uploaded_at,
            download_url=f"/quality/cars/{car.id}/attachments/{a.id}/download",
        )
        for car in cars
        for a in car.attachments
    ]


@router.post("/cars/{car_id}/attachments", response_model=CARAttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_car_attachment(
    car_id: UUID,
    file: UploadFile = File(...),
    description: Optional[str] = Form(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_not_escalated(car)
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)
    target_path, original_name, sha256, size_bytes = _store_car_attachment(car.id, file)
    clean_description = (description or "").strip()[:500] or None
    attachment = models.CARAttachment(
        car_id=car.id,
        filename=original_name,
        description=clean_description,
        file_ref=str(target_path),
        content_type=file.content_type,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    audit_services.log_event(
        db,
        amo_id=car.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car_attachment",
        entity_id=str(attachment.id),
        action="uploaded",
        after={"car_id": str(car.id), "filename": attachment.filename, "sha256": attachment.sha256},
        metadata=_audit_metadata(request) if request else {"module": "quality"},
    )
    db.commit()
    return CARAttachmentOut(
        id=attachment.id,
        car_id=attachment.car_id,
        filename=attachment.filename,
        description=getattr(attachment, "description", None),
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_at=attachment.uploaded_at,
        download_url=f"/quality/cars/{car.id}/attachments/{attachment.id}/download",
    )


@router.get("/cars/{car_id}/attachments/{attachment_id}/download", response_class=FileResponse)
def download_car_attachment(
    car_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)
    attachment = db.query(models.CARAttachment).filter(models.CARAttachment.id == attachment_id, models.CARAttachment.car_id == car.id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = Path(attachment.file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing on server.")
    return FileResponse(path=file_path, filename=attachment.filename, media_type=attachment.content_type or "application/octet-stream")


@router.delete("/cars/{car_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car_attachment(
    car_id: UUID,
    attachment_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_not_escalated(car)
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=False)
    attachment = db.query(models.CARAttachment).filter(models.CARAttachment.id == attachment_id, models.CARAttachment.car_id == car.id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        Path(attachment.file_ref).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(attachment)
    audit_services.log_event(
        db, amo_id=car.amo_id, actor_user_id=current_user.id, entity_type="qms_car_attachment", entity_id=str(attachment_id), action="deleted", metadata=_audit_metadata(request)
    )
    db.commit()
    return None


@router.get("/cars/{car_id}/responses", response_model=List[CARResponseOut])
def list_car_responses_for_review(
    car_id: UUID,
    request: Request,
    mark_open: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_review_access(db, current_user, car)
    latest = _car_invite_latest_active_response(db, car.id) if car.status == models.CARStatus.PENDING_VERIFICATION else None
    responses = [latest] if latest is not None else []
    if mark_open and latest and car.status == models.CARStatus.PENDING_VERIFICATION:
        opened_at = _latest_action_at_after(db, car.id, CAR_INVITE_REVIEW_OPENED_PREFIX, latest.submitted_at)
        if opened_at is None:
            add_car_action(
                db=db,
                car=car,
                action_type=models.CARActionType.COMMENT,
                message=f"{CAR_INVITE_REVIEW_OPENED_PREFIX} by auditor",
                actor_user_id=get_actor(),
            )
            audit_services.log_event(
                db,
                amo_id=current_user.amo_id,
                actor_user_id=current_user.id,
                entity_type="qms_car",
                entity_id=str(car.id),
                action="open_submission_review",
                correlation_id=str(uuid.uuid4()),
                metadata=_audit_metadata(request),
            )
            db.commit()
    return [_serialize_car_response(db, car.id, response, is_latest=True) for response in responses]


def _close_legacy_cap_for_car(
    db: Session,
    car: models.CorrectiveActionRequest,
    *,
    actor_user_id: Optional[str],
    verified_at: datetime,
) -> None:
    if not getattr(car, "finding_id", None):
        return
    cap = (
        db.query(models.QMSCorrectiveAction)
        .filter(models.QMSCorrectiveAction.finding_id == car.finding_id)
        .first()
    )
    if cap is None:
        return
    cap.root_cause = cap.root_cause or car.root_cause_text or car.root_cause
    cap.containment_action = cap.containment_action or car.containment_action
    cap.corrective_action = cap.corrective_action or car.capa_text or car.corrective_action
    cap.preventive_action = cap.preventive_action or car.preventive_action
    cap.evidence_ref = cap.evidence_ref or car.evidence_ref
    cap.verified_at = cap.verified_at or verified_at
    cap.verified_by_user_id = cap.verified_by_user_id or actor_user_id
    cap.status = models.QMSCAPStatus.CLOSED
    cap.updated_by_user_id = actor_user_id


def _close_finding_for_accepted_car(
    db: Session,
    car: models.CorrectiveActionRequest,
    *,
    actor_user_id: Optional[str],
    closed_at: datetime,
) -> None:
    if not getattr(car, "finding_id", None):
        return
    finding = (
        db.query(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.id == car.finding_id)
        .first()
    )
    if finding is None:
        return
    finding.verified_at = finding.verified_at or closed_at
    finding.verified_by_user_id = finding.verified_by_user_id or actor_user_id
    finding.closed_at = finding.closed_at or closed_at
    if car.evidence_ref and not finding.objective_evidence:
        finding.objective_evidence = car.evidence_ref
    try:
        task_services.close_tasks_for_entity(
            db,
            amo_id=car.amo_id,
            entity_type="qms_finding",
            entity_id=str(finding.id),
            actor_user_id=actor_user_id,
        )
    except Exception:
        pass


def _close_accepted_car_workflow(
    db: Session,
    car: models.CorrectiveActionRequest,
    *,
    actor_user_id: Optional[str],
) -> None:
    closed_at = datetime.now(timezone.utc)
    car.status = models.CARStatus.CLOSED
    car.closed_at = car.closed_at or closed_at
    car.evidence_verified_at = car.evidence_verified_at or closed_at
    car.root_cause_status = "ACCEPTED"
    car.capa_status = "ACCEPTED"
    _close_legacy_cap_for_car(db, car, actor_user_id=actor_user_id, verified_at=closed_at)
    _close_finding_for_accepted_car(db, car, actor_user_id=actor_user_id, closed_at=closed_at)
    try:
        task_services.close_tasks_for_entity(
            db,
            amo_id=car.amo_id,
            entity_type="quality_car",
            entity_id=str(car.id),
            actor_user_id=actor_user_id,
        )
        task_services.close_tasks_for_entity(
            db,
            amo_id=car.amo_id,
            entity_type="qms_car",
            entity_id=str(car.id),
            actor_user_id=actor_user_id,
        )
    except Exception:
        pass


@router.post("/cars/{car_id}/review", response_model=CAROut)
def review_car_response(
    car_id: UUID,
    payload: CARReviewUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_not_escalated(car)
    if car.status in {models.CARStatus.CLOSED, models.CARStatus.CANCELLED}:
        raise HTTPException(status_code=423, detail="This CAR is already closed or cancelled and cannot be reviewed again.")
    _require_car_review_access(db, current_user, car)
    if car.status != models.CARStatus.PENDING_VERIFICATION:
        raise HTTPException(status_code=409, detail="This CAR has no submitted response waiting for auditor review.")

    latest_response = _car_invite_latest_active_response(db, car.id)
    if not latest_response:
        raise HTTPException(status_code=404, detail="No active CAR response found for review")

    previous_status = car.status
    note_msg = None

    if payload.root_cause_status:
        if payload.root_cause_status not in {"ACCEPTED", "REJECTED", "SUBMITTED", "PENDING"}:
            raise HTTPException(status_code=400, detail="Invalid root cause review decision")
        if payload.root_cause_status == "REJECTED" and not (payload.root_cause_review_note or "").strip():
            raise HTTPException(status_code=400, detail="Root cause rejection requires a reason note")
        car.root_cause_status = payload.root_cause_status
        car.root_cause_review_note = (payload.root_cause_review_note or "").strip() or None

    if payload.capa_status:
        if payload.capa_status not in {"ACCEPTED", "REJECTED", "NEEDS_EVIDENCE", "SUBMITTED", "PENDING"}:
            raise HTTPException(status_code=400, detail="Invalid CAPA review decision")
        if payload.capa_status in {"REJECTED", "NEEDS_EVIDENCE"} and not (payload.capa_review_note or "").strip():
            raise HTTPException(status_code=400, detail="CAPA rejection/needs evidence requires a reason note")
        car.capa_status = payload.capa_status
        car.capa_review_note = (payload.capa_review_note or "").strip() or None

    _, outcome = _sync_car_review_state(db, car, actor_user_id=get_actor())
    if outcome == "closed":
        note_msg = f"CAR {car.car_number} accepted and closed. The linked finding was verified."
    elif outcome == "accepted_pending_evidence":
        note_msg = f"CAR {car.car_number} response accepted, but evidence is still required before closeout."
    elif outcome == "needs_evidence":
        note_msg = f"CAR {car.car_number} requires more evidence before closeout."
    elif outcome == "returned":
        note_msg = f"CAR {car.car_number} response was returned with review notes."

    if car.status != previous_status:
        add_car_action(
            db=db,
            car=car,
            action_type=models.CARActionType.STATUS_CHANGE,
            message=f"Status changed from {previous_status.value if hasattr(previous_status, 'value') else previous_status} to {car.status.value if hasattr(car.status, 'value') else car.status}",
            actor_user_id=get_actor(),
        )
    elif outcome == "closed":
        add_car_action(
            db=db,
            car=car,
            action_type=models.CARActionType.STATUS_CHANGE,
            message="CAR accepted, evidence verified, and linked finding closed.",
            actor_user_id=get_actor(),
        )

    if payload.message:
        add_car_action(
            db=db,
            car=car,
            action_type=models.CARActionType.COMMENT,
            message=payload.message.strip(),
            actor_user_id=get_actor(),
        )

    if note_msg:
        _notify_user(
            db,
            car.assigned_to_user_id,
            note_msg,
            models.QMSNotificationSeverity.ACTION_REQUIRED,
            action_url=_safe_notification_action_url(build_car_invite_link(car, request_origin=_public_request_origin(request))),
            action_label="Open CAR response",
            entity_type="car",
            entity_id=car.id,
        )

    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="review",
        after={"status": car.status.value},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(car)
    return car


@router.get("/auditors/{user_id}/stats", response_model=AuditorStatsOut)
def get_auditor_stats(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    qs = db.query(models.QMSAudit)
    amo_id = _current_amo_id(current_user)
    if amo_id:
        qs = qs.filter(models.QMSAudit.amo_id == amo_id)
    audits_total = qs.filter(
        (models.QMSAudit.lead_auditor_user_id == user_id)
        | (models.QMSAudit.observer_auditor_user_id == user_id)
        | (models.QMSAudit.assistant_auditor_user_id == user_id)
    ).count()

    audits_open = qs.filter(
        (models.QMSAudit.lead_auditor_user_id == user_id)
        | (models.QMSAudit.observer_auditor_user_id == user_id)
        | (models.QMSAudit.assistant_auditor_user_id == user_id),
        models.QMSAudit.status != models.QMSAuditStatus.CLOSED,
    ).count()

    audits_closed = qs.filter(
        (models.QMSAudit.lead_auditor_user_id == user_id)
        | (models.QMSAudit.observer_auditor_user_id == user_id)
        | (models.QMSAudit.assistant_auditor_user_id == user_id),
        models.QMSAudit.status == models.QMSAuditStatus.CLOSED,
    ).count()

    lead_audits = qs.filter(models.QMSAudit.lead_auditor_user_id == user_id).count()
    observer_audits = qs.filter(models.QMSAudit.observer_auditor_user_id == user_id).count()
    assistant_audits = qs.filter(models.QMSAudit.assistant_auditor_user_id == user_id).count()

    return {
        "user_id": user_id,
        "audits_total": audits_total,
        "audits_open": audits_open,
        "audits_closed": audits_closed,
        "lead_audits": lead_audits,
        "observer_audits": observer_audits,
        "assistant_audits": assistant_audits,
    }


def _build_qms_notification_summary_payload(db: Session, user_id: str) -> QMSNotificationSummaryOut:
    unread_count, latest_created_at = (
        db.query(
            func.count(models.QMSNotification.id),
            func.max(models.QMSNotification.created_at),
        )
        .filter(
            models.QMSNotification.user_id == user_id,
            models.QMSNotification.read_at.is_(None),
        )
        .one()
    )
    return QMSNotificationSummaryOut(
        unread_count=int(unread_count or 0),
        latest_created_at=latest_created_at,
    )


def _make_qms_notification_summary_etag(payload: QMSNotificationSummaryOut) -> str:
    stamp = payload.latest_created_at.isoformat() if payload.latest_created_at else ""
    digest = hashlib.sha256(f"{payload.unread_count}:{stamp}".encode("utf-8")).hexdigest()[:20]
    return f'W/"{digest}"'


@router.get("/notifications/me/summary", response_model=QMSNotificationSummaryOut)
def get_my_notification_summary(
    response: Response,
    if_none_match: Optional[str] = Header(default=None),
    db: Session = Depends(get_read_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    user_id = get_actor() or str(current_user.id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = _build_qms_notification_summary_payload(db, user_id)
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            payload = QMSNotificationSummaryOut(unread_count=0, latest_created_at=None)
        else:
            raise

    etag = _make_qms_notification_summary_etag(payload)
    headers = {"ETag": etag, "Cache-Control": "private, max-age=0, must-revalidate"}
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return payload


@router.get("/notifications/me", response_model=List[QMSNotificationOut])
def list_my_notifications(
    include_read: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    user_id = get_actor() or str(current_user.id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        query = (
            db.query(models.QMSNotification)
            .filter(models.QMSNotification.user_id == user_id)
            .order_by(models.QMSNotification.created_at.desc())
        )
        if not include_read:
            query = query.filter(models.QMSNotification.read_at.is_(None))
        notes = query.limit(limit).all()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            return []
        raise
    return notes


@router.post("/notifications/me/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    user_id = get_actor() or str(current_user.id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        updated = (
            db.query(models.QMSNotification)
            .filter(models.QMSNotification.user_id == user_id)
            .filter(models.QMSNotification.read_at.is_(None))
            .update({models.QMSNotification.read_at: func.now()}, synchronize_session=False)
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            return {"updated": 0}
        raise
    db.commit()
    return {"updated": int(updated or 0)}


@router.post("/notifications/{notification_id}/read", response_model=QMSNotificationOut)
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    user_id = get_actor() or str(current_user.id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        note = (
            db.query(models.QMSNotification)
            .filter(models.QMSNotification.id == notification_id, models.QMSNotification.user_id == user_id)
            .first()
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            raise HTTPException(
                status_code=503,
                detail="Notifications are not available because the database schema is missing.",
            ) from exc
        raise
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    note.read_at = func.now()
    db.commit()
    db.refresh(note)
    return note


def _is_missing_table_error(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return ("relation" in message and "does not exist" in message) or "no such table" in message


@router.post("/cars/{car_id}/actions", response_model=CARActionOut, status_code=status.HTTP_201_CREATED)
def add_car_action_log(
    car_id: UUID,
    payload: CARActionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")

    log = add_car_action(
        db=db,
        car=car,
        action_type=payload.action_type,
        message=payload.message.strip(),
        actor_user_id=get_actor(),
    )
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_car",
        entity_id=str(car.id),
        action="comment",
        after={"action_type": payload.action_type.value, "message": payload.message.strip()},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    db.commit()
    db.refresh(log)
    return log


@router.get("/cars/{car_id}/actions", response_model=List[CARActionOut])
def list_car_actions(car_id: UUID, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    return (
        db.query(models.CARActionLog)
        .filter(models.CARActionLog.car_id == car_id)
        .order_by(models.CARActionLog.created_at.desc())
        .all()
    )


AERODOC_DOC_DIR = Path(__file__).resolve().parents[2] / "generated" / "quality" / "aerodoc"
AERODOC_DOC_DIR.mkdir(parents=True, exist_ok=True)
AERODOC_ALLOWED_MIME_TYPES = {"application/pdf", "text/plain", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_AERODOC_UPLOAD_BYTES = 50 * 1024 * 1024


def _require_aerodoc_module(_: account_models.User = Depends(require_module("aerodoc_hybrid_dms"))):
    return True


def _is_aerodoc_control_role(current_user: account_models.User) -> bool:
    role_value = getattr(current_user, "role", None)
    role_value = getattr(role_value, "value", role_value)
    return bool(
        getattr(current_user, "is_superuser", False)
        or role_value in {
            account_models.AccountRole.AMO_ADMIN,
            account_models.AccountRole.QUALITY_MANAGER,
            account_models.AccountRole.QUALITY_INSPECTOR,
            "AMO_ADMIN",
            "QUALITY_MANAGER",
            "QUALITY_INSPECTOR",
            "DOCUMENT_CONTROL_OFFICER",
        }
    )


def _enforce_aerodoc_control(current_user: account_models.User) -> None:
    if not _is_aerodoc_control_role(current_user):
        raise HTTPException(status_code=403, detail="Document Control Officer or AMO Admin rights required")


def _store_aerodoc_upload(doc_id: UUID, rev_id: UUID, file: UploadFile) -> tuple[str, int, str]:
    filename = file.filename or "document.bin"
    ext = Path(filename).suffix.lower()
    if file.content_type not in AERODOC_ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported content type")
    if ext not in {".pdf", ".txt", ".doc", ".docx"}:
        raise HTTPException(status_code=400, detail="Unsupported file extension")
    target_dir = AERODOC_DOC_DIR / str(doc_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{rev_id}{ext}"
    digest = hashlib.sha256()
    total = 0
    with target_path.open("wb") as fh:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_AERODOC_UPLOAD_BYTES:
                fh.close()
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large")
            digest.update(chunk)
            fh.write(chunk)
    return digest.hexdigest(), total, str(target_path)


@router.post("/qms/documents/{doc_id}/revisions/upload", response_model=QMSUploadRevisionOut, dependencies=[Depends(_require_aerodoc_module)])
def upload_doc_revision(
    doc_id: UUID,
    issue_no: int = Query(..., ge=0),
    rev_no: int = Query(..., ge=0),
    version_semver: str = Query(..., pattern=r"^\d+\.\d+\.\d+$"),
    request: Request = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _enforce_aerodoc_control(current_user)
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == doc_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    rev = models.QMSDocumentRevision(amo_id=doc.amo_id, document_id=doc.id, issue_no=issue_no, rev_no=rev_no, created_by_user_id=get_actor(), version_semver=version_semver)
    db.add(rev)
    db.flush()
    sha256, byte_size, storage_path = _store_aerodoc_upload(doc.id, rev.id, file)
    rev.sha256 = sha256
    rev.byte_size = byte_size
    rev.file_ref = storage_path
    rev.primary_storage_provider = "local"
    rev.primary_storage_key = storage_path
    rev.mime_type = file.content_type
    replication = replicate_file(storage_path, f"{doc.id}/{rev.id}")
    audit_services.log_event(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms.document.revision",
        entity_id=str(rev.id),
        action="uploaded",
        after={"sha256": sha256, "byte_size": byte_size, "replication": replication.as_dict()},
        correlation_id=str(uuid.uuid4()),
        metadata=_audit_metadata(request),
    )
    if not (replication.aws_ok and replication.azure_ok and replication.onprem_ok):
        audit_services.log_event(
            db,
            amo_id=current_user.amo_id,
            actor_user_id=current_user.id,
            entity_type="qms.document.revision",
            entity_id=str(rev.id),
            action="replication_warning",
            after={"replication": replication.as_dict()},
            correlation_id=str(uuid.uuid4()),
            metadata=_audit_metadata(request),
        )
    db.commit()
    return QMSUploadRevisionOut(revision_id=rev.id, sha256=sha256, viewer_url=f"/maintenance/{current_user.amo_id}/quality/qms/documents/{doc.id}/revisions/{rev.id}/view")


@router.post("/qms/physical-copies", response_model=List[QMSPhysicalCopyOut], dependencies=[Depends(_require_aerodoc_module)])
def request_physical_copy(payload: QMSPhysicalCopyRequest, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    rev = db.query(models.QMSDocumentRevision).filter(models.QMSDocumentRevision.id == payload.revision_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    created = []
    existing = (
        db.query(models.QMSPhysicalControlledCopy)
        .filter(
            models.QMSPhysicalControlledCopy.amo_id == current_user.amo_id,
            models.QMSPhysicalControlledCopy.copy_serial_number.like(f"{payload.base_serial}-COPY-%"),
        )
        .all()
    )
    next_num = 1
    for row in existing:
        serial = row.copy_serial_number or ""
        if serial.startswith(f"{payload.base_serial}-COPY-"):
            suffix = serial.rsplit("-COPY-", 1)[-1]
            if suffix.isdigit():
                next_num = max(next_num, int(suffix) + 1)

    for _ in range(payload.count):
        serial = f"{payload.base_serial}-COPY-{next_num:03d}"
        row = models.QMSPhysicalControlledCopy(
            amo_id=current_user.amo_id,
            digital_revision_id=rev.id,
            copy_serial_number=serial,
            storage_location_path=payload.storage_location_path,
            copy_number=next_num,
        )
        db.add(row)
        db.flush()
        created.append(row)
        audit_services.log_event(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="qms.physical_copy", entity_id=str(row.id), action="created", after={"serial": serial, "revision_id": str(rev.id)}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
        next_num += 1
    db.commit()
    return created


def _custody_action(copy_id: UUID, action: QMSCustodyAction, payload: QMSCustodyActionCreate, request: Request, db: Session, current_user: account_models.User):
    copy = db.query(models.QMSPhysicalControlledCopy).filter(models.QMSPhysicalControlledCopy.id == copy_id, models.QMSPhysicalControlledCopy.amo_id == current_user.amo_id).first()
    if not copy:
        raise HTTPException(status_code=404, detail="Physical copy not found")
    log = models.QMSCustodyLog(amo_id=current_user.amo_id, physical_copy_id=copy.id, user_id=current_user.id, action=action, gps_lat=payload.gps_lat, gps_lng=payload.gps_lng, notes=payload.notes)
    db.add(log)
    if action == QMSCustodyAction.CHECK_OUT:
        copy.current_holder_user_id = current_user.id
    if action == QMSCustodyAction.CHECK_IN:
        copy.current_holder_user_id = None
    audit_services.log_event(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="qms.custody", entity_id=str(log.id), action=action.value.lower(), after={"copy_id": str(copy.id)}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    db.refresh(log)
    return log


@router.post("/qms/physical-copies/{copy_id}/checkout", response_model=QMSCustodyLogOut, dependencies=[Depends(_require_aerodoc_module)])
def checkout_copy(copy_id: UUID, payload: QMSCustodyActionCreate, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    return _custody_action(copy_id, QMSCustodyAction.CHECK_OUT, payload, request, db, current_user)


@router.post("/qms/physical-copies/{copy_id}/checkin", response_model=QMSCustodyLogOut, dependencies=[Depends(_require_aerodoc_module)])
def checkin_copy(copy_id: UUID, payload: QMSCustodyActionCreate, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    return _custody_action(copy_id, QMSCustodyAction.CHECK_IN, payload, request, db, current_user)


@router.get("/qms/physical-copies/verify/{serial}", response_model=QMSPhysicalVerifyOut, dependencies=[Depends(_require_aerodoc_module)])
def verify_physical_copy(serial: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    copy = db.query(models.QMSPhysicalControlledCopy).filter(models.QMSPhysicalControlledCopy.copy_serial_number == serial, models.QMSPhysicalControlledCopy.amo_id == current_user.amo_id).first()
    if not copy:
        return QMSPhysicalVerifyOut(serial=serial, status="RED", current=False)
    rev = db.query(models.QMSDocumentRevision).filter(models.QMSDocumentRevision.id == copy.digital_revision_id).first()
    is_current = bool(rev and rev.lifecycle_status == QMSRevisionLifecycleStatus.APPROVED and copy.status == QMSPhysicalCopyStatus.ACTIVE and copy.voided_at is None)
    return QMSPhysicalVerifyOut(serial=serial, status="GREEN" if is_current else "RED", current=is_current, approved_version=rev.version_semver if rev else None)


@router.post("/qms/revisions/issue", response_model=QMSDocumentRevisionOut, dependencies=[Depends(_require_aerodoc_module)])
def issue_revision(payload: QMSIssueRevisionRequest, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    doc = db.query(models.QMSDocument).filter(
        models.QMSDocument.id == payload.doc_id,
        models.QMSDocument.amo_id == _current_amo_id(current_user),
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.query(models.QMSDocumentRevision).filter(
        models.QMSDocumentRevision.document_id == payload.doc_id,
        models.QMSDocumentRevision.amo_id == _current_amo_id(current_user),
        models.QMSDocumentRevision.lifecycle_status == QMSRevisionLifecycleStatus.APPROVED,
    ).update({
        models.QMSDocumentRevision.lifecycle_status: QMSRevisionLifecycleStatus.SUPERSEDED,
        models.QMSDocumentRevision.superseded_at: datetime.now(timezone.utc),
    }, synchronize_session=False)

    rev = models.QMSDocumentRevision(
        amo_id=doc.amo_id,
        document_id=payload.doc_id,
        issue_no=payload.issue_no,
        rev_no=payload.rev_no,
        version_semver=payload.version_semver,
        change_summary=payload.change_summary,
        lifecycle_status=QMSRevisionLifecycleStatus.APPROVED,
        approved_at=datetime.now(timezone.utc),
        approved_by_user_id=current_user.id,
        created_by_user_id=get_actor(),
    )
    db.add(rev)
    db.flush()
    audit_services.log_event(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="qms.document.revision", entity_id=str(rev.id), action="issued", after={"doc_id": str(payload.doc_id), "version_semver": rev.version_semver}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    db.refresh(rev)
    return rev


def _stream_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@router.get("/qms/documents/{doc_id}/revisions/{rev_id}/open", dependencies=[Depends(_require_aerodoc_module)])
def open_revision(doc_id: UUID, rev_id: UUID, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    rev = db.query(models.QMSDocumentRevision).join(models.QMSDocument, models.QMSDocument.id == models.QMSDocumentRevision.document_id).filter(models.QMSDocumentRevision.id == rev_id, models.QMSDocumentRevision.document_id == doc_id).first()
    if not rev or not rev.file_ref:
        raise HTTPException(status_code=404, detail="Revision file not found")
    file_path = Path(rev.file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stored file missing")
    computed = _stream_file_sha256(file_path)
    integrity_ok = bool(rev.sha256 and computed == rev.sha256)
    if not integrity_ok:
        audit_services.log_event(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="qms.document.revision", entity_id=str(rev.id), action="integrity_mismatch", after={"stored": rev.sha256, "computed": computed}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
        db.commit()
    response = FileResponse(path=file_path, media_type=rev.mime_type or "application/octet-stream", filename=file_path.name)
    response.headers["X-Document-Integrity"] = "ok" if integrity_ok else "compromised"
    return response


@router.post("/qms/physical-copies/{copy_id}/report-damage", response_model=QMSDamageReportOut, dependencies=[Depends(_require_aerodoc_module)])
def report_damage(copy_id: UUID, payload: QMSDamageReportRequest, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    copy = db.query(models.QMSPhysicalControlledCopy).filter(models.QMSPhysicalControlledCopy.id == copy_id, models.QMSPhysicalControlledCopy.amo_id == current_user.amo_id).first()
    if not copy:
        raise HTTPException(status_code=404, detail="Physical copy not found")
    copy.status = QMSPhysicalCopyStatus.RECALL_PENDING
    copy.voided_at = datetime.now(timezone.utc)
    old_serial = copy.copy_serial_number
    replacement_serial = f"{old_serial}-R{int(datetime.now(timezone.utc).timestamp())}"
    replacement = models.QMSPhysicalControlledCopy(
        amo_id=current_user.amo_id,
        digital_revision_id=copy.digital_revision_id,
        copy_serial_number=replacement_serial,
        storage_location_path=payload.storage_location_path or copy.storage_location_path,
        copy_number=copy.copy_number + 1,
    )
    db.add(replacement)
    db.flush()
    copy.replaced_by_copy_id = replacement.id

    db.add(models.QMSCustodyLog(amo_id=current_user.amo_id, physical_copy_id=copy.id, user_id=current_user.id, action=QMSCustodyAction.DAMAGED, notes=payload.notes))
    db.add(models.QMSCustodyLog(amo_id=current_user.amo_id, physical_copy_id=replacement.id, user_id=current_user.id, action=QMSCustodyAction.INSPECTED, notes="Replacement issued"))

    audit_services.log_event(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="qms.physical_copy", entity_id=str(copy.id), action="damaged", after={"replacement_id": str(replacement.id)}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    return QMSDamageReportOut(old_copy_id=copy.id, new_copy_id=replacement.id, old_serial=old_serial, new_serial=replacement_serial)


@router.get("/qms/audit-mode/binder", dependencies=[Depends(_require_aerodoc_module)])
def audit_mode_binder(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    since = datetime.now(timezone.utc) - timedelta(days=730)
    docs = db.query(models.QMSDocument).filter(models.QMSDocument.status == models.QMSDocStatus.ACTIVE).all()
    custody = db.query(models.QMSCustodyLog).filter(models.QMSCustodyLog.amo_id == current_user.amo_id, models.QMSCustodyLog.occurred_at >= since).all()

    def stream_zip() -> Iterator[bytes]:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("current_manuals.json", JSONResponse(content=[{"id": str(d.id), "doc_code": d.doc_code, "title": d.title} for d in docs]).body.decode())
            zf.writestr("custody_logs.json", JSONResponse(content=[{"id": str(c.id), "copy_id": str(c.physical_copy_id), "action": c.action.value, "occurred_at": c.occurred_at.isoformat()} for c in custody]).body.decode())
        buf.seek(0)
        while True:
            chunk = buf.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(stream_zip(), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=aerodoc-binder.zip"})


@router.post("/qms/documents/{doc_id}/archive", dependencies=[Depends(_require_aerodoc_module)])
def archive_document(doc_id: UUID, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    _enforce_aerodoc_control(current_user)
    doc = db.query(models.QMSDocument).filter(models.QMSDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.status = models.QMSDocStatus.OBSOLETE
    audit_services.log_event(db, amo_id=current_user.amo_id, actor_user_id=current_user.id, entity_type="qms.document", entity_id=str(doc.id), action="archived", after={"retention_category": getattr(doc.retention_category, "value", str(doc.retention_category))}, correlation_id=str(uuid.uuid4()), metadata=_audit_metadata(request))
    db.commit()
    return {"status": "archived", "doc_id": str(doc.id)}
