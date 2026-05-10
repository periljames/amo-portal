# backend/amodb/apps/accounts/router_admin.py

from __future__ import annotations

import os
import json
import csv
import io
import socket
import smtplib
import ssl
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4
from typing import Any, List, Optional
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import or_, func, text
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.apps.audit import services as audit_services
from amodb.apps.audit import models as audit_models
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.notifications import service as notification_service
from amodb.apps.tasks import services as task_services
from amodb.apps.tasks import models as task_models
from amodb.security import get_current_active_user, require_admin, require_roles
from . import models, schemas, services
from .personnel_import import import_personnel_rows, parse_people_sheet

router = APIRouter(prefix="/accounts/admin", tags=["accounts_admin"])
RESERVED_PLATFORM_SLUGS = {"system", "root"}
PLATFORM_MODULE_CATALOG = [
    {"code": "qms", "label": "QMS Cockpit", "category": "Quality"},
    {"code": "quality", "label": "Quality Legacy Tools", "category": "Quality"},
    {"code": "training", "label": "Training & Competence", "category": "Quality"},
    {"code": "manuals", "label": "Controlled Manuals", "category": "Documents"},
    {"code": "aerodoc_hybrid_dms", "label": "AeroDoc Hybrid DMS", "category": "Documents"},
    {"code": "maintenance_program", "label": "Maintenance Programme", "category": "Maintenance"},
    {"code": "work", "label": "Work Orders", "category": "Maintenance"},
    {"code": "fleet", "label": "Fleet", "category": "Maintenance"},
    {"code": "reliability", "label": "Reliability", "category": "Continuing Airworthiness"},
    {"code": "finance_inventory", "label": "Finance & Inventory", "category": "Commercial"},
    {"code": "production", "label": "Production", "category": "Maintenance"},
    {"code": "planning", "label": "Planning", "category": "Maintenance"},
    {"code": "technical_records", "label": "Technical Records", "category": "Records"},
    {"code": "equipment_calibration", "label": "Equipment & Calibration", "category": "Quality"},
    {"code": "suppliers", "label": "Suppliers", "category": "Quality"},
    {"code": "management_review", "label": "Management Review", "category": "Quality"},
]
PLATFORM_MODULE_CODES = {item["code"] for item in PLATFORM_MODULE_CATALOG}
AMO_ASSET_UPLOAD_DIR = Path(os.getenv("AMO_ASSET_UPLOAD_DIR", "uploads/amo_assets")).resolve()
PLATFORM_ASSET_UPLOAD_DIR = Path(
    os.getenv("PLATFORM_ASSET_UPLOAD_DIR", "uploads/platform_assets")
).resolve()
TRAINING_UPLOAD_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve()
AIRCRAFT_DOC_UPLOAD_DIR = Path(
    os.getenv("AIRCRAFT_DOC_UPLOAD_DIR", "/tmp/amo_aircraft_documents")
).resolve()
AIRCRAFT_DOC_AMO_SUBDIR = "aircraft"

ALLOWED_PLATFORM_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}
PRESENCE_HEARTBEAT_GRACE_SECONDS = 150
RECENTLY_ACTIVE_WINDOW_MINUTES = 10

_USER_GROUP_SCHEMA_VERIFIED = False


def _ensure_user_group_schema(db: Session) -> None:
    global _USER_GROUP_SCHEMA_VERIFIED
    if _USER_GROUP_SCHEMA_VERIFIED:
        return

    bind = db.get_bind()
    inspector = sa.inspect(bind)
    statements: list[str] = []

    if inspector.has_table("user_groups"):
        group_columns = {column["name"] for column in inspector.get_columns("user_groups")}
        if "is_system_managed" not in group_columns:
            statements.append(
                "ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS is_system_managed BOOLEAN NOT NULL DEFAULT false"
            )
        if "is_active" not in group_columns:
            statements.append(
                "ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true"
            )
        if "created_at" not in group_columns:
            statements.append(
                "ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in group_columns:
            statements.append(
                "ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

    if inspector.has_table("user_group_members"):
        member_columns = {column["name"] for column in inspector.get_columns("user_group_members")}
        if "added_by_user_id" not in member_columns:
            statements.append(
                "ALTER TABLE user_group_members ADD COLUMN IF NOT EXISTS added_by_user_id VARCHAR(36) NULL"
            )
        if "member_role" not in member_columns:
            statements.append(
                "ALTER TABLE user_group_members ADD COLUMN IF NOT EXISTS member_role VARCHAR(32) NOT NULL DEFAULT 'member'"
            )
        if "added_at" not in member_columns:
            statements.append(
                "ALTER TABLE user_group_members ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

    if not statements:
        _USER_GROUP_SCHEMA_VERIFIED = True
        return

    try:
        for statement in statements:
            db.execute(text(statement))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_user_groups_amo_type ON user_groups (amo_id, group_type)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_user_groups_amo_active ON user_groups (amo_id, is_active)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_user_group_members_user ON user_group_members (user_id)"))
        db.commit()
        _USER_GROUP_SCHEMA_VERIFIED = True
    except Exception:
        db.rollback()
        raise


def _resolve_presence_state(*, raw_state: str, last_seen_at: Optional[datetime], now: datetime) -> tuple[str, bool]:
    normalized_state = str(raw_state or "offline").lower()
    freshness_cutoff = now - timedelta(seconds=PRESENCE_HEARTBEAT_GRACE_SECONDS)
    is_fresh = bool(last_seen_at and last_seen_at >= freshness_cutoff)
    is_online = bool(is_fresh and normalized_state in {"online", "away"})
    if not is_online:
        return "offline", False
    return ("away" if normalized_state == "away" else "online"), True


def _format_role_for_display(role_value: object) -> str:
    raw = str(getattr(role_value, "value", role_value) or "").strip()
    if not raw:
        return "Portal User"
    return raw.replace("_", " ").title()


def _display_title_for_user(user: models.User) -> str:
    title = str(user.position_title or "").strip()
    return title if title else _format_role_for_display(user.role)


def _presence_display_for_user(
    *,
    user: models.User,
    presence: schemas.UserPresenceRead,
    availability_status: Optional[str] = None,
) -> schemas.UserPresenceDisplayRead:
    if not user.is_active:
        return schemas.UserPresenceDisplayRead(
            status_label="Inactive",
            last_seen_label="Never seen" if not (presence.last_seen_at or user.last_login_at) else "Inactive",
            last_seen_at=presence.last_seen_at or user.last_login_at,
            last_seen_at_display=None,
        )

    if availability_status == "ON_LEAVE":
        return schemas.UserPresenceDisplayRead(
            status_label="On leave",
            last_seen_label="Leave scheduled",
            last_seen_at=presence.last_seen_at or user.last_login_at,
            last_seen_at_display=None,
        )

    if presence.is_online:
        return schemas.UserPresenceDisplayRead(
            status_label="Online",
            last_seen_label="Active now",
            last_seen_at=presence.last_seen_at,
            last_seen_at_display=None,
        )

    last_seen = presence.last_seen_at or user.last_login_at
    if not last_seen:
        return schemas.UserPresenceDisplayRead(
            status_label="Offline",
            last_seen_label="Never seen",
            last_seen_at=None,
            last_seen_at_display=None,
        )
    return schemas.UserPresenceDisplayRead(
        status_label="Offline",
        last_seen_label="Last seen",
        last_seen_at=last_seen,
        last_seen_at_display=last_seen.isoformat() if hasattr(last_seen, "isoformat") else str(last_seen),
    )


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _from_iso_date(value):
    if not value:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    return value


def _from_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _profile_state(profile: models.PersonnelProfile) -> dict:
    return {
        "id": profile.id,
        "person_id": profile.person_id,
        "user_id": profile.user_id,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "full_name": profile.full_name,
        "national_id": profile.national_id,
        "amel_no": profile.amel_no,
        "internal_certification_stamp_no": profile.internal_certification_stamp_no,
        "initial_authorization_date": _jsonable(profile.initial_authorization_date),
        "department": profile.department,
        "position_title": profile.position_title,
        "phone_number": profile.phone_number,
        "secondary_phone": profile.secondary_phone,
        "email": profile.email,
        "hire_date": _jsonable(profile.hire_date),
        "employment_status": profile.employment_status,
        "status": profile.status,
        "date_of_birth": _jsonable(profile.date_of_birth),
        "birth_place": profile.birth_place,
    }


def _user_state(user: models.User) -> dict:
    return {
        "id": user.id,
        "staff_code": user.staff_code,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "position_title": user.position_title,
        "phone": user.phone,
        "secondary_phone": user.secondary_phone,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "password_changed_at": _jsonable(user.password_changed_at),
    }


def _capture_import_state(db: Session, *, amo_id: str, rows: list[dict]) -> dict:
    person_ids = {str(r.get("PersonID") or "").strip() for r in rows if str(r.get("PersonID") or "").strip()}
    emails = {str(r.get("Email") or "").strip().lower() for r in rows if str(r.get("Email") or "").strip()}

    profile_query = db.query(models.PersonnelProfile).filter(models.PersonnelProfile.amo_id == amo_id)
    if person_ids:
        profile_query = profile_query.filter(models.PersonnelProfile.person_id.in_(person_ids))
    profiles = profile_query.all()
    if emails:
        email_profiles = (
            db.query(models.PersonnelProfile)
            .filter(models.PersonnelProfile.amo_id == amo_id, func.lower(models.PersonnelProfile.email).in_(emails))
            .all()
        )
        profile_map = {p.id: p for p in profiles}
        for profile in email_profiles:
            profile_map[profile.id] = profile
        profiles = list(profile_map.values())

    user_query = db.query(models.User).filter(models.User.amo_id == amo_id)
    if person_ids:
        user_query = user_query.filter(models.User.staff_code.in_(person_ids))
    users = user_query.all()
    if emails:
        email_users = (
            db.query(models.User)
            .filter(models.User.amo_id == amo_id, func.lower(models.User.email).in_(emails))
            .all()
        )
        user_map = {u.id: u for u in users}
        for user in email_users:
            user_map[user.id] = user
        users = list(user_map.values())

    return {
        "profiles": {p.id: _profile_state(p) for p in profiles},
        "users": {u.id: _user_state(u) for u in users},
    }


def _build_undo_payload(before: dict, after: dict) -> dict:
    created_profile_ids = [pid for pid in after["profiles"].keys() if pid not in before["profiles"]]
    created_user_ids = [uid for uid in after["users"].keys() if uid not in before["users"]]
    updated_profiles_before = [
        before["profiles"][pid]
        for pid in before["profiles"].keys()
        if pid in after["profiles"] and before["profiles"][pid] != after["profiles"][pid]
    ]
    updated_users_before = [
        before["users"][uid]
        for uid in before["users"].keys()
        if uid in after["users"] and before["users"][uid] != after["users"][uid]
    ]
    return {
        "created_profile_ids": created_profile_ids,
        "created_user_ids": created_user_ids,
        "updated_profiles_before": updated_profiles_before,
        "updated_users_before": updated_users_before,
    }



def _get_managed_user_or_404(db: Session, *, current_user: models.User, user_id: str) -> models.User:
    query = db.query(models.User).filter(models.User.id == user_id)
    if not current_user.is_superuser:
        query = query.filter(models.User.amo_id == current_user.amo_id)
    user = query.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not in your AMO.",
        )
    return user


def _emit_user_command_event(
    db: Session,
    *,
    actor_user_id: str,
    user: models.User,
    action: str,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=actor_user_id,
        entity_type="accounts.user.command",
        entity_id=str(user.id),
        action=action,
        after=after or {},
        metadata={"module": "accounts", **(metadata or {})},
    )


def _ensure_amo_storage_dirs(amo_id: str) -> None:
    for base in (AMO_ASSET_UPLOAD_DIR, TRAINING_UPLOAD_DIR, AIRCRAFT_DOC_UPLOAD_DIR):
        base.mkdir(parents=True, exist_ok=True)

    (AMO_ASSET_UPLOAD_DIR / amo_id).mkdir(parents=True, exist_ok=True)
    (TRAINING_UPLOAD_DIR / amo_id).mkdir(parents=True, exist_ok=True)
    (AIRCRAFT_DOC_UPLOAD_DIR / amo_id / AIRCRAFT_DOC_AMO_SUBDIR).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# AMO MANAGEMENT (SUPERUSER ONLY)
# ---------------------------------------------------------------------------


def _require_superuser(current_user: models.User) -> models.User:
    """
    Internal helper: platform superuser gate.

    - Blocks system/service accounts even if they somehow had is_superuser=True.
    - Requires is_superuser=True (platform owner).
    """
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot use superuser endpoints.",
        )

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required.",
        )
    return current_user


def _parse_env_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_env_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _platform_settings_defaults() -> dict:
    return {
        "api_base_url": os.getenv("PLATFORM_API_BASE_URL"),
        "platform_name": os.getenv("PLATFORM_BRAND_NAME", "AMO Portal"),
        "platform_tagline": os.getenv("PLATFORM_BRAND_TAGLINE"),
        "brand_accent": os.getenv("PLATFORM_BRAND_ACCENT"),
        "brand_accent_soft": os.getenv("PLATFORM_BRAND_ACCENT_SOFT"),
        "brand_accent_secondary": os.getenv("PLATFORM_BRAND_ACCENT_SECONDARY"),
        "gzip_minimum_size": _parse_env_int(os.getenv("GZIP_MINIMUM_SIZE")),
        "gzip_compresslevel": _parse_env_int(os.getenv("GZIP_COMPRESSLEVEL")),
        "max_request_body_bytes": _parse_env_int(os.getenv("MAX_REQUEST_BODY_BYTES")),
        "email_provider": os.getenv("PLATFORM_EMAIL_PROVIDER", os.getenv("EMAIL_PROVIDER")),
        "email_from_name": os.getenv("PLATFORM_EMAIL_FROM_NAME", os.getenv("EMAIL_FROM_NAME")),
        "email_from_email": os.getenv("PLATFORM_EMAIL_FROM_EMAIL", os.getenv("EMAIL_FROM_EMAIL")),
        "email_reply_to": os.getenv("PLATFORM_EMAIL_REPLY_TO", os.getenv("EMAIL_REPLY_TO")),
        "smtp_host": os.getenv("PLATFORM_SMTP_HOST", os.getenv("SMTP_HOST")),
        "smtp_port": _parse_env_int(os.getenv("PLATFORM_SMTP_PORT", os.getenv("SMTP_PORT"))),
        "smtp_username": os.getenv("PLATFORM_SMTP_USERNAME", os.getenv("SMTP_USERNAME")),
        "smtp_password_secret": os.getenv("PLATFORM_SMTP_PASSWORD", os.getenv("SMTP_PASSWORD")),
        "smtp_use_tls": (os.getenv("PLATFORM_SMTP_USE_TLS", os.getenv("SMTP_USE_TLS", "true")).lower() in {"1", "true", "yes", "on"}),
        "smtp_allow_self_signed": (os.getenv("PLATFORM_SMTP_ALLOW_SELF_SIGNED", os.getenv("SMTP_ALLOW_SELF_SIGNED", "false")).lower() in {"1", "true", "yes", "on"}),
        "smtp_test_recipient": os.getenv("PLATFORM_SMTP_TEST_RECIPIENT"),
        "support_email": os.getenv("PLATFORM_SUPPORT_EMAIL"),
        "ops_alert_email": os.getenv("PLATFORM_OPS_ALERT_EMAIL"),
        "acme_directory_url": os.getenv("ACME_DIRECTORY_URL"),
        "acme_client": os.getenv("ACME_CLIENT"),
        "certificate_status": os.getenv("ACME_CERT_STATUS"),
        "certificate_issuer": os.getenv("ACME_CERT_ISSUER"),
        "certificate_expires_at": _parse_env_datetime(
            os.getenv("ACME_CERT_EXPIRES_AT")
        ),
        "last_renewed_at": _parse_env_datetime(os.getenv("ACME_CERT_RENEWED_AT")),
        "notes": os.getenv("PLATFORM_NOTES"),
    }


