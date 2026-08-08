from __future__ import annotations

import html
from io import BytesIO
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from amodb.database import get_db

from . import billing_access, billing_auth, models, schemas, services


router = APIRouter(prefix="/billing", tags=["billing"])


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
        "issued_label": invoice.issued_at.strftime("%d %b %Y %H:%M") if invoice.issued_at else "—",
        "due_label": invoice.due_at.strftime("%d %b %Y %H:%M") if invoice.due_at else "—",
        "paid_label": invoice.paid_at.strftime("%d %b %Y %H:%M") if invoice.paid_at else "—",
        "compliance_note": "This portal invoice has not been confirmed as a final fiscal record unless the fiscalization status below says FISCALIZED.",
    }


def _render_invoice_html(db: Session, invoice: models.BillingInvoice) -> str:
    ctx = _build_invoice_context(db, invoice)

    def esc(value: Any) -> str:
        return html.escape(str(value if value not in {None, ""} else "—"))

    description = ctx.get("line_description") or ctx.get("description") or invoice.description or "Portal subscription / service invoice"
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
          <div class="muted">eTIMS: {esc(ctx.get('etims_status'))}</div>
        </div>
        <div class="card" style="grid-column:1 / -1;">
          <table>
            <thead><tr><th>Description</th><th>Amount</th></tr></thead>
            <tbody><tr><td>{esc(description)}</td><td>{esc(ctx['currency_amount'])} {esc(invoice.currency)}</td></tr></tbody>
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

    def escape_pdf(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    description = str(ctx.get("line_description") or ctx.get("description") or invoice.description or "Portal subscription / service invoice")
    lines = [
        escape_pdf(str(ctx["seller_name"])),
        escape_pdf(str(ctx["invoice_number"])),
        escape_pdf(f"Status: {ctx['status_label']}"),
        escape_pdf(f"Issued: {ctx['issued_label']}"),
        escape_pdf(f"Bill to: {ctx['buyer_name']} ({ctx['buyer_code'] or ''})"),
        escape_pdf(f"Description: {description}"),
        escape_pdf(f"Subtotal: {ctx['subtotal_amount']} {invoice.currency}"),
        escape_pdf(f"Tax: {ctx['tax_amount']} {invoice.currency}"),
        escape_pdf(f"Total: {ctx['currency_amount']} {invoice.currency}"),
        escape_pdf(f"eTIMS: {ctx.get('etims_status') or 'NOT_FISCALIZED'}"),
    ]
    content = "BT /F1 12 Tf 50 760 Td " + " T* ".join(f"({line}) Tj" for line in lines) + " ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(content.encode('utf-8'))} >> stream {content} endstream endobj",
    ]
    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets: list[int] = []
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
    pdf.write(str(xref_start).encode("utf-8"))
    pdf.write(b"\n%%EOF")
    return pdf.getvalue()


@router.get("/access-status", response_model=schemas.BillingAccessStatusRead)
def get_billing_access_status(
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_authenticated_user),
):
    if _is_platform_superuser(current_user):
        return _platform_access_status()
    return billing_access.get_billing_access_status(db, amo_id=current_user.amo_id)


@router.get("/entitlements", response_model=list[schemas.ResolvedEntitlement])
def list_entitlements(
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_authenticated_user),
):
    if _is_platform_superuser(current_user):
        return _platform_entitlements()
    return list(billing_access.resolve_entitlements(db, amo_id=current_user.amo_id).values())


@router.get("/usage-meters", response_model=list[schemas.UsageMeterRead])
def get_usage_meters(
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_authenticated_user),
):
    if _is_platform_superuser(current_user):
        return []
    return services.list_usage_meters(db, amo_id=current_user.amo_id)


@router.get("/invoices", response_model=list[schemas.InvoiceRead])
def get_invoices(
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_billing_reader),
):
    if _is_platform_superuser(current_user):
        return []
    return [schemas.InvoiceRead(**services.build_invoice_view(invoice)) for invoice in services.list_invoices(db, amo_id=current_user.amo_id)]


@router.get("/invoices/export")
def export_invoices(
    format: Literal["csv"] = "csv",
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_billing_reader),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform superusers must export invoices from the platform billing workspace with an explicit tenant filter.")
    if format != "csv":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export format.")
    invoices = services.list_invoices(db, amo_id=current_user.amo_id)
    content = services.build_invoice_export_csv(invoices)
    amo_code = getattr(getattr(current_user, "amo", None), "amo_code", None) or current_user.amo_id
    return Response(content, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=billing-invoices-{amo_code}.csv"})


@router.get("/invoices/{invoice_id}", response_model=schemas.InvoiceDetailRead)
def get_invoice_detail(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_billing_reader),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use the platform billing workspace with an explicit tenant context.")
    invoice = db.query(models.BillingInvoice).filter(
        models.BillingInvoice.id == invoice_id,
        models.BillingInvoice.amo_id == current_user.amo_id,
    ).first()
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
    current_user=Depends(billing_auth.require_billing_reader),
):
    if _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use the platform billing workspace with an explicit tenant context.")
    invoice = db.query(models.BillingInvoice).filter(
        models.BillingInvoice.id == invoice_id,
        models.BillingInvoice.amo_id == current_user.amo_id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    if format == "pdf":
        return Response(
            _render_invoice_pdf(db, invoice),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename={_invoice_filename(invoice, "pdf")}'},
        )
    return HTMLResponse(
        _render_invoice_html(db, invoice),
        headers={"Content-Disposition": f'attachment; filename={_invoice_filename(invoice, "html")}'},
    )


@router.get("/audit", response_model=list[schemas.BillingAuditLogRead])
def list_billing_audit(
    amo_id: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_authenticated_user),
):
    if not _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    return services.list_billing_audit_logs(db, amo_id=amo_id, event_type=event_type, limit=max(1, min(limit, 200)))


@router.get("/audit/export")
def export_billing_audit(
    amo_id: str | None = None,
    event_type: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user=Depends(billing_auth.require_authenticated_user),
):
    if not _is_platform_superuser(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required.")
    logs = services.list_billing_audit_logs(db, amo_id=amo_id, event_type=event_type, limit=max(1, min(limit, 1000)))
    return Response(
        services.build_billing_audit_export_csv(logs),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=billing-audit.csv"},
    )
