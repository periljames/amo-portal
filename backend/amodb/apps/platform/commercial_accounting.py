from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import saas_models, saas_services


def _tenant_ids(db: Session, mode: str) -> list[str]:
    query = db.query(account_models.AMO.id)
    if mode == "REAL":
        query = query.filter(account_models.AMO.is_demo.is_(False))
    elif mode == "DEMO":
        query = query.filter(account_models.AMO.is_demo.is_(True))
    return [str(row[0]) for row in query.all()]


def _currency_sums(query) -> dict[str, int]:
    return {
        str(currency or "USD").upper(): int(amount or 0)
        for currency, amount in query.group_by(account_models.BillingInvoice.currency).all()
    }


def _currency_counts(query) -> dict[str, int]:
    return {
        str(currency or "USD").upper(): int(count or 0)
        for currency, count in query.group_by(account_models.BillingInvoice.currency).all()
    }


def subledger_summary(db: Session, *, data_mode: str = "REAL") -> dict[str, Any]:
    """Return platform billing metrics without ever summing unlike currencies."""
    mode = str(data_mode or "REAL").strip().upper()
    if mode not in {"REAL", "DEMO", "ALL"}:
        mode = "REAL"
    tenant_ids = _tenant_ids(db, mode)
    now = saas_services.utcnow()
    since = now - timedelta(days=30)

    if not tenant_ids:
        return {
            "data_mode": mode,
            "outstanding_ar_by_currency": {},
            "overdue_ar_by_currency": {},
            "overdue_invoice_count_by_currency": {},
            "invoiced_30d_by_currency": {},
            "collected_30d_by_currency": {},
            "failed_payment_jobs_30d": 0,
            "provider_statuses": {},
            "metric_quality": {
                "ar_and_collection_metrics": "AUTHORITATIVE_PORTAL_SUBLEDGER",
                "cross_currency_aggregation": "PROHIBITED",
                "mrr_arr": "LEGACY_LICENSE_MODEL_NOT_AUTHORITATIVE_FOR_MULTI_CURRENCY",
                "logo_churn": "NOT_IMPLEMENTED",
                "net_revenue_retention": "NOT_IMPLEMENTED",
                "gross_revenue_retention": "NOT_IMPLEMENTED",
            },
        }

    base = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.amo_id.in_(tenant_ids))
    outstanding = _currency_sums(
        base.with_entities(
            account_models.BillingInvoice.currency,
            func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0),
        ).filter(account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING)
    )
    overdue_base = base.filter(
        account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING,
        account_models.BillingInvoice.due_at.isnot(None),
        account_models.BillingInvoice.due_at < now,
    )
    overdue = _currency_sums(
        overdue_base.with_entities(
            account_models.BillingInvoice.currency,
            func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0),
        )
    )
    overdue_counts = _currency_counts(
        overdue_base.with_entities(
            account_models.BillingInvoice.currency,
            func.count(account_models.BillingInvoice.id),
        )
    )
    invoiced = _currency_sums(
        base.with_entities(
            account_models.BillingInvoice.currency,
            func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0),
        ).filter(account_models.BillingInvoice.created_at >= since)
    )
    collected = _currency_sums(
        base.with_entities(
            account_models.BillingInvoice.currency,
            func.coalesce(func.sum(account_models.BillingInvoice.amount_cents), 0),
        ).filter(
            account_models.BillingInvoice.status == account_models.InvoiceStatus.PAID,
            account_models.BillingInvoice.paid_at.isnot(None),
            account_models.BillingInvoice.paid_at >= since,
        )
    )
    failed_jobs = int(
        db.query(func.count(saas_models.SaaSJob.id))
        .filter(
            saas_models.SaaSJob.tenant_id.in_(tenant_ids),
            saas_models.SaaSJob.queue_name == "billing",
            saas_models.SaaSJob.status.in_(["FAILED", "DEAD"]),
            saas_models.SaaSJob.created_at >= since,
        )
        .scalar()
        or 0
    )
    providers = saas_services.list_provider_credentials(db)
    provider_statuses = {
        str(item.get("provider")): str(item.get("status"))
        for item in providers
        if item.get("category") in {"BILLING", "PAYMENTS", "ACCOUNTING", "TAX"}
    }
    return {
        "data_mode": mode,
        "outstanding_ar_by_currency": outstanding,
        "overdue_ar_by_currency": overdue,
        "overdue_invoice_count_by_currency": overdue_counts,
        "invoiced_30d_by_currency": invoiced,
        "collected_30d_by_currency": collected,
        "failed_payment_jobs_30d": failed_jobs,
        "provider_statuses": provider_statuses,
        "metric_quality": {
            "ar_and_collection_metrics": "AUTHORITATIVE_PORTAL_SUBLEDGER",
            "cross_currency_aggregation": "PROHIBITED",
            "mrr_arr": "LEGACY_LICENSE_MODEL_NOT_AUTHORITATIVE_FOR_MULTI_CURRENCY",
            "logo_churn": "NOT_IMPLEMENTED",
            "net_revenue_retention": "NOT_IMPLEMENTED",
            "gross_revenue_retention": "NOT_IMPLEMENTED",
        },
    }
