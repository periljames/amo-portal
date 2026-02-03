# backend/amodb/apps/accounts/router_billing.py

from __future__ import annotations

from typing import Any, Dict

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


def _render_invoice_html(invoice: models.BillingInvoice) -> str:
    description = html.escape(invoice.description or "Invoice")
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Invoice {invoice.id}</title>
    <style>
      body {{ font-family: Arial, sans-serif; padding: 24px; color: #111827; }}
      .card {{ border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; }}
      .row {{ display: flex; justify-content: space-between; margin-bottom: 12px; }}
      .muted {{ color: #6b7280; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
      th, td {{ border-bottom: 1px solid #e5e7eb; text-align: left; padding: 8px; }}
    </style>
  </head>
  <body>
    <div class="card">
      <div class="row">
        <div>
          <h2>Invoice</h2>
          <div class="muted">ID: {invoice.id}</div>
        </div>
        <div>
          <div>Status: {invoice.status}</div>
          <div>Issued: {invoice.issued_at}</div>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Description</th>
            <th>Amount</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{description}</td>
            <td>{invoice.amount_cents / 100:.2f} {invoice.currency}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </body>
</html>
"""


def _render_invoice_pdf(invoice: models.BillingInvoice) -> bytes:
    # Minimal PDF with a single page and a few text lines.
    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = [
        _escape(f"Invoice {invoice.id}"),
        _escape(f"Status: {invoice.status}"),
        _escape(f"Issued: {invoice.issued_at}"),
        _escape(f"Amount: {invoice.amount_cents / 100:.2f} {invoice.currency}"),
        _escape(f"Description: {invoice.description or 'Invoice'}"),
    ]
    text_lines = " T* ".join([f"({line}) Tj" for line in lines])
    content = f"BT /F1 12 Tf 50 750 Td {text_lines} ET"
    objects = []
    objects.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj"
    )
    objects.append("4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
    objects.append(f"5 0 obj << /Length {len(content)} >> stream {content} endstream endobj")

    offsets = []
    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj.encode("utf-8"))
        pdf.write(b"\n")
    xref_start = pdf.tell()
    pdf.write(b"xref\n0 %d\n" % (len(objects) + 1))
    pdf.write(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
    pdf.write(b"trailer << /Size %d /Root 1 0 R >>\n" % (len(objects) + 1))
    pdf.write(b"startxref\n")
    pdf.write(f"{xref_start}".encode("utf-8"))
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


@router.get("/entitlements", response_model=list[schemas.ResolvedEntitlement])
def list_entitlements(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    entitlements = services.resolve_entitlements(db, amo_id=current_user.amo_id)
    return list(entitlements.values())


@router.get("/subscription", response_model=schemas.SubscriptionRead)
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    license = services.get_current_subscription(db, amo_id=current_user.amo_id)
    if not license:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription.")
    return license


@router.get("/invoices", response_model=list[schemas.InvoiceRead])
def get_invoices(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
    return services.list_invoices(db, amo_id=current_user.amo_id)


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
    data = schemas.InvoiceDetailRead.model_validate(invoice, from_attributes=True)
    if invoice.ledger_entry:
        data.ledger_entry = schemas.LedgerEntryRead.model_validate(
            invoice.ledger_entry, from_attributes=True
        )
    return data


@router.get("/invoices/{invoice_id}/document")
def get_invoice_document(
    invoice_id: str,
    format: str = "html",
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
        pdf_bytes = _render_invoice_pdf(invoice)
        return Response(
            pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=invoice-{invoice.id}.pdf"
            },
        )
    html_doc = _render_invoice_html(invoice)
    return HTMLResponse(
        html_doc,
        headers={
            "Content-Disposition": f"attachment; filename=invoice-{invoice.id}.html"
        },
    )


@router.get("/usage-meters", response_model=list[schemas.UsageMeterRead])
def get_usage_meters(
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
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
    return services.list_payment_methods(db, amo_id=current_user.amo_id)


@router.post("/payment-methods", response_model=schemas.PaymentMethodRead, status_code=status.HTTP_201_CREATED)
def add_payment_method(
    payload: schemas.PaymentMethodUpsertRequest,
    db: Session = Depends(get_db),
    current_user=Depends(_require_user),
):
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
