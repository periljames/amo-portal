from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, noload

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.accounts import services as account_services


_INSTALLED = False


def _term_delta(term: account_models.BillingTerm) -> timedelta:
    return {
        account_models.BillingTerm.MONTHLY: timedelta(days=30),
        account_models.BillingTerm.BI_ANNUAL: timedelta(days=182),
        account_models.BillingTerm.ANNUAL: timedelta(days=365),
    }.get(term, timedelta(days=30))


def _access_license(
    db: Session,
    *,
    amo_id: str,
    now: datetime,
) -> account_models.TenantLicense | None:
    """Resolve the best billing record in one bounded query."""
    active_priority = case(
        (
            account_models.TenantLicense.status.in_(
                [account_models.LicenseStatus.ACTIVE, account_models.LicenseStatus.TRIALING]
            ),
            0,
        ),
        (
            (
                (account_models.TenantLicense.status == account_models.LicenseStatus.EXPIRED)
                & account_models.TenantLicense.trial_grace_expires_at.isnot(None)
                & (account_models.TenantLicense.trial_grace_expires_at >= now)
            ),
            1,
        ),
        else_=2,
    )
    recency = func.coalesce(
        account_models.TenantLicense.current_period_end,
        account_models.TenantLicense.trial_grace_expires_at,
        account_models.TenantLicense.trial_ends_at,
        account_models.TenantLicense.updated_at,
        account_models.TenantLicense.created_at,
    )
    return (
        db.query(account_models.TenantLicense)
        .options(
            noload(account_models.TenantLicense.amo),
            noload(account_models.TenantLicense.catalog_sku),
            noload(account_models.TenantLicense.entitlements),
            noload(account_models.TenantLicense.ledger_entries),
            noload(account_models.TenantLicense.usage_meters),
        )
        .filter(account_models.TenantLicense.amo_id == amo_id)
        .order_by(active_priority.asc(), recency.desc(), account_models.TenantLicense.id.desc())
        .first()
    )


def _project_subscription(
    license: account_models.TenantLicense,
    *,
    now: datetime,
    has_payment_method: bool,
    has_overdue_invoice: bool,
) -> account_schemas.SubscriptionRead:
    status = license.status
    read_only = bool(license.is_read_only)
    trial_grace_expires_at = license.trial_grace_expires_at
    current_period_end = license.current_period_end

    if (
        status == account_models.LicenseStatus.TRIALING
        and license.trial_ends_at
        and license.trial_ends_at <= now
    ):
        if has_payment_method:
            status = account_models.LicenseStatus.ACTIVE
            read_only = False
            if current_period_end is None or current_period_end <= license.trial_ends_at:
                current_period_end = license.trial_ends_at + _term_delta(license.term)
        else:
            status = account_models.LicenseStatus.EXPIRED
            if trial_grace_expires_at is None:
                trial_grace_expires_at = license.trial_ends_at + timedelta(days=7)
            current_period_end = license.trial_ends_at
            read_only = now >= trial_grace_expires_at
    elif status == account_models.LicenseStatus.EXPIRED and license.trial_ends_at:
        if trial_grace_expires_at is None:
            trial_grace_expires_at = license.trial_ends_at + timedelta(days=7)
        read_only = now >= trial_grace_expires_at
        current_period_end = current_period_end or license.trial_ends_at
    elif status == account_models.LicenseStatus.CANCELLED:
        read_only = True
    elif has_overdue_invoice:
        read_only = True

    return account_schemas.SubscriptionRead(
        id=license.id,
        amo_id=license.amo_id,
        sku_id=license.sku_id,
        term=license.term,
        status=status,
        trial_started_at=license.trial_started_at,
        trial_ends_at=license.trial_ends_at,
        trial_grace_expires_at=trial_grace_expires_at,
        is_read_only=read_only,
        current_period_start=license.current_period_start,
        current_period_end=current_period_end,
        canceled_at=license.canceled_at,
    )


