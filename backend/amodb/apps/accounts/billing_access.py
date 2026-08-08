from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, noload

from . import models, schemas


def _access_license(db: Session, *, amo_id: str, now: datetime) -> models.TenantLicense | None:
    priority = case(
        (models.TenantLicense.status.in_([models.LicenseStatus.ACTIVE, models.LicenseStatus.TRIALING]), 0),
        (
            (models.TenantLicense.status == models.LicenseStatus.EXPIRED)
            & models.TenantLicense.trial_grace_expires_at.isnot(None)
            & (models.TenantLicense.trial_grace_expires_at >= now),
            1,
        ),
        else_=2,
    )
    recency = func.coalesce(
        models.TenantLicense.current_period_end,
        models.TenantLicense.trial_grace_expires_at,
        models.TenantLicense.trial_ends_at,
        models.TenantLicense.updated_at,
        models.TenantLicense.created_at,
    )
    return (
        db.query(models.TenantLicense)
        .options(
            noload(models.TenantLicense.amo),
            noload(models.TenantLicense.catalog_sku),
            noload(models.TenantLicense.entitlements),
            noload(models.TenantLicense.ledger_entries),
            noload(models.TenantLicense.usage_meters),
        )
        .filter(models.TenantLicense.amo_id == amo_id)
        .order_by(priority.asc(), recency.desc(), models.TenantLicense.id.desc())
        .first()
    )


def _project_subscription(
    license: models.TenantLicense,
    *,
    now: datetime,
    has_overdue_invoice: bool,
) -> schemas.SubscriptionRead:
    status = license.status
    read_only = bool(license.is_read_only)
    grace = license.trial_grace_expires_at
    current_period_end = license.current_period_end

    if status == models.LicenseStatus.TRIALING and license.trial_ends_at and license.trial_ends_at <= now:
        status = models.LicenseStatus.EXPIRED
        grace = grace or license.trial_ends_at + timedelta(days=7)
        current_period_end = license.trial_ends_at
        read_only = now >= grace
    elif status == models.LicenseStatus.EXPIRED:
        if license.trial_ends_at:
            grace = grace or license.trial_ends_at + timedelta(days=7)
            current_period_end = current_period_end or license.trial_ends_at
            read_only = now >= grace
        else:
            read_only = True
    elif status == models.LicenseStatus.CANCELLED:
        read_only = True
    elif current_period_end is not None:
        period_end = current_period_end if current_period_end.tzinfo else current_period_end.replace(tzinfo=timezone.utc)
        if period_end <= now:
            read_only = True
    if has_overdue_invoice:
        read_only = True

    return schemas.SubscriptionRead(
        id=license.id,
        amo_id=license.amo_id,
        sku_id=license.sku_id,
        term=license.term,
        status=status,
        trial_started_at=license.trial_started_at,
        trial_ends_at=license.trial_ends_at,
        trial_grace_expires_at=grace,
        is_read_only=read_only,
        current_period_start=license.current_period_start,
        current_period_end=current_period_end,
        canceled_at=license.canceled_at,
    )


def _current_module_count(db: Session, *, amo_id: str, now: datetime) -> int:
    return int(
        db.query(func.count(models.ModuleSubscription.id))
        .filter(
            models.ModuleSubscription.amo_id == amo_id,
            models.ModuleSubscription.status.in_([
                models.ModuleSubscriptionStatus.ENABLED,
                models.ModuleSubscriptionStatus.TRIAL,
            ]),
            or_(models.ModuleSubscription.effective_from.is_(None), models.ModuleSubscription.effective_from <= now),
            or_(models.ModuleSubscription.effective_to.is_(None), models.ModuleSubscription.effective_to >= now),
        )
        .scalar()
        or 0
    )


def _account_overdue_row(db: Session, *, amo_id: str, now: datetime):
    description = models.BillingInvoice.description
    module_scoped = or_(
        description.contains('"lock_scope":"MODULE"'),
        description.contains('"source":"MODULE_RENEWAL"'),
    )
    return (
        db.query(
            models.BillingInvoice.id.label("invoice_id"),
            func.count(models.BillingInvoice.id).over().label("overdue_count"),
        )
        .filter(
            models.BillingInvoice.amo_id == amo_id,
            models.BillingInvoice.status == models.InvoiceStatus.PENDING,
            models.BillingInvoice.due_at.isnot(None),
            models.BillingInvoice.due_at <= now,
            or_(description.is_(None), ~module_scoped),
        )
        .order_by(models.BillingInvoice.due_at.asc(), models.BillingInvoice.id.asc())
        .first()
    )


