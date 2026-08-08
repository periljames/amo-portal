from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.accounts import services as account_services

from . import commercial_access_policy


_INSTALLED = False


def _current_module_count(db: Session, *, amo_id: str, now: datetime) -> int:
    return int(
        db.query(func.count(account_models.ModuleSubscription.id))
        .filter(
            account_models.ModuleSubscription.amo_id == amo_id,
            account_models.ModuleSubscription.status.in_([
                account_models.ModuleSubscriptionStatus.ENABLED,
                account_models.ModuleSubscriptionStatus.TRIAL,
            ]),
            or_(
                account_models.ModuleSubscription.effective_from.is_(None),
                account_models.ModuleSubscription.effective_from <= now,
            ),
            or_(
                account_models.ModuleSubscription.effective_to.is_(None),
                account_models.ModuleSubscription.effective_to >= now,
            ),
        )
        .scalar()
        or 0
    )


def _account_overdue_row(db: Session, *, amo_id: str, now: datetime):
    """Return only arrears that are allowed to suspend the whole tenant.

    Optional module orders have no due date. Module renewal invoices are scoped
    to their module even if an older snapshot used ACCOUNT; source is checked too
    so historical renewal invoices cannot suddenly suspend unrelated modules.
    """
    description = account_models.BillingInvoice.description
    is_module_scoped = or_(
        description.contains('"lock_scope":"MODULE"'),
        description.contains('"source":"MODULE_RENEWAL"'),
    )
    return (
        db.query(
            account_models.BillingInvoice.id.label("invoice_id"),
            func.count(account_models.BillingInvoice.id).over().label("overdue_count"),
        )
        .filter(
            account_models.BillingInvoice.amo_id == amo_id,
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
            account_models.BillingInvoice.due_at.isnot(None),
            account_models.BillingInvoice.due_at <= now,
            or_(description.is_(None), ~is_module_scoped),
        )
        .order_by(account_models.BillingInvoice.due_at.asc(), account_models.BillingInvoice.id.asc())
        .first()
    )


def scoped_billing_access_status(
    db: Session,
    *,
    amo_id: str,
    as_of: datetime | None = None,
) -> account_schemas.BillingAccessStatusRead:
    now = as_of or datetime.now(timezone.utc)
    license = commercial_access_policy._access_license(db, amo_id=amo_id, now=now)
    payment_method_count = int(
        db.query(func.count(account_models.PaymentMethod.id))
        .filter(account_models.PaymentMethod.amo_id == amo_id)
        .scalar()
        or 0
    )
    active_module_count = _current_module_count(db, amo_id=amo_id, now=now)
    overdue = _account_overdue_row(db, amo_id=amo_id, now=now)
    actionable_invoice_id = str(overdue.invoice_id) if overdue is not None else None
    overdue_invoice_count = int(overdue.overdue_count or 0) if overdue is not None else 0

    # Account-level debt always takes precedence over individual product state.
    if overdue is not None:
        subscription = None
        if license is not None:
            subscription = commercial_access_policy._project_subscription(
                license,
                now=now,
                has_payment_method=False,
                has_overdue_invoice=True,
            )
        return account_schemas.BillingAccessStatusRead(
            subscription=subscription,
            access_state="PAYMENT_OVERDUE",
            has_access=False,
            redirect_to_billing=True,
            lock_reason="Account billing is overdue. Please settle the outstanding account invoice to continue.",
            payment_method_count=payment_method_count,
            overdue_invoice_count=overdue_invoice_count,
            actionable_invoice_id=actionable_invoice_id,
        )

    projected = None
    if license is not None:
        projected = commercial_access_policy._project_subscription(
            license,
            now=now,
            has_payment_method=False,
            has_overdue_invoice=False,
        )
        if not projected.is_read_only:
            access_state = "ACTIVE"
            if projected.status == account_models.LicenseStatus.TRIALING:
                access_state = "TRIALING"
            elif projected.status == account_models.LicenseStatus.EXPIRED:
                access_state = "TRIAL_GRACE"
            return account_schemas.BillingAccessStatusRead(
                subscription=projected,
                access_state=access_state,
                has_access=True,
                redirect_to_billing=False,
                lock_reason=None,
                payment_method_count=payment_method_count,
                overdue_invoice_count=0,
                actionable_invoice_id=None,
            )

    # Explicit commercial module subscriptions are authoritative for migrated or
    # module-only customers. Stale historical base licences must not falsely lock
    # an otherwise paid tenant after the commercial model has moved to modules.
    if active_module_count > 0:
        return account_schemas.BillingAccessStatusRead(
            subscription=None,
            access_state="MODULE_SUBSCRIBED",
            has_access=True,
            redirect_to_billing=False,
            lock_reason=None,
            payment_method_count=payment_method_count,
            overdue_invoice_count=0,
            actionable_invoice_id=None,
        )

    if projected is not None:
        access_state = "LOCKED"
        if projected.status == account_models.LicenseStatus.EXPIRED:
            access_state = "EXPIRED"
        elif projected.status == account_models.LicenseStatus.CANCELLED:
            access_state = "CANCELLED"
        return account_schemas.BillingAccessStatusRead(
            subscription=projected,
            access_state=access_state,
            has_access=False,
            redirect_to_billing=True,
            lock_reason="This AMO has no current paid account or module contract. Go to Billing to renew access.",
            payment_method_count=payment_method_count,
            overdue_invoice_count=0,
            actionable_invoice_id=None,
        )

    return account_schemas.BillingAccessStatusRead(
        subscription=None,
        access_state="NO_SUBSCRIPTION",
        has_access=False,
        redirect_to_billing=True,
        lock_reason="This AMO has no current paid subscription. An authorised billing user can select and activate modules in Billing.",
        payment_method_count=payment_method_count,
        overdue_invoice_count=0,
        actionable_invoice_id=None,
    )


def install_commercial_access_scope_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    account_services.get_billing_access_status = scoped_billing_access_status
    _INSTALLED = True
