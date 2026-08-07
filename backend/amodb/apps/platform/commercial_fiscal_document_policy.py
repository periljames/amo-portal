from __future__ import annotations

from typing import Any

from sqlalchemy.orm import object_session

from amodb.apps.accounts import services as account_services

from . import commercial_invoice_policy, saas_models


_INSTALLED = False
_FISCAL_ATTR = "_commercial_fiscalization"
_FISCAL_RESOLVED_ATTR = "_commercial_fiscalization_resolved"


def install_fiscal_document_policy() -> None:
    """Resolve external fiscal state without coupling legacy invoice models.

    Invoice lists batch fiscalization lookup once. Single-invoice detail/document
    paths perform one indexed lookup and cache it on the in-memory invoice object.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original_build = commercial_invoice_policy.build_invoice_view_accounting
    original_list_invoices = account_services.list_invoices

    def list_invoices(db, *args, **kwargs):
        rows = list(original_list_invoices(db, *args, **kwargs))
        invoice_ids = [str(row.id) for row in rows if getattr(row, "id", None)]
        fiscal_by_invoice: dict[str, Any] = {}
        if invoice_ids:
            fiscal_rows = (
                db.query(saas_models.SaaSInvoiceFiscalization)
                .filter(saas_models.SaaSInvoiceFiscalization.invoice_id.in_(invoice_ids))
                .all()
            )
            fiscal_by_invoice = {
                str(row.invoice_id): row for row in fiscal_rows
            }
        for invoice in rows:
            setattr(invoice, _FISCAL_ATTR, fiscal_by_invoice.get(str(invoice.id)))
            setattr(invoice, _FISCAL_RESOLVED_ATTR, True)
        return rows

    def _fiscalization(invoice):
        if bool(getattr(invoice, _FISCAL_RESOLVED_ATTR, False)):
            return getattr(invoice, _FISCAL_ATTR, None)
        session = object_session(invoice)
        fiscal = None
        if session is not None and getattr(invoice, "id", None):
            fiscal = (
                session.query(saas_models.SaaSInvoiceFiscalization)
                .filter(saas_models.SaaSInvoiceFiscalization.invoice_id == invoice.id)
                .first()
            )
        setattr(invoice, _FISCAL_ATTR, fiscal)
        setattr(invoice, _FISCAL_RESOLVED_ATTR, True)
        return fiscal

    def build_invoice_view(invoice) -> dict[str, Any]:
        view = dict(original_build(invoice))
        fiscal = _fiscalization(invoice)
        if fiscal is None:
            view["etims_status"] = "NOT_FISCALIZED"
            view["etims_reference"] = None
            return view
        view["etims_status"] = str(fiscal.status or "UNKNOWN").upper()
        view["etims_reference"] = fiscal.fiscal_document_number
        view["etims_provider"] = fiscal.provider
        view["etims_fiscalized_at"] = fiscal.fiscalized_at
        return view

    account_services.list_invoices = list_invoices
    commercial_invoice_policy.build_invoice_view_accounting = build_invoice_view
    account_services.build_invoice_view = build_invoice_view

    # router_billing was imported before the platform package. Its globals are
    # looked up at request time, so replacing this helper updates HTML/PDF output
    # without duplicating the API endpoint or changing route contracts.
    from amodb.apps.accounts import router_billing

    original_context = router_billing._build_invoice_context

    def invoice_context(db, invoice) -> dict[str, Any]:
        ctx = dict(original_context(db, invoice))
        view = build_invoice_view(invoice)
        status = str(view.get("etims_status") or "NOT_FISCALIZED").upper()
        reference = view.get("etims_reference")
        if status == "FISCALIZED":
            ctx["compliance_note"] = (
                f"Fiscalized through the configured eTIMS adapter. Fiscal reference: {reference}."
                if reference
                else "Fiscalized through the configured eTIMS adapter."
            )
        elif status == "RECONCILIATION_REQUIRED":
            ctx["compliance_note"] = (
                "eTIMS outcome requires reconciliation before this portal document is treated as the final fiscal record."
            )
        elif status in {"PENDING", "QUEUED", "SUBMITTING"}:
            ctx["compliance_note"] = (
                f"eTIMS fiscalization status: {status}. Final fiscal reference has not yet been issued."
            )
        else:
            ctx["compliance_note"] = (
                "This portal invoice has not been fiscalized through a configured certified eTIMS adapter."
            )
        return ctx

    router_billing._build_invoice_context = invoice_context
    _INSTALLED = True