def _get_or_create_platform_settings(db: Session) -> models.PlatformSettings:
    settings = db.query(models.PlatformSettings).first()
    if not settings:
        settings = models.PlatformSettings(**_platform_settings_defaults())
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings

    defaults = _platform_settings_defaults()
    updated = False
    for key, value in defaults.items():
        if value is not None and getattr(settings, key) in (None, ""):
            setattr(settings, key, value)
            updated = True
    if updated:
        db.commit()
        db.refresh(settings)
    return settings


def _ensure_platform_storage_dir() -> None:
    PLATFORM_ASSET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_safe_platform_path(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith(str(PLATFORM_ASSET_UPLOAD_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid platform asset path.",
        )
    return resolved


def _save_platform_upload(*, file: UploadFile, dest_path: Path) -> None:
    with dest_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def _delete_platform_asset(path: Optional[str]) -> None:
    if not path:
        return
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        return



def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _dt_value(value: Any) -> Optional[str]:
    return value.isoformat() if value and hasattr(value, "isoformat") else None


def _latest_license_for_amo(db: Session, *, amo_id: str) -> Optional[models.TenantLicense]:
    return services.get_latest_subscription(db, amo_id=amo_id)


def _get_or_create_platform_managed_sku(db: Session) -> models.CatalogSKU:
    """
    Ensure Super Admin can unblock or activate a tenant even before the commercial
    catalog has been configured. This SKU is internal, inactive by default, and
    exists only as the required foreign key anchor for a tenant license.
    """
    sku = db.query(models.CatalogSKU).filter(models.CatalogSKU.code == "PLATFORM_MANAGED").first()
    if sku:
        return sku
    sku = models.CatalogSKU(
        code="PLATFORM_MANAGED",
        name="Platform Managed Access",
        description="Internal superadmin-managed access anchor used before a commercial billing plan is assigned.",
        term=models.BillingTerm.MONTHLY,
        trial_days=0,
        amount_cents=0,
        currency="USD",
        min_usage_limit=None,
        max_usage_limit=None,
        is_active=False,
    )
    db.add(sku)
    db.flush()
    return sku


def _license_summary(license: Optional[models.TenantLicense]) -> Optional[dict[str, Any]]:
    if not license:
        return None
    sku = getattr(license, "catalog_sku", None)
    return {
        "id": license.id,
        "amo_id": license.amo_id,
        "sku_id": license.sku_id,
        "sku_code": getattr(sku, "code", None),
        "sku_name": getattr(sku, "name", None),
        "term": _enum_value(license.term),
        "status": _enum_value(license.status),
        "is_read_only": bool(license.is_read_only),
        "trial_started_at": _dt_value(license.trial_started_at),
        "trial_ends_at": _dt_value(license.trial_ends_at),
        "trial_grace_expires_at": _dt_value(license.trial_grace_expires_at),
        "current_period_start": _dt_value(license.current_period_start),
        "current_period_end": _dt_value(license.current_period_end),
        "canceled_at": _dt_value(license.canceled_at),
        "notes": license.notes,
        "created_at": _dt_value(license.created_at),
        "updated_at": _dt_value(license.updated_at),
    }


def _module_summary(subscription: models.ModuleSubscription) -> dict[str, Any]:
    return {
        "id": subscription.id,
        "amo_id": subscription.amo_id,
        "module_code": subscription.module_code,
        "status": _enum_value(subscription.status),
        "effective_from": _dt_value(subscription.effective_from),
        "effective_to": _dt_value(subscription.effective_to),
        "plan_code": subscription.plan_code,
        "metadata_json": subscription.metadata_json,
        "created_at": _dt_value(subscription.created_at),
        "updated_at": _dt_value(subscription.updated_at),
    }


def _invoice_summary(invoice: models.BillingInvoice) -> dict[str, Any]:
    return {
        **services.build_invoice_view(invoice),
        "created_at": _dt_value(invoice.created_at),
        "updated_at": _dt_value(invoice.updated_at),
    }


def _platform_settings_summary(settings: models.PlatformSettings) -> dict[str, Any]:
    return {
        "id": settings.id,
        "api_base_url": settings.api_base_url,
        "platform_name": settings.platform_name,
        "platform_tagline": settings.platform_tagline,
        "brand_accent": settings.brand_accent,
        "brand_accent_soft": settings.brand_accent_soft,
        "brand_accent_secondary": settings.brand_accent_secondary,
        "platform_logo_filename": settings.platform_logo_filename,
        "platform_logo_content_type": settings.platform_logo_content_type,
        "platform_logo_uploaded_at": _dt_value(settings.platform_logo_uploaded_at),
        "gzip_minimum_size": settings.gzip_minimum_size,
        "gzip_compresslevel": settings.gzip_compresslevel,
        "max_request_body_bytes": settings.max_request_body_bytes,
        "email_provider": settings.email_provider,
        "email_from_name": settings.email_from_name,
        "email_from_email": settings.email_from_email,
        "email_reply_to": settings.email_reply_to,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_username": settings.smtp_username,
        "smtp_password_secret": "********" if settings.smtp_password_secret else None,
        "smtp_use_tls": settings.smtp_use_tls,
        "smtp_allow_self_signed": settings.smtp_allow_self_signed,
        "smtp_test_recipient": settings.smtp_test_recipient,
        "support_email": settings.support_email,
        "ops_alert_email": settings.ops_alert_email,
        "acme_directory_url": settings.acme_directory_url,
        "acme_client": settings.acme_client,
        "certificate_status": settings.certificate_status,
        "certificate_issuer": settings.certificate_issuer,
        "certificate_expires_at": _dt_value(settings.certificate_expires_at),
        "last_renewed_at": _dt_value(settings.last_renewed_at),
        "notes": settings.notes,
        "created_at": _dt_value(settings.created_at),
        "updated_at": _dt_value(settings.updated_at),
    }


def _catalog_sku_summary(sku: models.CatalogSKU) -> dict[str, Any]:
    return {
        "id": sku.id,
        "code": sku.code,
        "name": sku.name,
        "description": sku.description,
        "term": _enum_value(sku.term),
        "trial_days": sku.trial_days,
        "amount_cents": sku.amount_cents,
        "currency": sku.currency,
        "min_usage_limit": sku.min_usage_limit,
        "max_usage_limit": sku.max_usage_limit,
        "is_active": bool(sku.is_active),
        "created_at": _dt_value(sku.created_at),
        "updated_at": _dt_value(sku.updated_at),
    }


def _tenant_control_summary(db: Session, *, amo: models.AMO, include_detail: bool = False) -> dict[str, Any]:
    users_total = db.query(func.count(models.User.id)).filter(models.User.amo_id == amo.id).scalar() or 0
    admins_total = (
        db.query(func.count(models.User.id))
        .filter(models.User.amo_id == amo.id, models.User.is_amo_admin.is_(True), models.User.is_superuser.is_(False))
        .scalar()
        or 0
    )
    active_users = (
        db.query(func.count(models.User.id))
        .filter(models.User.amo_id == amo.id, models.User.is_active.is_(True))
        .scalar()
        or 0
    )
    modules = (
        db.query(models.ModuleSubscription)
        .filter(models.ModuleSubscription.amo_id == amo.id)
        .order_by(models.ModuleSubscription.module_code.asc())
        .all()
    )
    latest_license = _latest_license_for_amo(db, amo_id=amo.id)
    open_invoices = (
        db.query(func.count(models.BillingInvoice.id))
        .filter(models.BillingInvoice.amo_id == amo.id, models.BillingInvoice.status == models.InvoiceStatus.PENDING)
        .scalar()
        or 0
    )
    latest_invoice = (
        db.query(models.BillingInvoice)
        .filter(models.BillingInvoice.amo_id == amo.id)
        .order_by(models.BillingInvoice.issued_at.desc(), models.BillingInvoice.created_at.desc())
        .first()
    )
    payload: dict[str, Any] = {
        "id": amo.id,
        "amo_code": amo.amo_code,
        "name": amo.name,
        "icao_code": amo.icao_code,
        "country": amo.country,
        "login_slug": amo.login_slug,
        "contact_email": amo.contact_email,
        "contact_phone": amo.contact_phone,
        "time_zone": amo.time_zone,
        "is_demo": bool(amo.is_demo),
        "is_active": bool(amo.is_active),
        "created_at": _dt_value(amo.created_at),
        "updated_at": _dt_value(amo.updated_at),
        "counts": {
            "users_total": int(users_total),
            "active_users": int(active_users),
            "tenant_admins": int(admins_total),
            "modules_total": len(modules),
            "modules_enabled": sum(1 for item in modules if item.status == models.ModuleSubscriptionStatus.ENABLED),
            "open_invoices": int(open_invoices),
        },
        "subscription": _license_summary(latest_license),
        "access_status": services.get_billing_access_status(db, amo_id=amo.id).model_dump(mode="json"),
        "latest_invoice": _invoice_summary(latest_invoice) if latest_invoice else None,
        "modules": [_module_summary(item) for item in modules],
    }
    if include_detail:
        payload["invoices"] = [
            _invoice_summary(invoice)
            for invoice in db.query(models.BillingInvoice)
            .filter(models.BillingInvoice.amo_id == amo.id)
            .order_by(models.BillingInvoice.issued_at.desc(), models.BillingInvoice.created_at.desc())
            .limit(25).all()
        ]
        payload["usage_meters"] = [
            {
                "id": meter.id,
                "meter_key": meter.meter_key,
                "used_units": meter.used_units,
                "last_recorded_at": _dt_value(meter.last_recorded_at),
                "license_id": meter.license_id,
            }
            for meter in db.query(models.UsageMeter)
            .filter(models.UsageMeter.amo_id == amo.id)
            .order_by(models.UsageMeter.meter_key.asc()).all()
        ]
        payload["module_performance"] = _module_performance_summary(db, amo_id=amo.id)
        payload["support_items"] = [item for item in _support_items_summary(db, limit=250) if item.get("amo_id") == amo.id]
        payload["recent_users"] = [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": _enum_value(user.role),
                "is_active": bool(user.is_active),
                "is_amo_admin": bool(user.is_amo_admin),
                "last_login_at": _dt_value(user.last_login_at),
            }
            for user in db.query(models.User)
            .filter(models.User.amo_id == amo.id)
            .order_by(models.User.created_at.desc()).limit(25).all()
        ]
    return payload


def _get_tenant_or_404(db: Session, *, amo_id: str) -> models.AMO:
    amo = db.query(models.AMO).filter(models.AMO.id == amo_id).first()
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return amo


def _latest_availability_map_for_users(
    db: Session, *, amo_id: str, user_ids: list[str]
) -> dict[str, object]:
    if not user_ids:
        return {}
    try:
        from amodb.apps.quality import models as quality_models

        rows = (
            db.query(quality_models.UserAvailability)
            .filter(
                quality_models.UserAvailability.amo_id == amo_id,
                quality_models.UserAvailability.user_id.in_(user_ids),
            )
            .order_by(
                quality_models.UserAvailability.updated_at.desc(),
                quality_models.UserAvailability.effective_from.desc(),
            )
            .all()
        )
        latest: dict[str, object] = {}
        for row in rows:
            key = str(row.user_id)
            if key not in latest:
                latest[key] = row
        return latest
    except Exception:
        return {}


def _current_availability_status(row: object | None) -> Optional[str]:
    if row is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        effective_from = getattr(row, 'effective_from', None)
        effective_to = getattr(row, 'effective_to', None)
        if effective_from and effective_from > now:
            return None
        if effective_to and effective_to < now:
            return None
        status_value = getattr(getattr(row, 'status', None), 'value', getattr(row, 'status', None))
        return str(status_value) if status_value else None
    except Exception:
        return None


def _slugify_group_code(value: str) -> str:
    code = re.sub(r'[^A-Z0-9]+', '_', (value or '').strip().upper())
    code = re.sub(r'_+', '_', code).strip('_')
    return code or f'GROUP_{uuid4().hex[:6].upper()}'


def _get_managed_group_or_404(db: Session, *, current_user: models.User, group_id: str) -> models.UserGroup:
    _ensure_user_group_schema(db)
    q = db.query(models.UserGroup).filter(models.UserGroup.id == group_id)
    if not current_user.is_superuser:
        q = q.filter(models.UserGroup.amo_id == current_user.amo_id)
    group = q.first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Group not found.')
    return group


def _get_managed_authorisation_type_or_404(
    db: Session, *, current_user: models.User, authorisation_type_id: str
) -> models.AuthorisationType:
    q = db.query(models.AuthorisationType).filter(models.AuthorisationType.id == authorisation_type_id)
    if not current_user.is_superuser:
        q = q.filter(models.AuthorisationType.amo_id == current_user.amo_id)
    item = q.first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Permission type not found.')
    return item


def _get_managed_user_authorisation_or_404(
    db: Session, *, current_user: models.User, user_authorisation_id: str
) -> models.UserAuthorisation:
    q = db.query(models.UserAuthorisation).filter(models.UserAuthorisation.id == user_authorisation_id)
    item = q.first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User permission not found.')
    user = db.query(models.User).filter(models.User.id == item.user_id).first()
    if not user or (not current_user.is_superuser and user.amo_id != current_user.amo_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User permission not found.')
    return item


def _get_personnel_profile_for_user(db: Session, *, user: models.User) -> Optional[models.PersonnelProfile]:
    return (
        db.query(models.PersonnelProfile)
        .filter(models.PersonnelProfile.amo_id == user.amo_id, models.PersonnelProfile.user_id == user.id)
        .first()
    )


def _set_profile_employment_state(
    profile: Optional[models.PersonnelProfile],
    *,
    employment_status: Optional[str] = None,
    status_value: Optional[str] = None,
    department_name: Optional[str] = None,
    position_title: Optional[str] = None,
) -> None:
    if not profile:
        return
    if employment_status is not None:
        profile.employment_status = employment_status
    if status_value is not None:
        profile.status = status_value
    if department_name is not None:
        profile.department = department_name
    if position_title is not None:
        profile.position_title = position_title


def _delete_user_hard(db: Session, *, actor: models.User, user: models.User) -> None:
    if str(actor.id) == str(user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='You cannot permanently delete the current signed-in user.')

    amo_id = str(user.amo_id)
    user_id = str(user.id)
    user_email = (user.email or '').lower()
    before = {
        'id': user_id,
        'email': user.email,
        'staff_code': user.staff_code,
        'full_name': user.full_name,
    }

    profiles = (
        db.query(models.PersonnelProfile)
        .filter(
            models.PersonnelProfile.amo_id == amo_id,
            or_(
                models.PersonnelProfile.user_id == user_id,
                func.lower(models.PersonnelProfile.email) == user_email,
                models.PersonnelProfile.person_id == user.staff_code,
            ),
        )
        .all()
    )
    for profile in profiles:
        db.delete(profile)

    db.delete(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Unable to permanently delete this user because related operational records still require it: {getattr(exc, "orig", exc)}',
        ) from exc

    audit_services.log_event(
        db,
        amo_id=amo_id,
        actor_user_id=str(actor.id),
        entity_type='accounts.user',
        entity_id=user_id,
        action='HARD_DELETED',
        before=before,
        after=None,
        metadata={'module': 'accounts'},
    )
    db.commit()


def _build_user_export_payload(db: Session, *, user: models.User) -> dict:
    _ensure_user_group_schema(db)
    from amodb.apps.tasks import models as task_models
    from amodb.apps.quality import models as quality_models

    dept = None
    if user.department_id:
        dept = db.query(models.Department).filter(models.Department.id == user.department_id).first()

    permissions = []
    for item in sorted(user.authorisations, key=lambda row: (row.expires_at is None, row.expires_at or date.max), reverse=True):
        permissions.append({
            'id': item.id,
            'code': item.authorisation_type.code if item.authorisation_type else None,
            'label': item.authorisation_type.name if item.authorisation_type else None,
            'maintenance_scope': getattr(getattr(item.authorisation_type, 'maintenance_scope', None), 'value', None),
            'scope_text': item.scope_text,
            'effective_from': item.effective_from.isoformat() if item.effective_from else None,
            'expires_at': item.expires_at.isoformat() if item.expires_at else None,
            'revoked_at': item.revoked_at.isoformat() if item.revoked_at else None,
            'revoked_reason': item.revoked_reason,
            'is_currently_valid': item.is_currently_valid(),
        })

    tasks = []
    for task in (
        db.query(task_models.Task)
        .filter(task_models.Task.amo_id == user.amo_id, task_models.Task.owner_user_id == str(user.id))
        .order_by(task_models.Task.updated_at.desc())
        .limit(250)
        .all()
    ):
        tasks.append({
            'id': str(task.id),
            'title': task.title,
            'status': getattr(task.status, 'value', task.status),
            'priority': task.priority,
            'due_at': task.due_at.isoformat() if task.due_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
        })

    activity = []
    for row in (
        db.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.amo_id == user.amo_id)
        .filter(or_(audit_models.AuditEvent.actor_user_id == str(user.id), audit_models.AuditEvent.entity_id == str(user.id)))
        .order_by(audit_models.AuditEvent.occurred_at.desc())
        .limit(250)
        .all()
    ):
        activity.append({
            'id': str(row.id),
            'occurred_at': row.occurred_at.isoformat() if row.occurred_at else None,
            'action': row.action,
            'entity_type': row.entity_type,
            'entity_id': row.entity_id,
        })

    availability = []
    for row in (
        db.query(quality_models.UserAvailability)
        .filter(quality_models.UserAvailability.amo_id == user.amo_id, quality_models.UserAvailability.user_id == user.id)
        .order_by(quality_models.UserAvailability.updated_at.desc())
        .limit(250)
        .all()
    ):
        availability.append({
            'id': str(row.id),
            'status': getattr(row.status, 'value', row.status),
            'effective_from': row.effective_from.isoformat() if row.effective_from else None,
            'effective_to': row.effective_to.isoformat() if row.effective_to else None,
            'note': row.note,
            'updated_at': row.updated_at.isoformat() if row.updated_at else None,
        })

    memberships = (
        db.query(models.UserGroupMember, models.UserGroup)
        .join(models.UserGroup, models.UserGroup.id == models.UserGroupMember.group_id)
        .filter(models.UserGroupMember.user_id == user.id)
        .order_by(models.UserGroup.name.asc())
        .all()
    )
    groups = [
        {
            'membership_id': member.id,
            'group_id': group.id,
            'code': group.code,
            'name': group.name,
            'group_type': getattr(group.group_type, 'value', group.group_type),
            'member_role': member.member_role,
            'added_at': member.added_at.isoformat() if member.added_at else None,
        }
        for member, group in memberships
    ]

    profile = _get_personnel_profile_for_user(db, user=user)
    department_name = dept.name if dept else None
    return {
        'user': {
            'id': user.id,
            'amo_id': user.amo_id,
            'staff_code': user.staff_code,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.full_name,
            'role': getattr(user.role, 'value', user.role),
            'position_title': user.position_title,
            'department_id': user.department_id,
            'department_name': department_name,
            'phone': user.phone,
            'secondary_phone': user.secondary_phone,
            'is_active': user.is_active,
            'is_superuser': user.is_superuser,
            'is_amo_admin': user.is_amo_admin,
            'is_auditor': user.is_auditor,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': user.updated_at.isoformat() if user.updated_at else None,
            'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
            'last_login_ip': user.last_login_ip,
            'last_login_user_agent': user.last_login_user_agent,
            'must_change_password': user.must_change_password,
            'password_changed_at': user.password_changed_at.isoformat() if user.password_changed_at else None,
            'token_revoked_at': user.token_revoked_at.isoformat() if user.token_revoked_at else None,
            'deactivated_at': user.deactivated_at.isoformat() if user.deactivated_at else None,
            'deactivated_reason': user.deactivated_reason,
        },
        'personnel_profile': None if profile is None else {
            'id': profile.id,
            'person_id': profile.person_id,
            'employment_status': profile.employment_status,
            'status': profile.status,
            'hire_date': profile.hire_date.isoformat() if profile.hire_date else None,
            'department': profile.department,
            'position_title': profile.position_title,
            'phone_number': profile.phone_number,
            'secondary_phone': profile.secondary_phone,
            'email': profile.email,
        },
        'permissions': permissions,
        'tasks': tasks,
        'activity_log': activity,
        'availability_history': availability,
        'group_memberships': groups,
    }


def _json_download_response(*, filename: str, payload: object) -> Response:
    content = json.dumps(payload, indent=2, default=str)
    return Response(
        content=content.encode('utf-8'),
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


def _csv_download_response(*, filename: str, rows: list[dict]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()) if rows else ['id'])
    writer.writeheader()
    if rows:
        writer.writerows(rows)
    return Response(
        content=buffer.getvalue().encode('utf-8'),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# SUPERUSER CONTEXT (DEMO / REAL)
# ---------------------------------------------------------------------------


@router.get(
    "/context",
    response_model=schemas.UserActiveContextRead,
    summary="Get the active demo/real context (superuser only)",
)
def get_admin_context(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    context = services.get_or_create_user_active_context(db, user=current_user)
    db.commit()
    db.refresh(context)
    return context


@router.post(
    "/context",
    response_model=schemas.UserActiveContextRead,
    summary="Set the active demo/real context (superuser only)",
)
def set_admin_context(
    payload: schemas.UserActiveContextUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    context = services.set_user_active_context(
        db,
        user=current_user,
        data_mode=payload.data_mode,
        active_amo_id=payload.active_amo_id,
    )
    db.commit()
    db.refresh(context)
    return context


@router.post(
    "/amos",
    response_model=schemas.AMORead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AMO (platform superuser only)",
)
def create_amo(
    payload: schemas.AMOCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create a new AMO.

    Only the platform SUPERUSER can call this. Normal AMO admins cannot
    create new organisations.
    """
    _require_superuser(current_user)

    login_slug = payload.login_slug.strip().lower()

    if login_slug in RESERVED_PLATFORM_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login slug is reserved for platform support.",
        )

    existing = (
        db.query(models.AMO)
        .filter(
            (models.AMO.amo_code == payload.amo_code)
            | (models.AMO.login_slug == login_slug)
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AMO with this code or login_slug already exists.",
        )

    amo = models.AMO(
        amo_code=payload.amo_code,
        name=payload.name,
        icao_code=payload.icao_code,
        country=payload.country,
        login_slug=login_slug,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        time_zone=payload.time_zone,
        is_demo=bool(payload.is_demo),
        is_active=True,
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    _ensure_amo_storage_dirs(amo.id)

    try:
        default_sku = os.getenv("AMODB_DEFAULT_TRIAL_SKU", "").strip()
        if not default_sku:
            skus = services.list_catalog_skus(db, include_inactive=False)
            default_sku = skus[0].code if skus else ""

        if default_sku:
            services.start_trial(
                db,
                amo_id=amo.id,
                sku_code=default_sku,
                idempotency_key=f"amo-create-{amo.id}-{uuid4().hex}",
            )
    except Exception as exc:
        # Tenant creation must not fail merely because commercial setup is not
        # complete yet. The platform superuser can attach a subscription from
        # /platform/control after creating the tenant.
        db.rollback()
        db.add(
            models.BillingAuditLog(
                amo_id=amo.id,
                event_type="TENANT_SUBSCRIPTION_BOOTSTRAP_SKIPPED",
                details=json.dumps({"error": str(getattr(exc, "detail", exc))}),
            )
        )
        db.commit()
    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=str(amo.id),
            action="create",
            actor_user_id=current_user.id,
            before_json=None,
            after_json={
                "amo_code": amo.amo_code,
                "login_slug": amo.login_slug,
                "name": amo.name,
                "billing_bootstrap": {"status": "created", "note": "tenant creation does not depend on billing bootstrap"},
            },
        ),
    )
    db.commit()
    return amo


@router.get(
    "/amos",
    response_model=List[schemas.AMORead],
    summary="List all AMOs (platform superuser only)",
)
def list_amos(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List all AMOs in the platform.

    Only SUPERUSER can see the full list.
    """
    _require_superuser(current_user)
    return db.query(models.AMO).order_by(models.AMO.amo_code.asc()).all()


@router.put(
    "/amos/{amo_id}",
    response_model=schemas.AMORead,
    summary="Update an AMO (platform superuser only)",
)
def update_amo(
    amo_id: str,
    payload: schemas.AMOUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = db.query(models.AMO).filter(models.AMO.id == amo_id).first()
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(amo, field, value)
    db.add(amo)
    db.commit()
    db.refresh(amo)

    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=str(amo.id),
            action="update",
            actor_user_id=current_user.id,
            before_json=None,
            after_json=update_data,
        ),
    )
    db.commit()
    return amo


@router.delete(
    "/amos/{amo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an AMO (platform superuser only)",
)
def deactivate_amo(
    amo_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = db.query(models.AMO).filter(models.AMO.id == amo_id).first()
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO not found.")
    amo.is_active = False
    db.add(amo)
    db.commit()
    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=str(amo.id),
            action="deactivate",
            actor_user_id=current_user.id,
            before_json=None,
            after_json={"is_active": False},
        ),
    )
    db.commit()
    return


@router.post(
    "/amos/{amo_id}/trial-extend",
    response_model=schemas.SubscriptionRead,
    summary="Extend AMO trial period (platform superuser only)",
)
def extend_amo_trial(
    amo_id: str,
    payload: schemas.TrialExtendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    license = services.get_current_subscription(db, amo_id=amo_id)
    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active or trialing subscription found for this AMO.",
        )
    if license.status not in (
        models.LicenseStatus.TRIALING,
        models.LicenseStatus.EXPIRED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only trial or expired subscriptions can be extended.",
        )

    now = datetime.now(timezone.utc)
    extend_delta = timedelta(days=payload.extend_days)
    existing_end = license.trial_ends_at or license.current_period_end
    base = existing_end if existing_end and existing_end > now else now
    license.trial_ends_at = base + extend_delta
    license.current_period_end = license.trial_ends_at
    license.trial_grace_expires_at = None
    license.status = models.LicenseStatus.TRIALING
    license.is_read_only = False
    if not license.trial_started_at:
        license.trial_started_at = now

    db.add(license)
    db.commit()
    db.refresh(license)

    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="TenantLicense",
            entity_id=str(license.id),
            action="trial_extend",
            actor_user_id=current_user.id,
            before_json=None,
            after_json={"extend_days": payload.extend_days},
        ),
    )
    db.commit()
    return license


# ---------------------------------------------------------------------------
# DEPARTMENTS (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/departments",
    response_model=schemas.DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create department within current user's AMO (or any AMO for superuser)",
)
def create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a department.

    - Normal AMO admins: can only create departments in their own AMO.
    - SUPERUSER: can create departments in any AMO.
    """
    if payload.amo_id != current_user.amo_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create department for another AMO.",
        )

    dup = (
        db.query(models.Department)
        .filter(
            models.Department.amo_id == payload.amo_id,
            models.Department.code == payload.code,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department code already exists for this AMO.",
        )

    dept = models.Department(
        amo_id=payload.amo_id,
        code=payload.code,
        name=payload.name,
        default_route=payload.default_route,
        sort_order=payload.sort_order,
        is_active=True,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get(
    "/departments",
    response_model=List[schemas.DepartmentRead],
    summary="List departments (current AMO by default; any AMO for superuser)",
)
def list_departments(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List departments.

    - Normal users / AMO admins: always scoped to their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to inspect another AMO;
      if omitted, sees departments for their own (ROOT/system) AMO.
    """
    q = db.query(models.Department)
    target_amo_id = None

    if current_user.is_superuser:
        target_amo_id = amo_id or current_user.amo_id
    else:
        target_amo_id = current_user.amo_id

    if target_amo_id:
        q = q.filter(models.Department.amo_id == target_amo_id)

    departments = q.order_by(models.Department.sort_order.asc()).all()
    if not departments and target_amo_id:
        created = services.seed_default_departments(db, amo_id=target_amo_id)
        if created:
            db.commit()
            departments = (
                db.query(models.Department)
                .filter(models.Department.amo_id == target_amo_id)
                .order_by(models.Department.sort_order.asc())
                .all()
            )

    return departments