def optimized_billing_access_status(
    db: Session,
    *,
    amo_id: str,
    as_of: datetime | None = None,
) -> account_schemas.BillingAccessStatusRead:
    """Resolve billing access in three bounded queries without eager-load spillover."""
    now = as_of or datetime.now(timezone.utc)

    # Query 1: only the single license record required for access projection.
    license = _access_license(db, amo_id=amo_id, now=now)

    # Query 2: a scalar payment-method count. The existing amo_id index serves it.
    payment_method_count = int(
        db.query(func.count(account_models.PaymentMethod.id))
        .filter(account_models.PaymentMethod.amo_id == amo_id)
        .scalar()
        or 0
    )

    # Query 3: the earliest overdue invoice and total overdue count in one query.
    overdue = (
        db.query(
            account_models.BillingInvoice.id.label("invoice_id"),
            func.count(account_models.BillingInvoice.id).over().label("overdue_count"),
        )
        .filter(
            account_models.BillingInvoice.amo_id == amo_id,
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
            account_models.BillingInvoice.due_at.isnot(None),
            account_models.BillingInvoice.due_at <= now,
        )
        .order_by(account_models.BillingInvoice.due_at.asc(), account_models.BillingInvoice.id.asc())
        .first()
    )
    actionable_invoice_id = str(overdue.invoice_id) if overdue is not None else None
    overdue_invoice_count = int(overdue.overdue_count or 0) if overdue is not None else 0

    if license is None:
        return account_schemas.BillingAccessStatusRead(
            subscription=None,
            access_state="NO_SUBSCRIPTION",
            has_access=False,
            redirect_to_billing=True,
            lock_reason="No active or historical subscription exists for this AMO.",
            payment_method_count=payment_method_count,
            overdue_invoice_count=overdue_invoice_count,
            actionable_invoice_id=actionable_invoice_id,
        )

    subscription = _project_subscription(
        license,
        now=now,
        has_payment_method=payment_method_count > 0,
        has_overdue_invoice=overdue is not None,
    )

    if overdue is not None:
        return account_schemas.BillingAccessStatusRead(
            subscription=subscription,
            access_state="PAYMENT_OVERDUE",
            has_access=False,
            redirect_to_billing=True,
            lock_reason="Billing is overdue. Please settle outstanding invoices to continue.",
            payment_method_count=payment_method_count,
            overdue_invoice_count=overdue_invoice_count,
            actionable_invoice_id=actionable_invoice_id,
        )

    if subscription.is_read_only:
        access_state = "LOCKED"
        if subscription.status == account_models.LicenseStatus.EXPIRED:
            access_state = "TRIAL_EXPIRED"
        elif subscription.status == account_models.LicenseStatus.CANCELLED:
            access_state = "CANCELLED"
        return account_schemas.BillingAccessStatusRead(
            subscription=subscription,
            access_state=access_state,
            has_access=False,
            redirect_to_billing=True,
            lock_reason="This AMO subscription is locked. Go to Billing to settle dues or renew access.",
            payment_method_count=payment_method_count,
            overdue_invoice_count=overdue_invoice_count,
            actionable_invoice_id=None,
        )

    access_state = "ACTIVE"
    if subscription.status == account_models.LicenseStatus.TRIALING:
        access_state = "TRIALING"
    elif subscription.status == account_models.LicenseStatus.EXPIRED:
        access_state = "TRIAL_GRACE"

    return account_schemas.BillingAccessStatusRead(
        subscription=subscription,
        access_state=access_state,
        has_access=True,
        redirect_to_billing=False,
        lock_reason=None,
        payment_method_count=payment_method_count,
        overdue_invoice_count=overdue_invoice_count,
        actionable_invoice_id=None,
    )


def optimized_resolve_entitlements(
    db: Session,
    *,
    amo_id: str,
    as_of: datetime | None = None,
) -> dict[str, account_schemas.ResolvedEntitlement]:
    """Resolve only entitlements attached to licences that can grant access now.

    The previous implementation joined entitlements for every historical licence
    ever issued to the tenant and discarded inactive licences in Python. That
    makes lookup cost grow with customer age. This query keeps one SQL round trip
    while excluding cancelled/expired historical licence rows at the database.
    """
    now = as_of or datetime.now(timezone.utc)
    license = account_models.TenantLicense
    entitlement = account_models.LicenseEntitlement

    active_period = and_(
        license.status.in_([account_models.LicenseStatus.ACTIVE, account_models.LicenseStatus.TRIALING]),
        or_(license.current_period_start.is_(None), license.current_period_start <= now),
        or_(license.current_period_end.is_(None), license.current_period_end >= now),
        or_(
            license.status != account_models.LicenseStatus.TRIALING,
            license.trial_ends_at.is_(None),
            license.trial_ends_at >= now,
        ),
    )
    grace_period = and_(
        license.status == account_models.LicenseStatus.EXPIRED,
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
        .filter(
            license.amo_id == amo_id,
            or_(active_period, grace_period),
        )
        .all()
    )

    resolved: dict[str, account_schemas.ResolvedEntitlement] = {}
    for row in rows:
        key = str(row.key)
        if bool(row.is_unlimited):
            resolved[key] = account_schemas.ResolvedEntitlement(
                key=key,
                is_unlimited=True,
                limit=None,
                source_license_id=row.license_id,
                license_term=row.term,
                license_status=row.status,
            )
            continue
        candidate_limit = int(row.limit or 0)
        existing = resolved.get(key)
        if existing is None or (
            not existing.is_unlimited
            and int(existing.limit or 0) < candidate_limit
        ):
            resolved[key] = account_schemas.ResolvedEntitlement(
                key=key,
                is_unlimited=False,
                limit=candidate_limit,
                source_license_id=row.license_id,
                license_term=row.term,
                license_status=row.status,
            )
    return resolved


def install_billing_access_hot_path() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    account_services.get_billing_access_status = optimized_billing_access_status
    account_services.resolve_entitlements = optimized_resolve_entitlements
    _INSTALLED = True
