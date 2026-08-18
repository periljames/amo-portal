from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import calendar_subscriptions, common, controlled_exports, models, roster_control, services

router = APIRouter(prefix="/rostering", tags=["rostering-control"])


class LegacyAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=64)
    context_label: Optional[str] = Field(default=None, max_length=128)
    aircraft_registration: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=4000)


class LegacyAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alias: str
    shift_template_id: str
    context_label: Optional[str] = None
    aircraft_registration: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class ControlledDocumentSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    form_number: str
    revision_label: Optional[str] = None
    revision_date: Optional[date] = None
    footer_note: Optional[str] = None
    prepared_by_label: str
    approved_by_label: str
    page_size: str


class ControlledDocumentSettingsUpdate(BaseModel):
    form_number: Optional[str] = Field(default=None, min_length=1, max_length=64)
    revision_label: Optional[str] = Field(default=None, max_length=64)
    revision_date: Optional[date] = None
    footer_note: Optional[str] = Field(default=None, max_length=4000)
    prepared_by_label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    approved_by_label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    page_size: Optional[str] = Field(default=None, pattern=r"^(A3|A4)$")


class CalendarSubscriptionStatus(BaseModel):
    active: bool
    created_at: Optional[datetime] = None
    rotated_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    refresh_interval_minutes: int = 60
    includes: list[str]


class CalendarSubscriptionLink(CalendarSubscriptionStatus):
    https_url: str
    webcal_url: str
    feed_path: str


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _require(db: Session, user: account_models.User, permission: workforce_permissions.PermissionCode) -> None:
    workforce_permissions.require_permission(db, user=user, permission=permission)


def _version_or_404(db: Session, *, amo_id: str, version_id: str) -> models.RosterVersion:
    row = services.get_version(db, amo_id=amo_id, version_id=version_id)
    if not row:
        raise HTTPException(status_code=404, detail="Roster version not found")
    return row


def _subscription_payload(row) -> CalendarSubscriptionStatus:
    return CalendarSubscriptionStatus(
        active=bool(row and row.revoked_at is None),
        created_at=getattr(row, "created_at", None),
        rotated_at=getattr(row, "rotated_at", None),
        revoked_at=getattr(row, "revoked_at", None),
        last_used_at=getattr(row, "last_used_at", None),
        includes=["PUBLISHED_DUTY", "TRAINING", "QMS_AUDITS", "MAINTENANCE_TASKS", "AIRCRAFT_ALLOCATIONS"],
    )


def _subscription_link(request: Request, row, raw_token: str) -> CalendarSubscriptionLink:
    feed_path = f"/rostering/calendar/feed/{raw_token}.ics"
    https_url = str(request.base_url).rstrip("/") + feed_path
    webcal_url = "webcal://" + https_url.split("://", 1)[-1]
    return CalendarSubscriptionLink(
        **_subscription_payload(row).model_dump(),
        https_url=https_url,
        webcal_url=webcal_url,
        feed_path=feed_path,
    )


