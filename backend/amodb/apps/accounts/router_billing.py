# backend/amodb/apps/accounts/router_billing.py

from __future__ import annotations

from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import HTMLResponse, Response
import html
from io import BytesIO
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import audit, schemas, services, models

router = APIRouter(prefix="/billing", tags=["billing"])


def _require_user(current_user=Depends(get_current_active_user)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return current_user



def _is_platform_superuser(user) -> bool:
    return bool(getattr(user, "is_superuser", False))


def _platform_entitlements() -> list[schemas.ResolvedEntitlement]:
    return [
        schemas.ResolvedEntitlement(
            key="platform.superuser",
            is_unlimited=True,
            limit=None,
            source_license_id="platform-superuser",
            license_term=models.BillingTerm.ANNUAL,
            license_status=models.LicenseStatus.ACTIVE,
        ),
        schemas.ResolvedEntitlement(
            key="platform.control",
            is_unlimited=True,
            limit=None,
            source_license_id="platform-superuser",
            license_term=models.BillingTerm.ANNUAL,
            license_status=models.LicenseStatus.ACTIVE,
        ),
    ]


def _platform_access_status() -> schemas.BillingAccessStatusRead:
    return schemas.BillingAccessStatusRead(
        subscription=None,
        access_state="PLATFORM_SUPERUSER",
        has_access=True,
        redirect_to_billing=False,
        lock_reason=None,
        payment_method_count=0,
        overdue_invoice_count=0,
        actionable_invoice_id=None,
    )

def _invoice_filename(invoice: models.BillingInvoice, suffix: str) -> str:
    return f"{services.format_invoice_number(invoice)}.{suffix}"


def _resolve_platform_settings(db: Session) -> models.PlatformSettings | None:
    try:
        return db.query(models.PlatformSettings).first()
    except Exception:
        return None


def _build_invoice_context(db: Session, invoice: models.BillingInvoice) -> dict[str, Any]:
    settings = _resolve_platform_settings(db)
    view = services.build_invoice_view(invoice)
    amo = getattr(invoice, "amo", None)
    return {
        **view,
        "status_label": getattr(invoice.status, "value", str(invoice.status)),
        "seller_name": (getattr(settings, "platform_name", None) or "AMO Portal").strip(),
        "seller_tagline": getattr(settings, "platform_tagline", None),
        "buyer_code": getattr(amo, "amo_code", None),
        "buyer_name": getattr(amo, "name", None),
        "buyer_email": getattr(amo, "contact_email", None),
        "buyer_phone": getattr(amo, "contact_phone", None),
        "currency_amount": f"{(view['total_cents'] or 0) / 100:.2f}",
        "subtotal_amount": f"{(view['subtotal_cents'] or 0) / 100:.2f}",
        "tax_amount": f"{(view['tax_amount_cents'] or 0) / 100:.2f}",
        "issued_label": invoice.issued_at.strftime('%d %b %Y %H:%M') if invoice.issued_at else 'â€”',
        "due_label": invoice.due_at.strftime('%d %b %Y %H:%M') if invoice.due_at else 'â€”',
        "paid_label": invoice.paid_at.strftime('%d %b %Y %H:%M') if invoice.paid_at else 'â€”',
        "compliance_note": 'eTIMS bridge not yet connected. This invoice is audit-ready for the portal but should not be treated as a KRA eTIMS fiscal invoice until eTIMS integration is configured.',
    }


def _render_invoice_html(db: Session, invoice: models.BillingInvoice) -> str:
    ctx = _build_invoice_context(db, invoice)
    def esc(v: Any) -> str:
        return html.escape(str(v or 'â€”'))
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{esc(ctx['invoice_number'])}</title>
    <style>
      body {{ font-family: Arial, sans-serif; padding: 24px; color: #0f172a; background: #f8fafc; }}
      .sheet {{ max-width: 940px; margin: 0 auto; background: white; border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; }}
      .hero {{ padding: 24px 28px; display: flex; justify-content: space-between; gap: 24px; border-bottom: 1px solid #e2e8f0; }}
      .muted {{ color: #64748b; }}
      .pill {{ display:inline-block; padding:6px 10px; border-radius:999px; background:#eff6ff; color:#1d4ed8; font-size:12px; font-weight:700; }}
      .grid {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 18px; padding: 24px 28px; }}
      .card {{ border:1px solid #e2e8f0; border-radius:12px; padding:16px; background:#fff; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ text-align:left; padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }}
      .totals td {{ font-weight:700; }}
      .note {{ padding: 0 28px 24px; color:#475569; font-size: 13px; }}
    </style>
  </head>
  <body>
    <div class="sheet">
      <div class="hero">
        <div>
          <div class="pill">Portal invoice</div>
          <h1 style="margin:12px 0 6px;">{esc(ctx['invoice_number'])}</h1>
          <div class="muted">Issued {esc(ctx['issued_label'])}</div>
          <div class="muted">Status {esc(ctx['status_label'])}</div>
        </div>
        <div style="text-align:right;">
          <h2 style="margin:0 0 6px;">{esc(ctx['seller_name'])}</h2>
          <div class="muted">{esc(ctx['seller_tagline'])}</div>
        </div>
      </div>
      <div class="grid">
        <div class="card">
          <strong>Bill to</strong>
          <div>{esc(ctx['buyer_name'])}</div>
          <div class="muted">AMO code: {esc(ctx['buyer_code'])}</div>
          <div class="muted">Email: {esc(ctx['buyer_email'])}</div>
          <div class="muted">Phone: {esc(ctx['buyer_phone'])}</div>
        </div>
        <div class="card">
          <strong>Commercial summary</strong>
          <div class="muted">Due: {esc(ctx['due_label'])}</div>
          <div class="muted">Paid: {esc(ctx['paid_label'])}</div>
          <div class="muted">eTIMS: {esc(ctx['etims_status'])}</div>
        </div>
        <div class="card" style="grid-column:1 / -1;">
          <table>
            <thead>
              <tr><th>Description</th><th>Amount</th></tr>
            </thead>
            <tbody>
              <tr><td>{esc(invoice.description or 'Portal subscription / service invoice')}</td><td>{esc(ctx['currency_amount'])} {esc(invoice.currency)}</td></tr>
            </tbody>
            <tfoot>
              <tr class="totals"><td>Subtotal</td><td>{esc(ctx['subtotal_amount'])} {esc(invoice.currency)}</td></tr>
              <tr class="totals"><td>Tax</td><td>{esc(ctx['tax_amount'])} {esc(invoice.currency)}</td></tr>
              <tr class="totals"><td>Total</td><td>{esc(ctx['currency_amount'])} {esc(invoice.currency)}</td></tr>
            </tfoot>
          </table>
        </div>
      </div>
      <div class="note">{esc(ctx['compliance_note'])}</div>
    </div>
  </body>
</html>
"""


def _render_invoice_pdf(db: Session, invoice: models.BillingInvoice) -> bytes:
    ctx = _build_invoice_context(db, invoice)
    def _escape(text: str) -> str:
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    lines = [
        _escape(ctx['seller_name']),
        _escape(ctx['invoice_number']),
        _escape(f"Status: {ctx['status_label']}"),
        _escape(f"Issued: {ctx['issued_label']}"),
        _escape(f"Bill to: {ctx['buyer_name']} ({ctx['buyer_code'] or ''})"),
        _escape(f"Description: {invoice.description or 'Portal subscription / service invoice'}"),
        _escape(f"Subtotal: {ctx['subtotal_amount']} {invoice.currency}"),
        _escape(f"Tax: {ctx['tax_amount']} {invoice.currency}"),
        _escape(f"Total: {ctx['currency_amount']} {invoice.currency}"),
        _escape(f"eTIMS: {ctx['etims_status']}"),
    ]
    text_lines = ' T* '.join([f"({line}) Tj" for line in lines])
    content = f"BT /F1 12 Tf 50 760 Td {text_lines} ET"
    objects = []
    objects.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append("3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj")
    objects.append("4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
    content_bytes = content.encode('utf-8')
    objects.append(f"5 0 obj << /Length {len(content_bytes)} >> stream {content_bytes.decode('utf-8')} endstream endobj")
    offsets = []
    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj.encode('utf-8'))
        pdf.write(b"\n")
    xref_start = pdf.tell()
    pdf.write(b"xref\n0 %d\n" % (len(objects) + 1))
    pdf.write(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.write(f"{offset:010d} 00000 n \n".encode('utf-8'))
    pdf.write(b"trailer << /Size %d /Root 1 0 R >>\n" % (len(objects) + 1))
    pdf.write(b"startxref\n")
    pdf.write(f"{xref_start}".encode('utf-8'))
    pdf.write(b"\n%%EOF")
    return pdf.getvalue()


@router.get("/catalog", response_model=list[schemas.CatalogSKURead])
def list_catalog(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if include_inactive and not getattr(current_user, "is_superuser", False):
        include_inactive = False
    return services.list_catalog_skus(db, include_inactive=include_inactive)


@router.post(
    "/catalog",
    response_model=schemas.CatalogSKURead,
    status_code=status.HTTP_201_CREATED,
)
def create_catalog(
    payload: schemas.CatalogSKUCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    try:
        return services.create_catalog_sku(
            db,
            data=payload,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put(
    "/catalog/{sku_id}",
    response_model=schemas.CatalogSKURead,
)
def update_catalog(
    sku_id: str,
    payload: schemas.CatalogSKUUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    try:
        return services.update_catalog_sku(
            db,
            sku_id=sku_id,
            data=payload,
            actor_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/entitlements", response_model=list[schemas.ResolvedEntitlement])
def list_entitlements(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        return _platform_entitlements()
    entitlements = services.resolve_entitlements(db, amo_id=current_user.amo_id)
    return list(entitlements.values())


@router.get("/subscription", response_model=schemas.SubscriptionRead)
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform superuser is not a billable AMO tenant.",
        )
    subscription = services.get_effective_subscription(db, amo_id=current_user.amo_id)
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription.")
    return subscription


@router.get("/access-status", response_model=schemas.BillingAccessStatusRead)
def get_billing_access_status(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        return _platform_access_status()
    return services.get_billing_access_status(db, amo_id=current_user.amo_id)


@router.get("/invoices", response_model=list[schemas.InvoiceRead])
def get_invoices(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        return []
    invoices = services.list_invoices(db, amo_id=current_user.amo_id)
    return [schemas.InvoiceRead(**services.build_invoice_view(invoice)) for invoice in invoices]


@router.get("/invoices/{invoice_id}", response_model=schemas.InvoiceDetailRead)
def get_invoice_detail(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    invoice = (
        db.query(models.BillingInvoice)
        .filter(
            models.BillingInvoice.id == invoice_id,
            models.BillingInvoice.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    data = schemas.InvoiceDetailRead(**services.build_invoice_view(invoice))
    if invoice.ledger_entry:
        data.ledger_entry = schemas.LedgerEntryRead.model_validate(invoice.ledger_entry, from_attributes=True)
    return data


@router.get("/invoices/{invoice_id}/document")
def get_invoice_document(
    invoice_id: str,
    format: Literal["html", "pdf"] = "html",
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    invoice = (
        db.query(models.BillingInvoice)
        .filter(
            models.BillingInvoice.id == invoice_id,
            models.BillingInvoice.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    if format == "pdf":
        pdf_bytes = _render_invoice_pdf(db, invoice)
        return Response(
            pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename={_invoice_filename(invoice, "pdf")}'
            },
        )
    html_doc = _render_invoice_html(db, invoice)
    return HTMLResponse(
        html_doc,
        headers={
            "Content-Disposition": f'attachment; filename={_invoice_filename(invoice, "html")}'
        },
    )


@router.get("/invoices/export")
def export_invoices(
    format: Literal["csv"] = "csv",
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform superusers must export invoices from the billing audit workspace with an explicit tenant filter.",
        )
    invoices = services.list_invoices(db, amo_id=current_user.amo_id)
    if format == "csv":
        content = services.build_invoice_export_csv(invoices)
        amo_code = getattr(getattr(current_user, "amo", None), "amo_code", None) or current_user.amo_id
        filename = f"billing-invoices-{amo_code}.csv"
        return Response(content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export format.")


@router.get("/audit/export")
def export_billing_audit(
    amo_id: str | None = None,
    event_type: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    logs = services.list_billing_audit_logs(db, amo_id=amo_id, event_type=event_type, limit=max(1, min(limit, 1000)))
    content = services.build_billing_audit_export_csv(logs)
    return Response(content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=billing-audit.csv"})


@router.get("/usage-meters", response_model=list[schemas.UsageMeterRead])
def get_usage_meters(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        return []
    return services.list_usage_meters(db, amo_id=current_user.amo_id)


@router.get("/audit", response_model=list[schemas.BillingAuditLogRead])
def list_billing_audit(
    amo_id: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    limit = max(1, min(limit, 200))
    return services.list_billing_audit_logs(
        db, amo_id=amo_id, event_type=event_type, limit=limit
    )


@router.get("/payment-methods", response_model=list[schemas.PaymentMethodRead])
def get_payment_methods(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        return []
    return services.list_payment_methods(db, amo_id=current_user.amo_id)


@router.post("/payment-methods", response_model=schemas.PaymentMethodRead, status_code=status.HTTP_201_CREATED)
def add_payment_method(
    payload: schemas.PaymentMethodUpsertRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers cannot mutate tenant payment methods from a global session.")
    if payload.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AMO mismatch.")
    return services.add_payment_method(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        idempotency_key=payload.idempotency_key,
    )


@router.delete("/payment-methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_method(
    payment_method_id: str,
    payload: schemas.PaymentMethodMutationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers cannot mutate tenant payment methods from a global session.")
    services.remove_payment_method(
        db,
        amo_id=current_user.amo_id,
        payment_method_id=payment_method_id,
        idempotency_key=payload.idempotency_key,
    )
    return {}


@router.post("/trial", response_model=schemas.SubscriptionRead, status_code=status.HTTP_201_CREATED)
def start_trial(
    payload: schemas.TrialStartRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers cannot start a tenant trial from a global session.")
    try:
        license = services.start_trial(
            db,
            amo_id=current_user.amo_id,
            sku_code=payload.sku_code,
            idempotency_key=payload.idempotency_key,
        )
        return license
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post("/purchase", response_model=schemas.SubscriptionRead, status_code=status.HTTP_201_CREATED)
def purchase(
    payload: schemas.PurchaseRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers cannot purchase tenant subscriptions from a global session.")
    license, _ledger, _invoice = services.purchase_sku(
        db,
        amo_id=current_user.amo_id,
        sku_code=payload.sku_code,
        idempotency_key=payload.idempotency_key,
        purchase_kind=payload.purchase_kind,
        expected_amount_cents=payload.expected_amount_cents,
        expected_currency=payload.currency,
    )
    return license


@router.post("/cancel", response_model=schemas.SubscriptionRead)
def cancel(
    payload: schemas.CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers cannot cancel tenant subscriptions from a global session.")
    license = services.cancel_subscription(
        db,
        amo_id=current_user.amo_id,
        effective_date=payload.effective_date,
        idempotency_key=payload.idempotency_key,
    )
    if not license:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription to cancel.")
    return license


@router.post("/audit-events", status_code=status.HTTP_202_ACCEPTED)
def record_audit_event(
    payload: schemas.AuditEventCreate,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers must record billing audit events with an explicit tenant workflow.")
    log = audit.safe_record_audit_event(
        db,
        amo_id=current_user.amo_id,
        event=payload.event_type.strip(),
        details=payload.details or {},
    )
    return {
        "id": log.id if log else None,
        "created_at": log.created_at if log else None,
    }


@router.post("/webhooks/{provider}", status_code=status.HTTP_202_ACCEPTED)
async def webhook_handler(
    provider: models.PaymentProvider,
    request: Request,
    psp_signature: str = Header(None, alias="X-PSP-Signature"),
    db: Session = Depends(get_db),
):
    payload: Dict[str, Any] = await request.json()
    external_id = payload.get("id") or payload.get("event_id") or "unknown"
    should_fail = payload.get("simulate_failure", False)
    event = services.handle_webhook(
        db,
        provider=provider,
        payload=payload,
        signature=psp_signature or "",
        external_event_id=str(external_id),
        event_type=payload.get("type"),
        should_fail=bool(should_fail),
    )
    return {"status": event.status}