@router.get(
    "/staff-code-suggestions",
    response_model=schemas.StaffCodeSuggestions,
    summary="Suggest staff codes based on first/last name",
)
def staff_code_suggestions(
    first_name: str,
    last_name: str,
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if not first_name.strip() or not last_name.strip():
        raise HTTPException(status_code=400, detail="First and last name are required.")

    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id

    def _clean(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", value.strip().upper())

    first = _clean(first_name)
    last = _clean(last_name)
    if not first or not last:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    base_candidates = [
        f"{first[0]}{last}",
        f"{first}{last[0]}",
        f"{first}{last}",
        f"{first[0]}{last[:6]}",
        f"{last}{first[0]}",
    ]

    existing = {
        row[0]
        for row in db.query(models.User.staff_code)
        .filter(models.User.amo_id == target_amo_id)
        .all()
    }

    suggestions: List[str] = []
    for candidate in base_candidates:
        if candidate and candidate not in existing and candidate not in suggestions:
            suggestions.append(candidate)

    suffix = 1
    while len(suggestions) < 5:
        base = base_candidates[0]
        candidate = f"{base}{suffix}"
        suffix += 1
        if candidate in existing or candidate in suggestions:
            continue
        suggestions.append(candidate)

    return schemas.StaffCodeSuggestions(suggestions=suggestions)


@router.put(
    "/departments/{department_id}",
    response_model=schemas.DepartmentRead,
    summary="Update a department (AMO admin or superuser)",
)
def update_department(
    department_id: str,
    payload: schemas.DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    dept = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    if not current_user.is_superuser and dept.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update department for another AMO.",
        )

    if payload.name is not None:
        dept.name = payload.name
    if payload.default_route is not None:
        dept.default_route = payload.default_route
    if payload.sort_order is not None:
        dept.sort_order = payload.sort_order
    if payload.is_active is not None:
        dept.is_active = payload.is_active

    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


# ---------------------------------------------------------------------------
# AMO ASSETS (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/assets",
    response_model=schemas.AMOAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an AMO asset (AMO admin or superuser)",
)
def create_amo_asset(
    payload: schemas.AMOAssetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create an AMO asset.

    - Normal AMO admins: can only create assets for their own AMO.
    - SUPERUSER: can create assets for any AMO.
    """
    if payload.amo_id != current_user.amo_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create assets for another AMO.",
        )

    asset = models.AMOAsset(
        **payload.model_dump(exclude={"is_active"}),
        is_active=payload.is_active if payload.is_active is not None else True,
        uploaded_by_user_id=current_user.id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get(
    "/assets",
    response_model=List[schemas.AMOAssetRead],
    summary="List AMO assets (current AMO by default; any AMO for superuser)",
)
def list_amo_assets(
    amo_id: Optional[str] = None,
    kind: Optional[models.AMOAssetKind] = None,
    only_active: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List assets.

    - Normal users / AMO admins: always scoped to their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to inspect another AMO;
      if omitted, sees assets for their own (ROOT/system) AMO.
    """
    q = db.query(models.AMOAsset)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.AMOAsset.amo_id == amo_id)
    else:
        q = q.filter(models.AMOAsset.amo_id == current_user.amo_id)

    if kind:
        q = q.filter(models.AMOAsset.kind == kind)
    if only_active:
        q = q.filter(models.AMOAsset.is_active.is_(True))

    return q.order_by(models.AMOAsset.created_at.desc()).all()


@router.get(
    "/assets/{asset_id}",
    response_model=schemas.AMOAssetRead,
    summary="Get an AMO asset by id",
)
def get_amo_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    if not current_user.is_superuser and asset.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this asset.")

    return asset


@router.put(
    "/assets/{asset_id}",
    response_model=schemas.AMOAssetRead,
    summary="Update an AMO asset (AMO admin or superuser)",
)
def update_amo_asset(
    asset_id: str,
    payload: schemas.AMOAssetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    if not current_user.is_superuser and asset.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this asset.")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(asset, field, value)

    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete(
    "/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an AMO asset (AMO admin or superuser)",
)
def deactivate_amo_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    if not current_user.is_superuser and asset.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this asset.")

    asset.is_active = False
    db.add(asset)
    db.commit()
    return


# ---------------------------------------------------------------------------
# USER MANAGEMENT (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/users",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user in current AMO (or any AMO for superuser)",
)
def create_user_admin(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a user.

    - Normal AMO admins: payload.amo_id is forced to their AMO.
    - SUPERUSER: can set any amo_id in payload.
    - Only SUPERUSER can create SUPERUSER role.
    - Enforces uniqueness for email OR staff_code within the AMO.
    """
    if not current_user.is_superuser:
        payload = payload.copy(update={"amo_id": current_user.amo_id})

    if (not current_user.is_superuser) and (payload.role == models.AccountRole.SUPERUSER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform superuser can create superuser accounts.",
        )

    if payload.role == models.AccountRole.SUPERUSER:
        payload = payload.copy(update={"amo_id": None, "department_id": None})

    try:
        user = services.create_user(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.user",
        entity_id=str(user.id),
        action="CREATED",
        after={"email": user.email, "role": user.role, "is_active": user.is_active},
        metadata={"module": "accounts"},
    )
    return user


@router.get(
    "/users",
    response_model=List[schemas.UserRead],
    summary="List users (current AMO by default; any AMO for superuser)",
)
def list_users_admin(
    amo_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    List users.

    - Normal AMO admins: see only users in their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to list users for that AMO;
      if omitted, sees users for their own (ROOT/system) AMO.
    - Supports skip/limit/search for frontend paging and filtering.
    """
    q = db.query(models.User)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.User.amo_id == amo_id)
    else:
        q = q.filter(models.User.amo_id == current_user.amo_id)

    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.User.full_name.ilike(s),
                models.User.email.ilike(s),
                models.User.staff_code.ilike(s),
            )
        )

    q = q.order_by(models.User.full_name.asc()).offset(skip).limit(limit)
    return q.all()


