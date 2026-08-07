from __future__ import annotations

from typing import Any

from sqlalchemy.orm import object_session

from amodb.apps.accounts import services as account_services

from . import commercial_invoice_policy, saas_models


_INSTALLED = False


def install_fiscal_document_policy() -> None:
    """Resolve the external fiscalization row when rendering invoice views.

    ``BillingInvoice`` intentionally does not own a relationship to the newer SaaS
    control-plane table. Using ``object_session`` keeps this read bounded to one
    indexed lookup without adding a migration or coupling the legacy account model
    to platform-specific fiscalization state.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    original_build = commercial_invoice_policy.build_invoice_view_accounting

    def build_invoice_view(invoice) -> dict[str, Any]:
        view = dict(original_build(invoice))
        session = object_session(invoice)
        fiscal = None
        if session is not None and getattr(invoice, "id", None):
            fiscal = (
                session.query(saas_models.SaaSInvoiceFiscalization)
                .filter(saas_models.SaaSInvoiceFiscalization.invoice_id == invoice.id)
                .first()
            )
        if fiscal is None:
            view["etims_status"] = "NOT_FISCALIZED"
            view["etims_reference"] = None
            return view
        view["etims_status"] = str(fiscal.status or "UNKNOWN").upper()
        view["etims_reference"] = fiscal.fiscal_document_number
        view["etims_provider"] = fiscal.provider
        view["etims_fiscalized_at"] = fiscal.fiscalized_at
        return view

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