def get_billing_access_status(
    db: Session,
    *,
    amo_id: str,
    as_of: datetime | None = None,
) -> schemas.BillingAccessStatusRead:
    now = as_of or datetime.now(timezone.utc)
    license = _access_license(db, amo_id=amo_id, now=now)
    active_module_count = _current_module_count(db, amo_id=amo_id, now=now)
    overdue = _account_overdue_row(db, amo_id=amo_id, now=now)
    actionable_invoice_id = str(overdue.invoice_id) if overdue is not None else None
    overdue_count = int(overdue.overdue_count or 0) if overdue is not None else 0

    if overdue is not None:
        subscription = _project_subscription(license, now=now, has_overdue_invoice=True) if license is not None else None
        return schemas.BillingAccessStatusRead(
            subscription=subscription,
            access_state="PAYMENT_OVERDUE",
            has_access=False,
            redirect_to_billing=True,
            lock_reason="Account billing is overdue. Please settle the outstanding account invoice to continue.",
            payment_method_count=0,
            overdue_invoice_count=overdue_count,
            actionable_invoice_id=actionable_invoice_id,
        )

    projected = _project_subscription(license, now=now, has_overdue_invoice=False) if license is not None else None
    if projected is not None and not projected.is_read_only:
        state = "TRIALING" if projected.status == models.LicenseStatus.TRIALING else "ACTIVE"
        if projected.status == models.LicenseStatus.EXPIRED:
            state = "TRIAL_GRACE"
        return schemas.BillingAccessStatusRead(
            subscription=projected,
            access_state=state,
            has_access=True,
            redirect_to_billing=False,
            lock_reason=None,
            payment_method_count=0,
            overdue_invoice_count=0,
            actionable_invoice_id=None,
        )

    if active_module_count > 0:
        return schemas.BillingAccessStatusRead(
            subscription=None,
            access_state="MODULE_SUBSCRIBED",
            has_access=True,
            redirect_to_billing=False,
            lock_reason=None,
            payment_method_count=0,
            overdue_invoice_count=0,
            actionable_invoice_id=None,
        )

    if projected is not None:
        state = "EXPIRED" if projected.status == models.LicenseStatus.EXPIRED else "LOCKED"
        if projected.status == models.LicenseStatus.CANCELLED:
            state = "CANCELLED"
        return schemas.BillingAccessStatusRead(
            subscription=projected,
            access_state=state,
            has_access=False,
            redirect_to_billing=True,
            lock_reason="This AMO has no current paid account or module contract. Go to Billing to renew access.",
            payment_method_count=0,
            overdue_invoice_count=0,
            actionable_invoice_id=None,
        )

    return schemas.BillingAccessStatusRead(
        subscription=None,
        access_state="NO_SUBSCRIPTION",
        has_access=False,
        redirect_to_billing=True,
        lock_reason="This AMO has no current paid subscription. An authorised billing user can select and activate modules in Billing.",
        payment_method_count=0,
        overdue_invoice_count=0,
        actionable_invoice_id=None,
    )


def resolve_entitlements(
    db: Session,
    *,
    amo_id: str,
    as_of: datetime | None = None,
) -> dict[str, schemas.ResolvedEntitlement]:
    now = as_of or datetime.now(timezone.utc)
    license = models.TenantLicense
    entitlement = models.LicenseEntitlement
    active_period = and_(
        license.status.in_([models.LicenseStatus.ACTIVE, models.LicenseStatus.TRIALING]),
        or_(license.current_period_start.is_(None), license.current_period_start <= now),
        or_(license.current_period_end.is_(None), license.current_period_end >= now),
        or_(license.status != models.LicenseStatus.TRIALING, license.trial_ends_at.is_(None), license.trial_ends_at >= now),
    )
    grace_period = and_(
        license.status == models.LicenseStatus.EXPIRED,
        license.trial_grace_expires_at.isnot(None),
        license.trial_grace_expires_at >= now,
        license.is_read_only.is_(False),
    )
    rows = (
        db.query(
            entitlement.key,
            entitlement.limit,
            entitlement.is_unlimited,
            license.id.label("license_id"),
            license.term,
            license.status,
        )
        .join(license, entitlement.license_id == license.id)
        .filter(license.amo_id == amo_id, or_(active_period, grace_period))
        .all()
    )
    resolved: dict[str, schemas.ResolvedEntitlement] = {}
    for row in rows:
        key = str(row.key)
        existing = resolved.get(key)
        if bool(row.is_unlimited):
            resolved[key] = schemas.ResolvedEntitlement(
                key=key,
                is_unlimited=True,
                limit=None,
                source_license_id=row.license_id,
                license_term=row.term,
                license_status=row.status,
            )
            continue
        candidate_limit = int(row.limit or 0)
        if existing is None or (not existing.is_unlimited and int(existing.limit or 0) < candidate_limit):
            resolved[key] = schemas.ResolvedEntitlement(
                key=key,
                is_unlimited=False,
                limit=candidate_limit,
                source_license_id=row.license_id,
                license_term=row.term,
                license_status=row.status,
            )
    return resolved