@router.get(
    "/users/{user_id}",
    response_model=schemas.UserRead,
    summary="Get one user (scoped to current AMO for admins; any AMO for superuser)",
)
def get_user_admin(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)


@router.put(
    "/users/{user_id}",
    response_model=schemas.UserRead,
    summary="Update user (scoped to current AMO for admins; any AMO for superuser)",
)
def update_user_admin(
    user_id: str,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.AccountRole.SUPERUSER, models.AccountRole.AMO_ADMIN)
    ),
):
    """
    Update a user.

    - AMO_ADMIN: can only update users in their AMO.
    - SUPERUSER: can update any user by id.
    - Blocks non-superusers from role escalation to SUPERUSER and from changing amo_id.
    """
    q = db.query(models.User).filter(models.User.id == user_id)

    if not current_user.is_superuser:
        q = q.filter(models.User.amo_id == current_user.amo_id)

    user = q.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not in your AMO.",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if not current_user.is_superuser:
        if "amo_id" in update_data or "is_superuser" in update_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot modify amo_id or superuser status.",
            )
        if "role" in update_data and update_data["role"] == models.AccountRole.SUPERUSER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot assign SUPERUSER role.",
            )

    # NOTE: services.update_user() should also enforce what fields are allowed.
    try:
        user = services.update_user(db, user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.user",
        entity_id=str(user.id),
        action="UPDATED",
        after=update_data,
        metadata={"module": "accounts"},
    )
    return user


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete user (scoped to current AMO for admins; any AMO for superuser)",
)
def delete_user_admin(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    _delete_user_hard(db, actor=current_user, user=user)
    return


@router.post(
    "/personnel/import",
    response_model=schemas.PersonnelImportSummary,
    summary="Import personnel profiles and linked login accounts from People Excel sheet",
)
async def import_personnel_admin(
    file: UploadFile = File(...),
    dry_run: bool = True,
    sheet_name: str = "People",
    amo_id: Optional[str] = None,
    decisions_json: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    try:
        rows = parse_people_sheet(content, filename=file.filename or "upload.xlsx", sheet_name=sheet_name)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    before_state = None
    try:
        decisions: dict[int, str] = {}
        if decisions_json:
            raw = json.loads(decisions_json)
            if isinstance(raw, dict):
                decisions = {int(k): str(v) for k, v in raw.items()}
        if not dry_run:
            before_state = _capture_import_state(db, amo_id=target_amo_id, rows=rows)
        summary = import_personnel_rows(
            db,
            amo_id=target_amo_id,
            rows=rows,
            dry_run=dry_run,
            decisions=decisions,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError as exc:
        db.rollback()
        detail = str(getattr(exc, "orig", exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Personnel import failed due to a data conflict: {detail}",
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Personnel import database error: {exc}",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Personnel import failed unexpectedly. Check backend logs for details.",
        )

    metadata = {"module": "accounts", "sheet": sheet_name}
    if not dry_run and before_state is not None:
        after_state = _capture_import_state(db, amo_id=target_amo_id, rows=rows)
        metadata["undo_payload"] = _build_undo_payload(before_state, after_state)
        metadata["undo_available"] = True

    audit_services.log_event(
        db,
        amo_id=target_amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.personnel_import",
        entity_id=target_amo_id,
        action="DRY_RUN" if dry_run else "IMPORT",
        after=summary.model_dump(),
        metadata=metadata,
    )
    return summary


@router.post(
    "/personnel/import/undo-last",
    response_model=schemas.PersonnelImportSummary,
    summary="Undo last live personnel import using audit snapshot",
)
def undo_last_personnel_import(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id
    event = (
        db.query(audit_models.AuditEvent)
        .filter(
            audit_models.AuditEvent.amo_id == target_amo_id,
            audit_models.AuditEvent.entity_type == "accounts.personnel_import",
            audit_models.AuditEvent.action == "IMPORT",
        )
        .order_by(audit_models.AuditEvent.occurred_at.desc())
        .first()
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No live personnel import found to undo.")
    metadata = event.metadata_json or {}
    undo_payload = metadata.get("undo_payload")
    if not isinstance(undo_payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Latest personnel import has no undo snapshot.")
    if metadata.get("undo_applied"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Latest personnel import already undone.")

    created_profile_ids = undo_payload.get("created_profile_ids") or []
    created_user_ids = undo_payload.get("created_user_ids") or []
    updated_profiles_before = undo_payload.get("updated_profiles_before") or []
    updated_users_before = undo_payload.get("updated_users_before") or []

    if created_profile_ids:
        db.query(models.PersonnelProfile).filter(models.PersonnelProfile.id.in_(created_profile_ids)).delete(synchronize_session=False)
    if created_user_ids:
        db.query(models.User).filter(models.User.id.in_(created_user_ids)).delete(synchronize_session=False)

    for state in updated_profiles_before:
        profile = db.query(models.PersonnelProfile).filter(models.PersonnelProfile.id == state.get("id")).first()
        if not profile:
            continue
        for key in [
            "person_id", "user_id", "first_name", "last_name", "full_name", "national_id", "amel_no",
            "internal_certification_stamp_no", "department", "position_title", "phone_number", "secondary_phone",
            "email", "employment_status", "status", "birth_place",
        ]:
            setattr(profile, key, state.get(key))
        profile.initial_authorization_date = _from_iso_date(state.get("initial_authorization_date"))
        profile.hire_date = _from_iso_date(state.get("hire_date"))
        profile.date_of_birth = _from_iso_date(state.get("date_of_birth"))

    for state in updated_users_before:
        user = db.query(models.User).filter(models.User.id == state.get("id")).first()
        if not user:
            continue
        for key in [
            "staff_code", "email", "first_name", "last_name", "full_name", "position_title",
            "phone", "secondary_phone", "is_active", "must_change_password",
        ]:
            setattr(user, key, state.get(key))
        user.password_changed_at = _from_iso_datetime(state.get("password_changed_at"))

    metadata["undo_applied"] = True
    metadata["undo_applied_at"] = datetime.now(timezone.utc).isoformat()
    event.metadata_json = metadata
    db.add(event)
    db.commit()

    audit_services.log_event(
        db,
        amo_id=target_amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.personnel_import",
        entity_id=target_amo_id,
        action="UNDO_LAST",
        after={
            "created_profile_ids_removed": len(created_profile_ids),
            "created_user_ids_removed": len(created_user_ids),
            "profiles_restored": len(updated_profiles_before),
            "users_restored": len(updated_users_before),
        },
        metadata={"module": "accounts", "source_event_id": event.id},
    )

    return schemas.PersonnelImportSummary(
        dry_run=False,
        rows_processed=0,
        created_personnel=0,
        updated_personnel=0,
        created_accounts=0,
        updated_accounts=0,
        skipped_accounts=0,
        rejected_rows=0,
        skipped_rows=0,
        issues=[],
        conflicts=[],
    )


@router.post("/users/{user_id}/commands/disable", response_model=schemas.UserCommandResult)
def command_disable_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.deactivated_reason = "disabled_by_admin_command"
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="DISABLED",
        after={"is_active": False},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="disable", status="ok", effective_at=datetime.now(timezone.utc))


@router.post("/users/{user_id}/commands/enable", response_model=schemas.UserCommandResult)
def command_enable_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    user.is_active = True
    user.deactivated_at = None
    user.deactivated_reason = None
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="ENABLED",
        after={"is_active": True},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="enable", status="ok", effective_at=datetime.now(timezone.utc))


@router.post("/users/{user_id}/commands/revoke-access", response_model=schemas.UserCommandResult)
def command_revoke_access(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    user.token_revoked_at = now
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="ACCESS_REVOKED",
        after={"token_revoked_at": now.isoformat()},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="revoke-access", status="ok", effective_at=now)


@router.post("/users/{user_id}/commands/force-password-reset", response_model=schemas.UserCommandResult)
def command_force_password_reset(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    user.must_change_password = True
    user.token_revoked_at = now
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="PASSWORD_RESET_FORCED",
        after={"must_change_password": True, "token_revoked_at": now.isoformat()},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="force-password-reset", status="ok", effective_at=now)


@router.post("/users/{user_id}/commands/notify", response_model=schemas.UserCommandResult)
def command_notify_user(
    user_id: str,
    payload: schemas.UserCommandNotifyPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    notification_service.send_email(
        template_key="accounts.user.command.notify",
        recipient=user.email,
        subject=payload.subject,
        context={"message": payload.message, "user_id": user.id, "actor_user_id": current_user.id},
        correlation_id=f"user-notify-{user.id}-{int(now.timestamp())}",
        amo_id=user.amo_id,
        db=db,
    )
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="NOTIFIED",
        after={"subject": payload.subject},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="notify", status="ok", effective_at=now)


@router.post("/users/{user_id}/commands/schedule-review", response_model=schemas.UserCommandResult)
def command_schedule_review(
    user_id: str,
    payload: schemas.UserCommandSchedulePayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    task = task_services.create_task(
        db,
        amo_id=user.amo_id,
        title=payload.title,
        description=payload.description,
        owner_user_id=user.id,
        supervisor_user_id=current_user.id,
        due_at=payload.due_at,
        entity_type="accounts.user",
        entity_id=user.id,
        priority=payload.priority,
        metadata={"scheduled_by": current_user.id, "command": "schedule-review"},
    )
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="REVIEW_SCHEDULED",
        after={"task_id": task.id, "due_at": payload.due_at.isoformat() if payload.due_at else None},
        metadata={"task_id": task.id},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="schedule-review", status="ok", effective_at=now, task_id=task.id)


def _apply_leave_status(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    status_value: str,
    note: Optional[str],
    effective_from: Optional[datetime],
    effective_to: Optional[datetime],
    actor_user_id: Optional[str],
) -> None:
    from amodb.apps.quality import models as quality_models

    item = quality_models.UserAvailability(
        amo_id=amo_id,
        user_id=user_id,
        status=quality_models.UserAvailabilityStatus(status_value),
        effective_from=effective_from or datetime.now(timezone.utc),
        effective_to=effective_to,
        note=(note or '').strip() or None,
        updated_by_user_id=actor_user_id,
    )
    db.add(item)


@router.post(
    "/users/bulk",
    response_model=schemas.BulkUserActionResult,
    summary="Apply bulk actions to selected users",
)
def bulk_user_action(
    payload: schemas.BulkUserActionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user_ids = [uid for uid in payload.user_ids if str(uid).strip()]
    if not user_ids:
        raise HTTPException(status_code=400, detail='Select at least one user.')

    users_query = db.query(models.User).filter(models.User.id.in_(user_ids))
    if not current_user.is_superuser:
        users_query = users_query.filter(models.User.amo_id == current_user.amo_id)
    users = users_query.all()
    if len(users) != len(set(user_ids)):
        raise HTTPException(status_code=404, detail='One or more selected users could not be found in scope.')

    affected_ids: list[str] = []
    target_department_name = None
    target_group = None
    if payload.action == 'assign_department':
        if not payload.department_id:
            raise HTTPException(status_code=400, detail='department_id is required for department assignment.')
        dept = db.query(models.Department).filter(models.Department.id == payload.department_id).first()
        if not dept:
            raise HTTPException(status_code=404, detail='Department not found.')
        target_department_name = dept.name
        for user in users:
            if dept.amo_id != user.amo_id:
                raise HTTPException(status_code=400, detail='Selected department does not belong to every chosen user.')
    if payload.action in {'add_group', 'remove_group'}:
        if not payload.group_id:
            raise HTTPException(status_code=400, detail='group_id is required for this action.')
        target_group = _get_managed_group_or_404(db, current_user=current_user, group_id=payload.group_id)

    for user in users:
        if payload.action == 'enable':
            user.is_active = True
            user.deactivated_at = None
            user.deactivated_reason = None
        elif payload.action == 'disable':
            user.is_active = False
            user.deactivated_at = datetime.now(timezone.utc)
            user.deactivated_reason = (payload.note or 'bulk_disabled_by_admin').strip()
        elif payload.action == 'assign_department':
            user.department_id = payload.department_id
            _set_profile_employment_state(
                _get_personnel_profile_for_user(db, user=user),
                department_name=target_department_name,
            )
        elif payload.action == 'clear_department':
            user.department_id = None
            _set_profile_employment_state(_get_personnel_profile_for_user(db, user=user), department_name='')
        elif payload.action == 'change_role':
            if payload.role is None:
                raise HTTPException(status_code=400, detail='role is required for role changes.')
            user.role = payload.role
            user.is_amo_admin = payload.role == models.AccountRole.AMO_ADMIN
            user.is_auditor = payload.role == models.AccountRole.AUDITOR
        elif payload.action == 'add_group':
            if user.amo_id != target_group.amo_id:
                raise HTTPException(status_code=400, detail='Selected group does not belong to every chosen user.')
            existing = db.query(models.UserGroupMember).filter(models.UserGroupMember.group_id == target_group.id, models.UserGroupMember.user_id == user.id).first()
            if not existing:
                db.add(models.UserGroupMember(group_id=target_group.id, user_id=user.id, added_by_user_id=current_user.id, member_role='member'))
        elif payload.action == 'remove_group':
            db.query(models.UserGroupMember).filter(models.UserGroupMember.group_id == target_group.id, models.UserGroupMember.user_id == user.id).delete(synchronize_session=False)
        elif payload.action == 'schedule_leave':
            _apply_leave_status(
                db, amo_id=user.amo_id, user_id=user.id, status_value='ON_LEAVE', note=payload.note,
                effective_from=payload.effective_from, effective_to=payload.effective_to, actor_user_id=current_user.id
            )
        elif payload.action == 'return_from_leave':
            _apply_leave_status(
                db, amo_id=user.amo_id, user_id=user.id, status_value='ON_DUTY', note=payload.note,
                effective_from=payload.effective_from, effective_to=payload.effective_to, actor_user_id=current_user.id
            )
        elif payload.action == 'delete':
            _delete_user_hard(db, actor=current_user, user=user)
            affected_ids.append(str(user.id))
            continue
        else:
            raise HTTPException(status_code=400, detail='Unsupported bulk action.')
        db.add(user)
        affected_ids.append(str(user.id))

    if payload.action != 'delete':
        db.commit()

    return schemas.BulkUserActionResult(
        action=payload.action,
        processed=len(affected_ids),
        affected_user_ids=affected_ids,
        detail=f'Bulk action {payload.action} completed for {len(affected_ids)} user(s).',
    )


@router.post(
    "/users/{user_id}/employment-actions",
    response_model=schemas.UserEmploymentActionResult,
    summary="Apply a lifecycle or leave action to one user",
)
def user_employment_action(
    user_id: str,
    payload: schemas.UserEmploymentActionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    profile = _get_personnel_profile_for_user(db, user=user)
    department_name = None
    if payload.department_id:
        dept = db.query(models.Department).filter(models.Department.id == payload.department_id).first()
        if not dept or dept.amo_id != user.amo_id:
            raise HTTPException(status_code=400, detail='Department not found in the selected tenant scope.')
        user.department_id = dept.id
        department_name = dept.name

    if payload.position_title is not None:
        user.position_title = (payload.position_title or '').strip() or None
    if payload.role is not None:
        user.role = payload.role
        user.is_amo_admin = payload.role == models.AccountRole.AMO_ADMIN
        user.is_auditor = payload.role == models.AccountRole.AUDITOR

    action = payload.action
    if action == 'new_hire':
        user.is_active = True
        user.deactivated_at = None
        user.deactivated_reason = None
        _set_profile_employment_state(
            profile,
            employment_status=payload.employment_status or 'Active',
            status_value='Active',
            department_name=department_name if payload.department_id is not None else None,
            position_title=user.position_title,
        )
    elif action in {'promote', 'demote'}:
        if payload.role is None and payload.position_title is None:
            raise HTTPException(status_code=400, detail='Provide a role or title for promotion/demotion.')
        _set_profile_employment_state(profile, position_title=user.position_title)
    elif action == 'transfer':
        if payload.department_id is None and payload.position_title is None:
            raise HTTPException(status_code=400, detail='Provide a department or title for transfer.')
        _set_profile_employment_state(
            profile,
            department_name=department_name if payload.department_id is not None else None,
            position_title=user.position_title if payload.position_title is not None else None,
        )
    elif action == 'resign':
        user.is_active = False
        user.deactivated_at = datetime.now(timezone.utc)
        user.deactivated_reason = (payload.note or 'resigned').strip()
        _set_profile_employment_state(
            profile,
            employment_status=payload.employment_status or 'Resigned',
            status_value='Resigned',
        )
    elif action == 'reinstate':
        user.is_active = True
        user.deactivated_at = None
        user.deactivated_reason = None
        _set_profile_employment_state(
            profile,
            employment_status=payload.employment_status or 'Active',
            status_value='Active',
        )
    elif action == 'schedule_leave':
        _apply_leave_status(
            db, amo_id=user.amo_id, user_id=user.id, status_value='ON_LEAVE', note=payload.note,
            effective_from=payload.effective_from, effective_to=payload.effective_to, actor_user_id=current_user.id
        )
    elif action == 'return_from_leave':
        _apply_leave_status(
            db, amo_id=user.amo_id, user_id=user.id, status_value='ON_DUTY', note=payload.note,
            effective_from=payload.effective_from, effective_to=payload.effective_to, actor_user_id=current_user.id
        )
    else:
        raise HTTPException(status_code=400, detail='Unsupported employment action.')

    db.add(user)
    if profile is not None:
        db.add(profile)
    db.commit()

    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=str(current_user.id),
        entity_type='accounts.user',
        entity_id=str(user.id),
        action=f'LIFECYCLE_{action.upper()}',
        after={
            'role': getattr(user.role, 'value', user.role),
            'department_id': user.department_id,
            'position_title': user.position_title,
            'is_active': user.is_active,
            'note': payload.note,
        },
        metadata={'module': 'accounts'},
    )
    db.commit()
    return schemas.UserEmploymentActionResult(
        user_id=str(user.id),
        action=action,
        effective_at=datetime.now(timezone.utc),
        status='ok',
        note=payload.note,
    )


@router.get(
    "/users/{user_id}/export",
    summary="Download a complete user profile export",
)
def export_single_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    payload = _build_user_export_payload(db, user=user)
    filename = f'user_{user.staff_code or user.id}.json'
    return _json_download_response(filename=filename, payload=payload)


@router.get(
    "/users/export",
    summary="Bulk export selected user records",
)
def export_users(
    ids: str,
    format: str = 'json',
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user_ids = [item.strip() for item in ids.split(',') if item.strip()]
    if not user_ids:
        raise HTTPException(status_code=400, detail='Provide one or more user ids.')
    q = db.query(models.User).filter(models.User.id.in_(user_ids))
    if not current_user.is_superuser:
        q = q.filter(models.User.amo_id == current_user.amo_id)
    users = q.order_by(models.User.full_name.asc()).all()
    if not users:
        raise HTTPException(status_code=404, detail='No users found for export.')

    if format.lower() == 'csv':
        rows = []
        for user in users:
            dept = db.query(models.Department).filter(models.Department.id == user.department_id).first() if user.department_id else None
            rows.append({
                'id': user.id,
                'staff_code': user.staff_code,
                'full_name': user.full_name,
                'email': user.email,
                'role': getattr(user.role, 'value', user.role),
                'position_title': user.position_title or '',
                'department': dept.name if dept else '',
                'is_active': 'Yes' if user.is_active else 'No',
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else '',
            })
        return _csv_download_response(filename='users_export.csv', rows=rows)

    payload = [_build_user_export_payload(db, user=user) for user in users]
    return _json_download_response(filename='users_export.json', payload=payload)


# ---------------------------------------------------------------------------
# PLATFORM SAAS CONTROL PLANE (SUPERUSER ONLY)
# ---------------------------------------------------------------------------


@router.get("/platform/control-plane", summary="Full platform SaaS control-plane state for superusers")
def get_platform_control_plane(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    tenants = db.query(models.AMO).order_by(models.AMO.is_active.desc(), models.AMO.amo_code.asc()).all()
    catalog = services.list_catalog_skus(db, include_inactive=True)
    settings = _get_or_create_platform_settings(db)
    recent_invoices = (
        db.query(models.BillingInvoice)
        .order_by(models.BillingInvoice.issued_at.desc(), models.BillingInvoice.created_at.desc())
        .limit(25).all()
    )
    return {
        "scope": "platform",
        "settings": _platform_settings_summary(settings),
        "module_catalog": PLATFORM_MODULE_CATALOG,
        "tenants": [_tenant_control_summary(db, amo=amo) for amo in tenants],
        "catalog": [_catalog_sku_summary(sku) for sku in catalog],
        "recent_invoices": [_invoice_summary(invoice) for invoice in recent_invoices],
        "diagnostics": _run_platform_diagnostics(db, settings=settings),
        "support_items": _support_items_summary(db, limit=100),
    }


@router.get("/platform/tenants/{amo_id}", summary="Get one tenant with modules, subscription, users, invoices and usage meters")
def get_platform_tenant_detail(
    amo_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = _get_tenant_or_404(db, amo_id=amo_id)
    return _tenant_control_summary(db, amo=amo, include_detail=True)


@router.post("/platform/tenants/{amo_id}/reactivate", summary="Reactivate a deactivated tenant")
def reactivate_platform_tenant(
    amo_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = _get_tenant_or_404(db, amo_id=amo_id)
    amo.is_active = True
    db.add(amo)
    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(entity_type="AMO", entity_id=str(amo.id), action="reactivate", actor_user_id=current_user.id, before_json=None, after_json={"is_active": True}),
    )
    db.commit()
    db.refresh(amo)
    return _tenant_control_summary(db, amo=amo, include_detail=True)


@router.post("/platform/tenants/{amo_id}/modules/bulk", summary="Bulk update tenant module controls")
def bulk_update_platform_tenant_modules(
    amo_id: str,
    payload: schemas.PlatformTenantModulesBulkUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = _get_tenant_or_404(db, amo_id=amo_id)
    changed: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for item in payload.modules:
        module_code = item.module_code.strip()
        if not module_code:
            continue
        if module_code not in PLATFORM_MODULE_CODES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown module code: {module_code}")
        subscription = (
            db.query(models.ModuleSubscription)
            .filter(models.ModuleSubscription.amo_id == amo.id, models.ModuleSubscription.module_code == module_code)
            .first()
        )
        if not subscription:
            subscription = models.ModuleSubscription(amo_id=amo.id, module_code=module_code, effective_from=item.effective_from or now)
        subscription.status = item.status
        subscription.plan_code = item.plan_code
        subscription.effective_from = item.effective_from or subscription.effective_from or now
        subscription.effective_to = item.effective_to
        subscription.metadata_json = item.metadata_json
        db.add(subscription)
        changed.append({"module_code": module_code, "status": _enum_value(item.status)})
    if changed:
        audit_services.create_audit_event(
            db,
            amo_id=amo.id,
            data=audit_schemas.AuditEventCreate(entity_type="ModuleSubscription", entity_id=str(amo.id), action="bulk_update", actor_user_id=current_user.id, before_json=None, after_json={"modules": changed}),
        )
    db.commit()
    db.refresh(amo)
    return _tenant_control_summary(db, amo=amo, include_detail=True)


@router.post("/platform/tenants/{amo_id}/subscription", summary="Platform superuser subscription override or SKU assignment")
def update_platform_tenant_subscription(
    amo_id: str,
    payload: schemas.PlatformTenantSubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = _get_tenant_or_404(db, amo_id=amo_id)
    now = datetime.now(timezone.utc)
    license = _latest_license_for_amo(db, amo_id=amo.id)
    if payload.sku_code:
        sku = db.query(models.CatalogSKU).filter(models.CatalogSKU.code == payload.sku_code).first()
        if not sku:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SKU not found.")
        active = (
            db.query(models.TenantLicense)
            .filter(models.TenantLicense.amo_id == amo.id, models.TenantLicense.status.in_([models.LicenseStatus.ACTIVE, models.LicenseStatus.TRIALING]))
            .all()
        )
        for old_license in active:
            old_license.status = models.LicenseStatus.CANCELLED
            old_license.canceled_at = now
            db.add(old_license)
        period_end = payload.current_period_end or now + (
            timedelta(days=365) if sku.term == models.BillingTerm.ANNUAL else timedelta(days=182) if sku.term == models.BillingTerm.BI_ANNUAL else timedelta(days=30)
        )
        license = models.TenantLicense(
            amo_id=amo.id,
            sku_id=sku.id,
            term=sku.term,
            status=payload.status or models.LicenseStatus.ACTIVE,
            trial_started_at=now if (payload.status or models.LicenseStatus.ACTIVE) == models.LicenseStatus.TRIALING else None,
            trial_ends_at=payload.trial_ends_at,
            trial_grace_expires_at=payload.trial_grace_expires_at,
            is_read_only=bool(payload.is_read_only) if payload.is_read_only is not None else False,
            current_period_start=now,
            current_period_end=period_end,
            notes=payload.notes,
        )
        db.add(license)
    elif license:
        if payload.status is not None:
            license.status = payload.status
        if payload.is_read_only is not None:
            license.is_read_only = payload.is_read_only
        if payload.current_period_end is not None:
            license.current_period_end = payload.current_period_end
        if payload.trial_ends_at is not None:
            license.trial_ends_at = payload.trial_ends_at
        if payload.trial_grace_expires_at is not None:
            license.trial_grace_expires_at = payload.trial_grace_expires_at
        if payload.notes is not None:
            license.notes = payload.notes
        db.add(license)
    else:
        sku = _get_or_create_platform_managed_sku(db)
        period_end = payload.current_period_end or now + timedelta(days=30)
        license = models.TenantLicense(
            amo_id=amo.id,
            sku_id=sku.id,
            term=sku.term,
            status=payload.status or models.LicenseStatus.ACTIVE,
            trial_started_at=now if (payload.status or models.LicenseStatus.ACTIVE) == models.LicenseStatus.TRIALING else None,
            trial_ends_at=payload.trial_ends_at,
            trial_grace_expires_at=payload.trial_grace_expires_at,
            is_read_only=bool(payload.is_read_only) if payload.is_read_only is not None else False,
            current_period_start=now,
            current_period_end=period_end,
            notes=payload.notes or "Created by platform superadmin because no tenant license existed.",
        )
        db.add(license)

    if payload.clear_overdue_invoices:
        overdue_rows = (
            db.query(models.BillingInvoice)
            .filter(
                models.BillingInvoice.amo_id == amo.id,
                models.BillingInvoice.status == models.InvoiceStatus.PENDING,
                models.BillingInvoice.due_at.isnot(None),
                models.BillingInvoice.due_at <= now,
            )
            .all()
        )
        for invoice in overdue_rows:
            invoice.status = models.InvoiceStatus.VOID
            invoice.description = f"{invoice.description or ''}\nVoided by platform superadmin access-clear action.".strip()
            db.add(invoice)

    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(entity_type="TenantLicense", entity_id=str(license.id if license else amo.id), action="platform_override", actor_user_id=current_user.id, before_json=None, after_json=payload.model_dump(mode="json", exclude_unset=True)),
    )
    db.commit()
    db.refresh(amo)
    return _tenant_control_summary(db, amo=amo, include_detail=True)


@router.post("/platform/tenants/{amo_id}/invoices", summary="Create a manual tenant invoice")
def create_platform_tenant_invoice(
    amo_id: str,
    payload: schemas.PlatformTenantInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = _get_tenant_or_404(db, amo_id=amo_id)
    now = datetime.now(timezone.utc)
    license = _latest_license_for_amo(db, amo_id=amo.id)
    idempotency_key = f"platform-manual-invoice-{amo.id}-{uuid4().hex}"
    ledger = models.LedgerEntry(
        amo_id=amo.id,
        license_id=license.id if license else None,
        amount_cents=payload.amount_cents,
        currency=payload.currency.upper(),
        entry_type=models.LedgerEntryType.CHARGE,
        description=payload.description or "Manual platform invoice",
        idempotency_key=idempotency_key,
        recorded_at=now,
    )
    db.add(ledger)
    db.flush()
    status_value = models.InvoiceStatus.PAID if payload.mark_paid else payload.status
    invoice = models.BillingInvoice(
        amo_id=amo.id,
        license_id=license.id if license else None,
        ledger_entry_id=ledger.id,
        amount_cents=payload.amount_cents,
        currency=payload.currency.upper(),
        status=status_value,
        description=payload.description or "Manual platform invoice",
        idempotency_key=idempotency_key,
        issued_at=now,
        due_at=payload.due_at,
        paid_at=now if status_value == models.InvoiceStatus.PAID else None,
    )
    db.add(invoice)
    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(entity_type="BillingInvoice", entity_id=str(invoice.id), action="manual_create", actor_user_id=current_user.id, before_json=None, after_json={"amount_cents": payload.amount_cents, "currency": payload.currency.upper(), "status": _enum_value(status_value)}),
    )
    db.commit()
    db.refresh(invoice)
    return _invoice_summary(invoice)



def _safe_count_table(db: Session, *, table_name: str, amo_id: Optional[str] = None, amo_column: str = "amo_id") -> int | None:
    try:
        inspector = sa.inspect(db.get_bind())
        if not inspector.has_table(table_name):
            return None
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if amo_id and amo_column not in columns:
            return None
        if amo_id:
            return int(db.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE {amo_column} = :amo_id"), {"amo_id": amo_id}).scalar() or 0)
        return int(db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)
    except Exception:
        return None


def _module_performance_summary(db: Session, *, amo_id: str) -> dict[str, Any]:
    table_map = {
        "qms": ["qms_audits", "qms_findings", "qms_cars", "qms_documents", "qms_activity_logs"],
        "quality": ["qms_audits", "qms_findings", "qms_cars", "quality_audits", "audit_events"],
        "training": ["training_courses", "training_requirements", "training_records", "competence_gaps"],
        "manuals": ["manuals", "manual_versions", "manual_change_requests"],
        "aerodoc_hybrid_dms": ["manuals", "manual_versions", "doc_control_documents"],
        "finance_inventory": ["billing_invoices", "ledger_entries", "usage_meters", "inventory_items"],
        "fleet": ["aircraft", "aircraft_documents"],
        "maintenance_program": ["maintenance_programs", "maintenance_program_tasks"],
        "work": ["tasks", "task_cards", "task_assignments"],
        "reliability": ["reliability_events", "reliability_alerts"],
        "technical_records": ["technical_records", "aircraft_documents"],
        "equipment_calibration": ["qms_equipment", "qms_calibration_records"],
        "suppliers": ["qms_suppliers", "qms_supplier_evaluations"],
        "management_review": ["qms_management_reviews", "qms_management_review_actions"],
    }
    result: dict[str, Any] = {}
    for module_code, tables in table_map.items():
        counts: dict[str, int] = {}
        for table_name in tables:
            value = _safe_count_table(db, table_name=table_name, amo_id=amo_id)
            if value is not None:
                counts[table_name] = value
        result[module_code] = {"record_count": sum(counts.values()), "tables": counts, "health": "wired" if counts else "not_detected"}
    return result


def _support_items_summary(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    try:
        query = (db.query(task_models.Task, models.AMO).join(models.AMO, models.AMO.id == task_models.Task.amo_id).filter(or_(task_models.Task.entity_type.ilike("%support%"), task_models.Task.title.ilike("%support%"), task_models.Task.title.ilike("%issue%"), task_models.Task.title.ilike("%error%"), task_models.Task.description.ilike("%support%"), task_models.Task.description.ilike("%issue%"), task_models.Task.description.ilike("%error%"))).order_by(task_models.Task.updated_at.desc()).limit(max(1, min(limit, 500))))
        return [{"id": task.id, "amo_id": task.amo_id, "amo_code": amo.amo_code, "tenant_name": amo.name, "title": task.title, "description": task.description, "status": _enum_value(task.status), "priority": task.priority, "entity_type": task.entity_type, "entity_id": task.entity_id, "due_at": _dt_value(task.due_at), "created_at": _dt_value(task.created_at), "updated_at": _dt_value(task.updated_at)} for task, amo in query.all()]
    except Exception as exc:
        return [{"error": "support_items_unavailable", "detail": str(getattr(exc, "orig", exc))}]


def _check_database(db: Session) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        value = db.execute(text("SELECT 1")).scalar()
        return {"status": "ok" if value == 1 else "degraded", "latency_ms": round((time.perf_counter() - start) * 1000, 2)}
    except Exception as exc:
        return {"status": "error", "latency_ms": round((time.perf_counter() - start) * 1000, 2), "detail": str(getattr(exc, "orig", exc))}


def _check_tcp_host(host: str | None, port: int | None, timeout_seconds: float = 4.0) -> dict[str, Any]:
    if not host or not port:
        return {"status": "not_configured"}
    start = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds): pass
        return {"status": "ok", "latency_ms": round((time.perf_counter() - start) * 1000, 2)}
    except Exception as exc:
        return {"status": "error", "latency_ms": round((time.perf_counter() - start) * 1000, 2), "detail": str(exc)}


def _check_internet(url: str | None, timeout_seconds: float = 4.0) -> dict[str, Any]:
    target = (url or "https://example.com").strip() or "https://example.com"
    start = time.perf_counter()
    try:
        req = urllib.request.Request(target, method="HEAD", headers={"User-Agent": "AMO-Portal-Diagnostics/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", 0) or 0)
        return {"status": "ok" if 200 <= status_code < 500 else "degraded", "status_code": status_code, "latency_ms": round((time.perf_counter() - start) * 1000, 2), "url": target}
    except Exception as exc:
        return {"status": "error", "latency_ms": round((time.perf_counter() - start) * 1000, 2), "url": target, "detail": str(exc)}


def _check_storage() -> dict[str, Any]:
    targets = [AMO_ASSET_UPLOAD_DIR, PLATFORM_ASSET_UPLOAD_DIR, TRAINING_UPLOAD_DIR]
    checks = []
    for target in targets:
        start = time.perf_counter()
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".diag_{uuid4().hex}.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            checks.append({"path": str(target), "status": "ok", "latency_ms": round((time.perf_counter() - start) * 1000, 2)})
        except Exception as exc:
            checks.append({"path": str(target), "status": "error", "latency_ms": round((time.perf_counter() - start) * 1000, 2), "detail": str(exc)})
    return {"status": "ok" if all(item["status"] == "ok" for item in checks) else "degraded", "checks": checks}


def _check_server_throughput(sample_seconds: float = 0.5) -> dict[str, Any]:
    duration = max(0.1, min(float(sample_seconds or 0.5), 3.0))
    start = time.perf_counter()
    iterations = 0
    checksum = 0
    while (time.perf_counter() - start) < duration:
        checksum = (checksum * 33 + iterations) % 1_000_000_007
        iterations += 1
    elapsed = max(time.perf_counter() - start, 0.001)
    return {
        "status": "ok",
        "sample_seconds": round(elapsed, 3),
        "operations": iterations,
        "ops_per_second": round(iterations / elapsed, 2),
        "checksum": checksum,
    }


def _check_database_throughput(db: Session, sample_seconds: float = 0.5) -> dict[str, Any]:
    duration = max(0.1, min(float(sample_seconds or 0.5), 3.0))
    start = time.perf_counter()
    queries = 0
    try:
        while (time.perf_counter() - start) < duration:
            db.execute(text("SELECT 1")).scalar()
            queries += 1
        elapsed = max(time.perf_counter() - start, 0.001)
        return {
            "status": "ok",
            "sample_seconds": round(elapsed, 3),
            "queries": queries,
            "queries_per_second": round(queries / elapsed, 2),
        }
    except Exception as exc:
        elapsed = max(time.perf_counter() - start, 0.001)
        return {
            "status": "error",
            "sample_seconds": round(elapsed, 3),
            "queries": queries,
            "queries_per_second": round(queries / elapsed, 2),
            "detail": str(getattr(exc, "orig", exc)),
        }


def _check_internet_throughput(url: str | None, timeout_seconds: float = 4.0, max_bytes: int = 131_072) -> dict[str, Any]:
    target = (url or "https://example.com").strip() or "https://example.com"
    start = time.perf_counter()
    total = 0
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={
                "User-Agent": "AMO-Portal-Diagnostics/1.0",
                "Range": f"bytes=0-{max_bytes - 1}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            while total < max_bytes:
                chunk = response.read(min(16_384, max_bytes - total))
                if not chunk:
                    break
                total += len(chunk)
            status_code = int(getattr(response, "status", 0) or 0)
        elapsed = max(time.perf_counter() - start, 0.001)
        return {
            "status": "ok" if 200 <= status_code < 500 else "degraded",
            "url": target,
            "status_code": status_code,
            "bytes_read": total,
            "latency_ms": round(elapsed * 1000, 2),
            "kbps": round((total / 1024) / elapsed, 2),
        }
    except Exception as exc:
        elapsed = max(time.perf_counter() - start, 0.001)
        return {
            "status": "error",
            "url": target,
            "bytes_read": total,
            "latency_ms": round(elapsed * 1000, 2),
            "kbps": 0,
            "detail": str(exc),
        }


def _run_platform_diagnostics(
    db: Session,
    *,
    settings: models.PlatformSettings,
    internet_url: str | None = None,
    timeout_seconds: float = 4.0,
    include_throughput: bool = False,
    sample_seconds: float = 0.5,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "server": {"status": "ok", "process": os.getpid()},
        "database": _check_database(db),
        "storage": _check_storage(),
        "internet": _check_internet(internet_url, timeout_seconds=timeout_seconds),
        "smtp_tcp": _check_tcp_host(settings.smtp_host, settings.smtp_port, timeout_seconds=timeout_seconds),
        "email_config": {
            "provider": settings.email_provider or "none",
            "from_email": settings.email_from_email,
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "smtp_username": settings.smtp_username,
            "has_secret": bool(settings.smtp_password_secret),
            "support_email": settings.support_email,
            "ops_alert_email": settings.ops_alert_email,
        },
    }
    if include_throughput:
        payload["throughput"] = {
            "server": _check_server_throughput(sample_seconds=sample_seconds),
            "database": _check_database_throughput(db, sample_seconds=sample_seconds),
            "internet": _check_internet_throughput(internet_url, timeout_seconds=timeout_seconds),
        }
    return payload

# ---------------------------------------------------------------------------
# PLATFORM DIAGNOSTICS (SUPERUSER ONLY)
# ---------------------------------------------------------------------------


@router.get(
    "/platform/diagnostics",
    summary="Platform diagnostics for global superuser control plane",
)
def get_platform_diagnostics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    _require_superuser(current_user)

    def safe_scalar(query, label: str):
        try:
            return query.scalar() or 0
        except Exception as exc:  # pragma: no cover - defensive diagnostics
            return {"error": label, "detail": str(getattr(exc, "orig", exc))}

    total_tenants = safe_scalar(db.query(func.count(models.AMO.id)), "tenants")
    active_tenants = safe_scalar(
        db.query(func.count(models.AMO.id)).filter(models.AMO.is_active.is_(True)),
        "active_tenants",
    )
    total_users = safe_scalar(db.query(func.count(models.User.id)), "users")
    platform_superusers = safe_scalar(
        db.query(func.count(models.User.id)).filter(models.User.is_superuser.is_(True)),
        "platform_superusers",
    )
    tenant_admins = safe_scalar(
        db.query(func.count(models.User.id)).filter(
            models.User.is_amo_admin.is_(True),
            models.User.is_superuser.is_(False),
        ),
        "tenant_admins",
    )
    superusers_with_tenant = safe_scalar(
        db.query(func.count(models.User.id)).filter(
            models.User.is_superuser.is_(True),
            models.User.amo_id.isnot(None),
        ),
        "superusers_with_tenant",
    )

    return {
        "scope": "platform",
        "authenticated_user_id": str(current_user.id),
        "authenticated_user_amo_id": current_user.amo_id,
        "separation": {
            "superusers_with_tenant": superusers_with_tenant,
            "expected_superuser_amo_id": None,
        },
        "counts": {
            "tenants_total": total_tenants,
            "tenants_active": active_tenants,
            "users_total": total_users,
            "platform_superusers": platform_superusers,
            "tenant_admins": tenant_admins,
        },
        "controls": {
            "tenant_billing_gated": True,
            "platform_billing_gated": False,
            "global_superuser_context": "amo_id=None",
        },
    }


# ---------------------------------------------------------------------------
# ADMIN OVERVIEW SUMMARY
# ---------------------------------------------------------------------------


@router.get(
    "/overview-summary",
    response_model=schemas.OverviewSummary,
    summary="Overview summary for admin dashboard (AMO admin or superuser)",
)
def get_overview_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    is_superuser = current_user.is_superuser
    amo_scope = None if is_superuser else current_user.amo_id
    now = datetime.now(timezone.utc)
    errors: List[str] = []

    def scoped(query, model_field):
        if amo_scope is None:
            return query
        return query.filter(model_field == amo_scope)

    def safe_count(query, label: str) -> Optional[int]:
        try:
            return query.scalar() or 0
        except Exception:
            errors.append(label)
            return None

    users_missing_department = safe_count(
        scoped(
            db.query(func.count(models.User.id)).filter(
                models.User.department_id.is_(None)
            ),
            models.User.amo_id,
        ),
        "users_missing_department",
    )
    inactive_users = safe_count(
        scoped(
            db.query(func.count(models.User.id)).filter(
                models.User.is_active.is_(False)
            ),
            models.User.amo_id,
        ),
        "inactive_users",
    )
    inactive_assets = safe_count(
        scoped(
            db.query(func.count(models.AMOAsset.id)).filter(
                models.AMOAsset.is_active.is_(False)
            ),
            models.AMOAsset.amo_id,
        ),
        "inactive_assets",
    )
    inactive_amos = None
    if is_superuser:
        inactive_amos = safe_count(
            db.query(func.count(models.AMO.id)).filter(
                models.AMO.is_active.is_(False)
            ),
            "inactive_amos",
        )

    badges: dict[str, schemas.OverviewBadge] = {}
    issues: List[schemas.OverviewIssue] = []

    def badge(
        key: str,
        count: Optional[int],
        severity: str,
        route: str,
        available: bool = True,
    ) -> None:
        badges[key] = schemas.OverviewBadge(
            count=count,
            severity=severity,
            route=route,
            available=available,
        )

    def issue(
        key: str,
        label: str,
        count: Optional[int],
        severity: str,
        route: str,
    ) -> None:
        if count is None or count == 0:
            return
        issues.append(
            schemas.OverviewIssue(
                key=key,
                label=label,
                count=count,
                severity=severity,
                route=route,
            )
        )

    users_attention = safe_count(
        scoped(
            db.query(func.count(func.distinct(models.User.id))).filter(
                or_(
                    models.User.department_id.is_(None),
                    models.User.is_active.is_(False),
                )
            ),
            models.User.amo_id,
        ),
        "users_attention",
    )
    users_available = users_attention is not None
    badge(
        "users",
        users_attention,
        "warning" if (users_attention or 0) > 0 else "info",
        "/admin/users?filter=attention",
        available=users_available,
    )
    badge(
        "assets",
        inactive_assets,
        "warning" if (inactive_assets or 0) > 0 else "info",
        "/admin/amo-assets?filter=inactive",
        available=inactive_assets is not None,
    )
    if is_superuser:
        badge(
            "amos",
            inactive_amos,
            "warning" if (inactive_amos or 0) > 0 else "info",
            "/admin/amos?filter=inactive",
            available=inactive_amos is not None,
        )

    badge(
        "billing",
        None,
        "info",
        "/admin/billing?filter=issues",
        available=False,
    )

    issue(
        "users_missing_department",
        "Users missing department",
        users_missing_department,
        "warning",
        "/admin/users?filter=missing_department",
    )
    issue(
        "inactive_users",
        "Inactive users",
        inactive_users,
        "warning",
        "/admin/users?filter=inactive",
    )
    if is_superuser:
        issue(
            "inactive_amos",
            "Inactive AMOs",
            inactive_amos,
            "warning",
            "/admin/amos?filter=inactive",
        )
    issue(
        "inactive_assets",
        "Inactive assets",
        inactive_assets,
        "warning",
        "/admin/amo-assets?filter=inactive",
    )

    recent_activity: List[schemas.OverviewActivity] = []
    recent_activity_available = True
    try:
        query = db.query(audit_models.AuditEvent)
        if amo_scope is not None:
            query = query.filter(audit_models.AuditEvent.amo_id == amo_scope)
        events = query.order_by(audit_models.AuditEvent.occurred_at.desc()).limit(5).all()
        for event in events:
            recent_activity.append(
                schemas.OverviewActivity(
                    occurred_at=event.occurred_at,
                    action=event.action,
                    entity_type=event.entity_type,
                    actor_user_id=event.actor_user_id,
                )
            )
    except Exception:
        recent_activity_available = False
        errors.append("recent_activity")

    system_status = "healthy"
    if errors:
        system_status = "degraded"

    return schemas.OverviewSummary(
        system=schemas.OverviewSystemStatus(
            status=system_status,
            last_checked_at=now,
            refresh_paused=False,
            errors=errors,
        ),
        badges=badges,
        issues=issues,
        recent_activity=recent_activity,
        recent_activity_available=recent_activity_available,
    )


# ---------------------------------------------------------------------------
# AUTHORISATIONS (AMO ADMIN / QUALITY MANAGER / SUPERUSER)
# ---------------------------------------------------------------------------


def _require_quality_or_admin(user: models.User) -> models.User:
    """
    Helper gate for authorisation management.

    - SUPERUSER or AMO admin always allowed.
    - QUALITY_MANAGER allowed for their AMO.
    - System/service accounts are blocked even if flags are set.
    """
    if getattr(user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot manage authorisations.",
        )

    if user.is_superuser or user.is_amo_admin:
        return user
    if user.role == models.AccountRole.QUALITY_MANAGER:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Quality Manager or AMO Admin required.",
    )


@router.post(
    "/authorisation-types",
    response_model=schemas.AuthorisationTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create authorisation type for an AMO",
)
def create_authorisation_type(
    payload: schemas.AuthorisationTypeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create an authorisation type.

    - Normal admins / QMs: can only create for their AMO.
    - SUPERUSER: can create for any AMO by setting payload.amo_id.
    """
    _require_quality_or_admin(current_user)

    if not current_user.is_superuser and payload.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create authorisation type for another AMO.",
        )

    dup = (
        db.query(models.AuthorisationType)
        .filter(
            models.AuthorisationType.amo_id == payload.amo_id,
            models.AuthorisationType.code == payload.code,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Authorisation code already exists for this AMO.",
        )

    atype = models.AuthorisationType(
        amo_id=payload.amo_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        maintenance_scope=payload.maintenance_scope,
        regulation_reference=payload.regulation_reference,
        can_issue_crs=payload.can_issue_crs,
        requires_dual_sign=payload.requires_dual_sign,
        requires_valid_licence=payload.requires_valid_licence,
        is_active=True,
    )
    db.add(atype)
    db.commit()
    db.refresh(atype)
    return atype


@router.get(
    "/authorisation-types",
    response_model=List[schemas.AuthorisationTypeRead],
    summary="List authorisation types (current AMO by default; any AMO for superuser)",
)
def list_authorisation_types(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List authorisation types.

    - Normal users / admins: see types only for their AMO.
    - SUPERUSER: can optionally pass `amo_id` to view another AMO; if omitted,
      sees types for their own (ROOT/system) AMO.
    """
    q = db.query(models.AuthorisationType)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.AuthorisationType.amo_id == amo_id)
    else:
        q = q.filter(models.AuthorisationType.amo_id == current_user.amo_id)

    return q.order_by(models.AuthorisationType.code.asc()).all()


@router.post(
    "/user-authorisations",
    response_model=schemas.UserAuthorisationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant authorisation to user",
)
def grant_user_authorisation(
    payload: schemas.UserAuthorisationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Grant a specific authorisation type to a user.

    - SUPERUSER: can grant for any AMO as long as user and type share the same AMO.
    - AMO Admin / QM: can only grant within their AMO.

    Security hardening:
    - granted_by_user_id is ALWAYS set to the authenticated current_user.id
      (client is not allowed to spoof this).
    """
    _require_quality_or_admin(current_user)

    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    atype = (
        db.query(models.AuthorisationType)
        .filter(models.AuthorisationType.id == payload.authorisation_type_id)
        .first()
    )

    if not user or not atype:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User or authorisation type not found.",
        )

    if user.amo_id != atype.amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User and authorisation type must belong to the same AMO.",
        )

    if not current_user.is_superuser and user.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User or authorisation type invalid for this AMO.",
        )

    ua = models.UserAuthorisation(
        user_id=user.id,
        authorisation_type_id=atype.id,
        scope_text=payload.scope_text,
        effective_from=payload.effective_from,
        expires_at=payload.expires_at,
        granted_by_user_id=current_user.id,
    )
    db.add(ua)
    db.commit()
    db.refresh(ua)
    return ua


@router.put(
    "/authorisation-types/{authorisation_type_id}",
    response_model=schemas.AuthorisationTypeRead,
    summary="Update an authorisation type",
)
def update_authorisation_type(
    authorisation_type_id: str,
    payload: schemas.AuthorisationTypeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_quality_or_admin(current_user)
    item = _get_managed_authorisation_type_or_404(
        db, current_user=current_user, authorisation_type_id=authorisation_type_id
    )
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete(
    "/authorisation-types/{authorisation_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an authorisation type and its linked grants",
)
def delete_authorisation_type(
    authorisation_type_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_quality_or_admin(current_user)
    item = _get_managed_authorisation_type_or_404(
        db, current_user=current_user, authorisation_type_id=authorisation_type_id
    )
    db.query(models.UserAuthorisation).filter(
        models.UserAuthorisation.authorisation_type_id == item.id
    ).delete(synchronize_session=False)
    db.delete(item)
    db.commit()
    return


@router.get(
    "/user-authorisations",
    response_model=List[schemas.UserAuthorisationRead],
    summary="List user permissions, optionally scoped to one user",
)
def list_user_authorisations(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_quality_or_admin(current_user)
    q = db.query(models.UserAuthorisation).join(models.User, models.User.id == models.UserAuthorisation.user_id)
    if current_user.is_superuser:
        if user_id:
            q = q.filter(models.UserAuthorisation.user_id == user_id)
    else:
        q = q.filter(models.User.amo_id == current_user.amo_id)
        if user_id:
            q = q.filter(models.UserAuthorisation.user_id == user_id)
    return q.order_by(models.UserAuthorisation.created_at.desc()).all()


@router.put(
    "/user-authorisations/{user_authorisation_id}",
    response_model=schemas.UserAuthorisationRead,
    summary="Update a granted user permission",
)
def update_user_authorisation(
    user_authorisation_id: str,
    payload: schemas.UserAuthorisationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_quality_or_admin(current_user)
    item = _get_managed_user_authorisation_or_404(
        db, current_user=current_user, user_authorisation_id=user_authorisation_id
    )
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete(
    "/user-authorisations/{user_authorisation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a granted user permission",
)
def delete_user_authorisation(
    user_authorisation_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_quality_or_admin(current_user)
    item = _get_managed_user_authorisation_or_404(
        db, current_user=current_user, user_authorisation_id=user_authorisation_id
    )
    db.delete(item)
    db.commit()
    return


# ---------------------------------------------------------------------------
# GROUPS / COHORTS
# ---------------------------------------------------------------------------


@router.get(
    "/groups",
    response_model=List[schemas.UserGroupRead],
    summary="List user groups and cohorts for the active tenant",
)
def list_user_groups(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    _ensure_user_group_schema(db)
    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id
    groups = (
        db.query(models.UserGroup)
        .filter(models.UserGroup.amo_id == target_amo_id)
        .order_by(models.UserGroup.group_type.asc(), models.UserGroup.name.asc())
        .all()
    )
    counts = {
        gid: count
        for gid, count in db.query(
            models.UserGroupMember.group_id, func.count(models.UserGroupMember.id)
        ).filter(
            models.UserGroupMember.group_id.in_([g.id for g in groups]) if groups else False
        ).group_by(models.UserGroupMember.group_id).all()
    } if groups else {}
    return [
        schemas.UserGroupRead(
            id=str(group.id),
            amo_id=str(group.amo_id),
            owner_user_id=group.owner_user_id,
            code=group.code,
            name=group.name,
            description=group.description,
            group_type=getattr(group.group_type, 'value', group.group_type),
            is_system_managed=group.is_system_managed,
            is_active=group.is_active,
            created_at=group.created_at,
            updated_at=group.updated_at,
            member_count=int(counts.get(group.id, 0)),
        )
        for group in groups
    ]


@router.post(
    "/groups",
    response_model=schemas.UserGroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom user group",
)
def create_user_group(
    payload: schemas.UserGroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target_amo_id = payload.amo_id if current_user.is_superuser else current_user.amo_id
    if target_amo_id != payload.amo_id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail='Cannot create groups for another tenant.')
    code = _slugify_group_code(payload.code or payload.name)
    dup = db.query(models.UserGroup).filter(models.UserGroup.amo_id == target_amo_id, models.UserGroup.code == code).first()
    if dup:
        raise HTTPException(status_code=409, detail='A group with this code already exists.')
    group = models.UserGroup(
        amo_id=target_amo_id,
        owner_user_id=current_user.id,
        code=code,
        name=payload.name.strip(),
        description=(payload.description or '').strip() or None,
        group_type=models.UserGroupType(payload.group_type),
        is_system_managed=False,
        is_active=payload.is_active,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return schemas.UserGroupRead(
        id=str(group.id), amo_id=str(group.amo_id), owner_user_id=group.owner_user_id, code=group.code,
        name=group.name, description=group.description, group_type=getattr(group.group_type, 'value', group.group_type),
        is_system_managed=group.is_system_managed, is_active=group.is_active, created_at=group.created_at,
        updated_at=group.updated_at, member_count=0
    )


@router.put(
    "/groups/{group_id}",
    response_model=schemas.UserGroupRead,
    summary="Update a custom user group",
)
def update_user_group(
    group_id: str,
    payload: schemas.UserGroupUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    group = _get_managed_group_or_404(db, current_user=current_user, group_id=group_id)
    if group.is_system_managed:
        raise HTTPException(status_code=400, detail='System-managed groups cannot be edited.')
    data = payload.model_dump(exclude_unset=True)
    if 'code' in data and data['code'] is not None:
        data['code'] = _slugify_group_code(data['code'])
    for field, value in data.items():
        setattr(group, field, value)
    db.add(group)
    db.commit()
    db.refresh(group)
    member_count = db.query(func.count(models.UserGroupMember.id)).filter(models.UserGroupMember.group_id == group.id).scalar() or 0
    return schemas.UserGroupRead(
        id=str(group.id), amo_id=str(group.amo_id), owner_user_id=group.owner_user_id, code=group.code,
        name=group.name, description=group.description, group_type=getattr(group.group_type, 'value', group.group_type),
        is_system_managed=group.is_system_managed, is_active=group.is_active, created_at=group.created_at,
        updated_at=group.updated_at, member_count=int(member_count)
    )


@router.delete(
    "/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom user group",
)
def delete_user_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    group = _get_managed_group_or_404(db, current_user=current_user, group_id=group_id)
    if group.is_system_managed:
        raise HTTPException(status_code=400, detail='System-managed groups cannot be deleted.')
    db.delete(group)
    db.commit()
    return


@router.get(
    "/groups/{group_id}/members",
    response_model=List[schemas.UserGroupMemberRead],
    summary="List the members of a user group",
)
def list_user_group_members(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    group = _get_managed_group_or_404(db, current_user=current_user, group_id=group_id)
    rows = (
        db.query(models.UserGroupMember, models.User)
        .join(models.User, models.User.id == models.UserGroupMember.user_id)
        .filter(models.UserGroupMember.group_id == group.id)
        .order_by(models.User.full_name.asc())
        .all()
    )
    return [
        schemas.UserGroupMemberRead(
            id=str(member.id), group_id=str(group.id), user_id=str(user.id), full_name=user.full_name,
            email=user.email, staff_code=user.staff_code, member_role=member.member_role, added_at=member.added_at
        )
        for member, user in rows
    ]


@router.post(
    "/groups/{group_id}/members",
    response_model=schemas.UserGroupMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user to a group",
)
def add_user_group_member(
    group_id: str,
    payload: schemas.UserGroupMemberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    group = _get_managed_group_or_404(db, current_user=current_user, group_id=group_id)
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=payload.user_id)
    if user.amo_id != group.amo_id:
        raise HTTPException(status_code=400, detail='User and group must belong to the same tenant.')
    existing = db.query(models.UserGroupMember).filter(models.UserGroupMember.group_id == group.id, models.UserGroupMember.user_id == user.id).first()
    if existing:
        return schemas.UserGroupMemberRead(
            id=str(existing.id), group_id=str(group.id), user_id=str(user.id), full_name=user.full_name,
            email=user.email, staff_code=user.staff_code, member_role=existing.member_role, added_at=existing.added_at
        )
    member = models.UserGroupMember(
        group_id=group.id,
        user_id=user.id,
        added_by_user_id=current_user.id,
        member_role=(payload.member_role or 'member').strip() or 'member',
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return schemas.UserGroupMemberRead(
        id=str(member.id), group_id=str(group.id), user_id=str(user.id), full_name=user.full_name,
        email=user.email, staff_code=user.staff_code, member_role=member.member_role, added_at=member.added_at
    )


@router.delete(
    "/groups/{group_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a user from a group",
)
def delete_user_group_member(
    group_id: str,
    membership_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    group = _get_managed_group_or_404(db, current_user=current_user, group_id=group_id)
    member = db.query(models.UserGroupMember).filter(models.UserGroupMember.id == membership_id, models.UserGroupMember.group_id == group.id).first()
    if not member:
        raise HTTPException(status_code=404, detail='Group member not found.')
    db.delete(member)
    db.commit()
    return


# ---------------------------------------------------------------------------
# PLATFORM SETTINGS (SUPERUSER)
# ---------------------------------------------------------------------------


@router.get(
    "/platform-settings",
    response_model=schemas.PlatformSettingsRead,
    summary="Get platform settings (superuser only)",
)
def get_platform_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    return _get_or_create_platform_settings(db)


@router.put(
    "/platform-settings",
    response_model=schemas.PlatformSettingsRead,
    summary="Update platform settings (superuser only)",
)
def update_platform_settings(
    payload: schemas.PlatformSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings


@router.post(
    "/platform-assets/logo",
    response_model=schemas.PlatformSettingsRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload platform logo (superuser only)",
)
def upload_platform_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    _ensure_platform_storage_dir()

    filename = file.filename or "platform-logo"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PLATFORM_LOGO_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logo must be one of: .png, .jpg, .jpeg, .svg",
        )

    settings = _get_or_create_platform_settings(db)
    asset_id = uuid4().hex
    dest_path = _ensure_safe_platform_path(
        PLATFORM_ASSET_UPLOAD_DIR / f"platform_logo_{asset_id}{ext}"
    )

    _save_platform_upload(file=file, dest_path=dest_path)

    if settings.platform_logo_path:
        _delete_platform_asset(settings.platform_logo_path)

    settings.platform_logo_path = str(dest_path)
    settings.platform_logo_filename = filename
    settings.platform_logo_content_type = file.content_type
    settings.platform_logo_uploaded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings


@router.get(
    "/platform-assets/logo",
    response_class=FileResponse,
    summary="Download platform logo (superuser only)",
)
def download_platform_logo(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    if not settings.platform_logo_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No platform logo configured.",
        )

    path = _ensure_safe_platform_path(Path(settings.platform_logo_path))
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform logo asset not found.",
        )

    return FileResponse(
        path=str(path),
        media_type=settings.platform_logo_content_type or "application/octet-stream",
        filename=settings.platform_logo_filename or path.name,
    )




@router.post("/platform/diagnostics/run", summary="Run platform network, database, internet and SMTP diagnostics")
def run_platform_diagnostics_endpoint(payload: schemas.PlatformDiagnosticsRunRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    return _run_platform_diagnostics(
        db,
        settings=settings,
        internet_url=payload.internet_url,
        timeout_seconds=payload.timeout_seconds,
        include_throughput=payload.include_throughput,
        sample_seconds=payload.sample_seconds,
    )


@router.get("/platform/email-settings", summary="Get platform outbound email settings")
def get_platform_email_settings(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_superuser(current_user)
    return _platform_settings_summary(_get_or_create_platform_settings(db))


@router.put("/platform/email-settings", summary="Update platform outbound email settings")
def update_platform_email_settings(payload: schemas.PlatformSettingsUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    allowed = {"email_provider", "email_from_name", "email_from_email", "email_reply_to", "smtp_host", "smtp_port", "smtp_username", "smtp_password_secret", "smtp_use_tls", "smtp_allow_self_signed", "smtp_test_recipient", "support_email", "ops_alert_email"}
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key in allowed:
            setattr(settings, key, value)
    db.commit(); db.refresh(settings)
    return _platform_settings_summary(settings)


@router.post("/platform/email-settings/test", summary="Test platform SMTP settings without persisting an email")
def test_platform_email_settings(payload: schemas.PlatformEmailTestRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    if (settings.email_provider or "none").lower() not in {"smtp", "custom_smtp"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SMTP provider is not configured.")
    if not settings.smtp_host or not settings.smtp_port:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SMTP host and port are required.")
    recipient = (payload.recipient or settings.smtp_test_recipient or settings.ops_alert_email or settings.support_email or settings.email_from_email or "").strip()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a test recipient or configure support/ops/from email.")
    started = time.perf_counter()
    try:
        context = ssl.create_default_context()
        if settings.smtp_allow_self_signed:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        server = smtplib.SMTP(str(settings.smtp_host), int(settings.smtp_port), timeout=8)
        try:
            if settings.smtp_use_tls: server.starttls(context=context)
            if settings.smtp_username and settings.smtp_password_secret: server.login(settings.smtp_username, settings.smtp_password_secret)
            sender = settings.email_from_email or settings.smtp_username or recipient
            message = f"From: {sender}\r\nTo: {recipient}\r\nSubject: {payload.subject}\r\n\r\n{payload.body}\r\n"
            server.sendmail(sender, [recipient], message)
        finally:
            server.quit()
        return {"status": "ok", "recipient": recipient, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"SMTP test failed: {exc}") from exc


@router.get("/platform/support-items", summary="List support or issue items raised by tenants")
def list_platform_support_items(limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_superuser(current_user)
    return {"items": _support_items_summary(db, limit=limit)}


@router.get("/platform/tenants/{amo_id}/module-performance", summary="Inspect module-level record counts and wiring for a tenant")
def get_platform_tenant_module_performance(amo_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_superuser(current_user)
    amo = _get_tenant_or_404(db, amo_id=amo_id)
    return {"tenant": {"id": amo.id, "amo_code": amo.amo_code, "name": amo.name}, "modules": _module_performance_summary(db, amo_id=amo.id)}


# ---------------------------------------------------------------------------
# USER DIRECTORY / WORKSPACE (SAFE, SCHEMA-COMPATIBLE)
# ---------------------------------------------------------------------------


def _manager_roles() -> set[models.AccountRole]:
    return {
        models.AccountRole.SUPERUSER,
        models.AccountRole.AMO_ADMIN,
        models.AccountRole.QUALITY_MANAGER,
        models.AccountRole.SAFETY_MANAGER,
        models.AccountRole.PLANNING_ENGINEER,
        models.AccountRole.PRODUCTION_ENGINEER,
    }


def _presence_map_for_users(db: Session, *, amo_id: str, user_ids: list[str]) -> dict[str, schemas.UserPresenceRead]:
    if not user_ids:
        return {}

    try:
        from amodb.apps.realtime import models as realtime_models

        now = datetime.now(timezone.utc)
        rows = (
            db.query(realtime_models.PresenceState)
            .filter(
                realtime_models.PresenceState.amo_id == amo_id,
                realtime_models.PresenceState.user_id.in_(user_ids),
            )
            .all()
        )
        result: dict[str, schemas.UserPresenceRead] = {}
        for row in rows:
            last_seen = row.last_seen_at
            resolved_state, is_online = _resolve_presence_state(
                raw_state=str(getattr(row.state, "value", row.state) or "offline"),
                last_seen_at=last_seen,
                now=now,
            )
            result[str(row.user_id)] = schemas.UserPresenceRead(
                state=resolved_state,
                is_online=is_online,
                last_seen_at=last_seen,
                source="realtime",
            )
        return result
    except Exception:
        return {}


def _resolve_presence_for_user(
    *,
    user: models.User,
    presence_map: dict[str, schemas.UserPresenceRead],
) -> schemas.UserPresenceRead:
    realtime_presence = presence_map.get(str(user.id))
    if realtime_presence is not None:
        return realtime_presence
    return schemas.UserPresenceRead(
        state="offline",
        is_online=False,
        last_seen_at=user.last_login_at,
        source="login",
    )


@router.get(
    "/user-directory",
    response_model=schemas.AdminUserDirectoryRead,
    summary="Dense user directory with presence and HR metrics",
)
def get_user_directory_admin(
    amo_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id
    if not target_amo_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AMO context is required.")

    q = (
        db.query(models.User)
        .filter(models.User.amo_id == target_amo_id)
        .order_by(models.User.full_name.asc())
    )
    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.User.full_name.ilike(s),
                models.User.email.ilike(s),
                models.User.staff_code.ilike(s),
                models.User.position_title.ilike(s),
            )
        )

    users = q.offset(skip).limit(min(max(limit, 1), 250)).all()
    all_users = db.query(models.User).filter(models.User.amo_id == target_amo_id).all()

    department_ids = sorted({u.department_id for u in all_users if u.department_id})
    departments = {}
    if department_ids:
        departments = {
            str(d.id): d.name
            for d in db.query(models.Department).filter(models.Department.id.in_(department_ids)).all()
        }

    presence_map = _presence_map_for_users(db, amo_id=target_amo_id, user_ids=[str(u.id) for u in all_users])
    availability_map = _latest_availability_map_for_users(db, amo_id=target_amo_id, user_ids=[str(u.id) for u in all_users])

    items = []
    for user in users:
        presence = _resolve_presence_for_user(user=user, presence_map=presence_map)
        availability_status = _current_availability_status(availability_map.get(str(user.id)))
        presence_display = _presence_display_for_user(user=user, presence=presence, availability_status=availability_status)
        items.append(
            schemas.AdminUserDirectoryItem(
                id=str(user.id),
                amo_id=str(user.amo_id),
                department_id=user.department_id,
                department_name=departments.get(str(user.department_id)) if user.department_id else None,
                staff_code=user.staff_code,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                full_name=user.full_name,
                role=user.role,
                position_title=user.position_title,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                is_amo_admin=user.is_amo_admin,
                display_title=_display_title_for_user(user),
                availability_status=availability_status,
                last_login_at=user.last_login_at,
                created_at=user.created_at,
                updated_at=user.updated_at,
                presence=presence,
                presence_display=presence_display,
            )
        )

    all_presence = [_resolve_presence_for_user(user=u, presence_map=presence_map) for u in all_users]
    recent_cutoff = datetime.now(timezone.utc) - timedelta(minutes=RECENTLY_ACTIVE_WINDOW_MINUTES)
    all_online = sum(1 for presence in all_presence if presence.is_online)
    all_away = sum(1 for presence in all_presence if presence.state == "away")
    on_leave = sum(1 for u in all_users if _current_availability_status(availability_map.get(str(u.id))) == "ON_LEAVE")
    all_recently_active = sum(
        1
        for presence in all_presence
        if bool(presence.last_seen_at and presence.last_seen_at >= recent_cutoff)
    )
    metrics = schemas.AdminUserDirectoryMetrics(
        total_users=len(all_users),
        active_users=sum(1 for u in all_users if u.is_active),
        inactive_users=sum(1 for u in all_users if not u.is_active),
        online_users=all_online,
        away_users=all_away,
        on_leave_users=on_leave,
        recently_active_users=all_recently_active,
        departmentless_users=sum(1 for u in all_users if not u.department_id),
        managers=sum(1 for u in all_users if u.role in _manager_roles()),
    )
    return schemas.AdminUserDirectoryRead(items=items, metrics=metrics)


@router.get(
    "/users/{user_id}/workspace",
    response_model=schemas.AdminUserWorkspaceRead,
    summary="User workspace with profile tabs, tasks, permissions, activity, and login record",
)
def get_user_workspace_admin(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    _ensure_user_group_schema(db)
    from amodb.apps.tasks import models as task_models
    from amodb.apps.quality import models as quality_models

    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    target_amo_id = user.amo_id

    departments: dict[str, str] = {}
    if user.department_id:
        dept = db.query(models.Department).filter(models.Department.id == user.department_id).first()
        if dept:
            departments[str(dept.id)] = dept.name

    presence_map = _presence_map_for_users(db, amo_id=target_amo_id, user_ids=[str(user.id)])
    availability_map = _latest_availability_map_for_users(db, amo_id=target_amo_id, user_ids=[str(user.id)])
    current_availability = availability_map.get(str(user.id))
    availability_status = _current_availability_status(current_availability)
    presence = _resolve_presence_for_user(user=user, presence_map=presence_map)
    presence_display = _presence_display_for_user(
        user=user,
        presence=presence,
        availability_status=availability_status,
    )

    tasks = (
        db.query(task_models.Task)
        .filter(task_models.Task.amo_id == target_amo_id, task_models.Task.owner_user_id == str(user.id))
        .order_by(task_models.Task.updated_at.desc())
        .limit(100)
        .all()
    )
    task_items = [
        schemas.UserTaskSummaryRead(
            id=str(task.id),
            title=task.title,
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            priority=task.priority,
            due_at=task.due_at,
            entity_type=task.entity_type,
            entity_id=task.entity_id,
            updated_at=task.updated_at,
        )
        for task in tasks
    ]

    permissions = [
        schemas.UserPermissionSummaryRead(
            id=str(item.id),
            code=item.authorisation_type.code,
            label=item.authorisation_type.name,
            maintenance_scope=(item.authorisation_type.maintenance_scope.value if getattr(item.authorisation_type, "maintenance_scope", None) is not None else None),
            scope_text=item.scope_text,
            effective_from=item.effective_from,
            expires_at=item.expires_at,
            is_currently_valid=item.is_currently_valid(),
        )
        for item in sorted(user.authorisations, key=lambda row: (row.expires_at is None, row.expires_at or date.max), reverse=True)
    ]

    activity_rows = (
        db.query(audit_models.AuditEvent)
        .filter(audit_models.AuditEvent.amo_id == target_amo_id)
        .filter(
            or_(
                audit_models.AuditEvent.actor_user_id == str(user.id),
                audit_models.AuditEvent.entity_id == str(user.id),
            )
        )
        .order_by(audit_models.AuditEvent.occurred_at.desc())
        .limit(100)
        .all()
    )
    activity = [
        schemas.UserActivitySummaryRead(
            id=str(row.id),
            occurred_at=row.occurred_at,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
        )
        for row in activity_rows
    ]

    profile_row = _get_personnel_profile_for_user(db, user=user)
    profile = None
    if profile_row is not None:
        profile = schemas.PersonnelProfileSummaryRead(
            id=str(profile_row.id),
            person_id=profile_row.person_id,
            employment_status=profile_row.employment_status,
            status=profile_row.status,
            hire_date=profile_row.hire_date,
            department=profile_row.department,
            position_title=profile_row.position_title,
        )

    availability_rows = (
        db.query(quality_models.UserAvailability)
        .filter(quality_models.UserAvailability.amo_id == target_amo_id, quality_models.UserAvailability.user_id == user.id)
        .order_by(quality_models.UserAvailability.updated_at.desc())
        .limit(100)
        .all()
    )
    availability = [
        schemas.UserAvailabilitySummaryRead(
            id=str(row.id),
            status=getattr(row.status, 'value', row.status),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            note=row.note,
            updated_at=row.updated_at,
        )
        for row in availability_rows
    ]

    membership_rows = (
        db.query(models.UserGroupMember, models.UserGroup)
        .join(models.UserGroup, models.UserGroup.id == models.UserGroupMember.group_id)
        .filter(models.UserGroupMember.user_id == user.id)
        .order_by(models.UserGroup.name.asc())
        .all()
    )
    group_memberships: list[schemas.UserGroupRead] = []
    groups = [
        schemas.UserGroupChipRead(kind="role", label="Role", value=str(user.role.value if hasattr(user.role, 'value') else user.role)),
    ]
    if user.position_title:
        groups.append(schemas.UserGroupChipRead(kind="post_holder", label="Post holder", value=user.position_title))
    if user.department_id and departments.get(str(user.department_id)):
        groups.append(schemas.UserGroupChipRead(kind="department", label="Department", value=departments[str(user.department_id)]))
    if user.role in _manager_roles():
        groups.append(schemas.UserGroupChipRead(kind="managerial", label="Managerial cohort", value="Manager"))

    member_counts = {
        str(group_id): int(count)
        for group_id, count in db.query(models.UserGroupMember.group_id, func.count(models.UserGroupMember.id))
        .filter(models.UserGroupMember.group_id.in_([group.id for _, group in membership_rows]) if membership_rows else False)
        .group_by(models.UserGroupMember.group_id)
        .all()
    } if membership_rows else {}

    for member, group in membership_rows:
        group_memberships.append(
            schemas.UserGroupRead(
                id=str(group.id),
                amo_id=str(group.amo_id),
                owner_user_id=group.owner_user_id,
                code=group.code,
                name=group.name,
                description=group.description,
                group_type=getattr(group.group_type, 'value', group.group_type),
                is_system_managed=group.is_system_managed,
                is_active=group.is_active,
                created_at=group.created_at,
                updated_at=group.updated_at,
                member_count=member_counts.get(str(group.id), 0),
            )
        )
        groups.append(
            schemas.UserGroupChipRead(
                kind="custom_group",
                label=group.name,
                value=(member.member_role or 'member').title(),
            )
        )

    metrics = [
        schemas.UserWorkspaceMetricRead(key="open_tasks", label="Open tasks", value=sum(1 for t in task_items if t.status in {"OPEN", "IN_PROGRESS"})),
        schemas.UserWorkspaceMetricRead(key="permissions", label="Permissions", value=len(permissions)),
        schemas.UserWorkspaceMetricRead(key="activity_entries", label="Activity entries", value=len(activity)),
        schemas.UserWorkspaceMetricRead(key="groups", label="Groups", value=len(group_memberships)),
        schemas.UserWorkspaceMetricRead(key="availability_entries", label="Availability", value=len(availability)),
    ]

    return schemas.AdminUserWorkspaceRead(
        user=schemas.UserRead.model_validate(user),
        department_name=departments.get(str(user.department_id)) if user.department_id else None,
        display_title=_display_title_for_user(user),
        presence=presence,
        presence_display=presence_display,
        metrics=metrics,
        tasks=task_items,
        permissions=permissions,
        activity_log=activity,
        login_record=schemas.UserLoginRecordRead(
            last_login_at=user.last_login_at,
            last_login_ip=user.last_login_ip,
            last_login_user_agent=user.last_login_user_agent,
            must_change_password=user.must_change_password,
            password_changed_at=user.password_changed_at,
            token_revoked_at=user.token_revoked_at,
        ),
        groups=groups,
        profile=profile,
        availability=availability,
        group_memberships=group_memberships,
    )