@router.get("/shift-templates/aliases", response_model=list[LegacyAliasRead])
def list_legacy_aliases(
    template_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise HTTPException(status_code=403, detail="Roster access denied")
    return roster_control.list_aliases(db, amo_id=_amo(current_user), template_id=template_id)


@router.post("/shift-templates/{template_id}/aliases", response_model=LegacyAliasRead, status_code=status.HTTP_201_CREATED)
def create_legacy_alias(
    template_id: str,
    payload: LegacyAliasCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES)
    try:
        row = roster_control.create_alias(
            db,
            amo_id=_amo(current_user),
            template_id=template_id,
            alias=payload.alias,
            actor_user_id=current_user.id,
            context_label=payload.context_label,
            aircraft_registration=payload.aircraft_registration,
            notes=payload.notes,
        )
        db.commit()
        db.refresh(row)
        return row
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/shift-templates/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_legacy_alias(
    alias_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES)
    try:
        roster_control.delete_alias(db, amo_id=_amo(current_user), alias_id=alias_id, actor_user_id=current_user.id)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/controlled-document/settings", response_model=ControlledDocumentSettingsRead)
def get_controlled_document_settings(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_ALL)
    row = roster_control.get_or_create_settings(db, amo_id=_amo(current_user), actor_user_id=current_user.id)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/controlled-document/settings", response_model=ControlledDocumentSettingsRead)
def patch_controlled_document_settings(
    payload: ControlledDocumentSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_MANAGE_CONTROLLED_OUTPUT)
    row = roster_control.get_or_create_settings(db, amo_id=_amo(current_user), actor_user_id=current_user.id)
    try:
        roster_control.update_settings(
            db,
            row=row,
            actor_user_id=current_user.id,
            values=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        db.refresh(row)
        return row
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/versions/{version_id}/controlled-roster.pdf")
def controlled_roster_pdf(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_ALL)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id)
    snapshot = roster_control.snapshot_for_export(db, version=version, actor_user_id=current_user.id)
    payload = controlled_exports.controlled_roster_pdf(snapshot)
    db.commit()
    filename = f"controlled-roster-{version.period.period_code}-v{version.version_no}.pdf"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/versions/{version_id}/controlled-roster.xlsx")
def controlled_roster_xlsx(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_ALL)
    version = _version_or_404(db, amo_id=_amo(current_user), version_id=version_id)
    snapshot = roster_control.snapshot_for_export(db, version=version, actor_user_id=current_user.id)
    payload = controlled_exports.controlled_roster_xlsx(snapshot)
    db.commit()
    filename = f"controlled-roster-{version.period.period_code}-v{version.version_no}.xlsx"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/calendar/subscription", response_model=CalendarSubscriptionLink)
def personal_calendar_subscription(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return the owner's stable subscription URL without rotating it.

    The bearer token is random, stored encrypted at rest, and looked up by hash.
    This keeps the existing self-service calendar UI compatible while still
    allowing explicit rotate/revoke operations.
    """
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    row, raw_token = calendar_subscriptions.get_or_issue_active_subscription(
        db,
        amo_id=_amo(current_user),
        user_id=current_user.id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _subscription_link(request, row, raw_token)


@router.post("/calendar/subscription", response_model=CalendarSubscriptionLink, status_code=status.HTTP_201_CREATED)
def create_personal_calendar_subscription(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    row, raw_token = calendar_subscriptions.get_or_issue_active_subscription(
        db,
        amo_id=_amo(current_user),
        user_id=current_user.id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _subscription_link(request, row, raw_token)


@router.post("/calendar/subscription/rotate", response_model=CalendarSubscriptionLink)
def rotate_personal_calendar_subscription(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    row, raw_token = calendar_subscriptions.issue_calendar_subscription(
        db,
        amo_id=_amo(current_user),
        user_id=current_user.id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _subscription_link(request, row, raw_token)


@router.delete("/calendar/subscription", status_code=status.HTTP_204_NO_CONTENT)
def revoke_personal_calendar_subscription(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require(db, current_user, workforce_permissions.PermissionCode.ROSTER_VIEW_OWN)
    calendar_subscriptions.revoke_calendar_subscription(
        db,
        amo_id=_amo(current_user),
        user_id=current_user.id,
        actor_user_id=current_user.id,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/calendar/feed/{token}.ics", name="controlled_personal_roster_calendar_feed")
def personal_calendar_feed(
    token: str,
    db: Session = Depends(get_db),
):
    row = calendar_subscriptions.resolve_calendar_subscription(db, raw_token=token)
    if not row:
        raise HTTPException(status_code=404, detail="Calendar subscription is invalid or revoked")
    try:
        content = roster_control.stable_personal_calendar(db, amo_id=row.amo_id, user_id=row.user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return PlainTextResponse(
        content,
        media_type="text/calendar",
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": "inline; filename=amo-portal-calendar.ics",
        },
    )
