from __future__ import annotations

import io
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pdfrw import PageMerge, PdfReader, PdfWriter
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


@dataclass
class SignResult:
    output_pdf_bytes: bytes
    appearance_applied: bool
    cryptographic_signature_applied: bool
    signing_provider: str
    provider_transaction_id: str | None
    certificate_subject: str | None
    certificate_serial: str | None
    signing_time: datetime | None
    timestamp_applied: bool
    raw_provider_metadata: dict[str, Any]


@dataclass
class ValidationResult:
    cryptographically_valid: bool
    signature_present: bool
    certificate_subject: str | None
    certificate_serial: str | None
    signing_time: datetime | None
    timestamp_present: bool
    timestamp_valid: bool | None
    chain_valid: bool | None
    revocation_checked: bool | None
    validation_summary: dict[str, Any]
    raw_validation_metadata: dict[str, Any]


class SigningProvider:
    name = "base"

    def sign_pdf(self, input_pdf_bytes: bytes, signing_context: dict[str, Any]) -> SignResult:
        raise NotImplementedError

    def validate_pdf(self, signed_pdf_bytes: bytes, validation_context: dict[str, Any]) -> ValidationResult:
        raise NotImplementedError

    def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "provider": self.name}


class AppearanceOnlyProvider(SigningProvider):
    name = "appearance_only"

    def sign_pdf(self, input_pdf_bytes: bytes, signing_context: dict[str, Any]) -> SignResult:
        base = PdfReader(fdata=input_pdf_bytes)
        if not base.pages:
            raise ValueError("PDF has no pages")

        overlay_buf = io.BytesIO()
        c = canvas.Canvas(overlay_buf)
        first_page = base.pages[0]
        width = float(first_page.MediaBox[2])
        height = float(first_page.MediaBox[3])
        c.setPageSize((width, height))

        placements = signing_context.get("placements", [])
        signer_name = signing_context.get("signer_name", "Signer")
        approved_at = signing_context.get("approved_at") or datetime.now(timezone.utc).isoformat()
        doc_hash = signing_context.get("doc_hash", "")

        for placement in placements:
            x = float(placement.get("x", 72))
            y = float(placement.get("y", 72))
            c.setFillColor(HexColor("#0b5cab"))
            c.rect(x, y, 180, 42, stroke=1, fill=0)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x + 8, y + 27, "E-Signature Approval")
            c.setFont("Helvetica", 8)
            c.drawString(x + 8, y + 16, signer_name[:28])
            c.drawString(x + 8, y + 6, approved_at[:24])
            c.setFillColor(HexColor("#1f2937"))
            c.setFont("Helvetica", 7)
            c.drawString(x + 8, y + 3, "Signature")
            c.setFillColor(HexColor("#0b5cab"))
            c.circle(x + 140, y + 15, 14, stroke=1, fill=0)
            c.setFont("Helvetica", 7)
            c.drawString(x + 132, y + 13, "STAMP")

        verify_url = signing_context.get("verification_url", "")
        qr_widget = qr.QrCodeWidget(verify_url)
        bounds = qr_widget.getBounds()
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        size = 80
        d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
        d.add(qr_widget)
        renderPDF.draw(d, c, width - 100, 30)

        c.setFont("Helvetica", 7)
        c.drawString(40, 24, "Visual signature appearance applied. Cryptographic PDF signature: NO")
        c.drawString(40, 14, f"Document SHA-256: {doc_hash[:24]}...")
        c.save()

        overlay = PdfReader(fdata=overlay_buf.getvalue())
        PageMerge(base.pages[0]).add(overlay.pages[0]).render()

        out = io.BytesIO()
        PdfWriter().write(out, base)
        return SignResult(
            output_pdf_bytes=out.getvalue(),
            appearance_applied=True,
            cryptographic_signature_applied=False,
            signing_provider=self.name,
            provider_transaction_id=None,
            certificate_subject=None,
            certificate_serial=None,
            signing_time=None,
            timestamp_applied=False,
            raw_provider_metadata={"mode": "appearance_only"},
        )

    def validate_pdf(self, signed_pdf_bytes: bytes, validation_context: dict[str, Any]) -> ValidationResult:
        return ValidationResult(
            cryptographically_valid=False,
            signature_present=False,
            certificate_subject=None,
            certificate_serial=None,
            signing_time=None,
            timestamp_present=False,
            timestamp_valid=None,
            chain_valid=None,
            revocation_checked=None,
            validation_summary={"mode": "appearance_only", "note": "No cryptographic signature present"},
            raw_validation_metadata={"mode": "appearance_only"},
        )


class LocalPadesPlaceholderProvider(SigningProvider):
    name = "local_pades_placeholder"

    def sign_pdf(self, input_pdf_bytes: bytes, signing_context: dict[str, Any]) -> SignResult:
        raise NotImplementedError("Local PAdES placeholder cannot produce cryptographic signatures")

    def validate_pdf(self, signed_pdf_bytes: bytes, validation_context: dict[str, Any]) -> ValidationResult:
        return ValidationResult(
            cryptographically_valid=False,
            signature_present=False,
            certificate_subject=None,
            certificate_serial=None,
            signing_time=None,
            timestamp_present=False,
            timestamp_valid=None,
            chain_valid=None,
            revocation_checked=None,
            validation_summary={"error": "not_implemented"},
            raw_validation_metadata={"provider": self.name},
        )


class ExternalPadesProvider(SigningProvider):
    name = "external_pades"

    def __init__(
        self,
        *,
        sign_url: str,
        validate_url: str,
        timeout_seconds: int,
        auth_mode: str,
        bearer_token: str | None,
    ):
        self.sign_url = sign_url
        self.validate_url = validate_url
        self.timeout_seconds = timeout_seconds
        self.auth_mode = auth_mode
        self.bearer_token = bearer_token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_mode == "bearer" and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _post_json(self, url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 200))
            body = resp.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return status, parsed

    def sign_pdf(self, input_pdf_bytes: bytes, signing_context: dict[str, Any]) -> SignResult:
        payload = {
            "pdf_base64": signing_context["pdf_base64"],
            "signing_context": signing_context,
        }
        status, parsed = self._post_json(self.sign_url, payload)
        signed_b64 = parsed.get("signed_pdf_base64")
        if status >= 400 or not signed_b64:
            raise RuntimeError(parsed.get("error") or "external provider signing failed")
        output_bytes = io.BytesIO()
        output_bytes.write(__import__("base64").b64decode(signed_b64))
        st = parsed.get("signing_time")
        signing_time = datetime.fromisoformat(st) if st else None
        return SignResult(
            output_pdf_bytes=output_bytes.getvalue(),
            appearance_applied=bool(parsed.get("appearance_applied", True)),
            cryptographic_signature_applied=bool(parsed.get("cryptographic_signature_applied", False)),
            signing_provider=self.name,
            provider_transaction_id=parsed.get("provider_transaction_id"),
            certificate_subject=parsed.get("certificate_subject"),
            certificate_serial=parsed.get("certificate_serial"),
            signing_time=signing_time,
            timestamp_applied=bool(parsed.get("timestamp_applied", False)),
            raw_provider_metadata={
                "provider_transaction_id": parsed.get("provider_transaction_id"),
                "profile": parsed.get("profile"),
                "response_code": parsed.get("response_code"),
            },
        )

    def validate_pdf(self, signed_pdf_bytes: bytes, validation_context: dict[str, Any]) -> ValidationResult:
        payload = {
            "pdf_base64": __import__("base64").b64encode(signed_pdf_bytes).decode("utf-8"),
            "validation_context": validation_context,
        }
        status, parsed = self._post_json(self.validate_url, payload)
        if status >= 400:
            raise RuntimeError(parsed.get("error") or "external provider validation failed")
        st = parsed.get("signing_time")
        signing_time = datetime.fromisoformat(st) if st else None
        return ValidationResult(
            cryptographically_valid=bool(parsed.get("cryptographically_valid", False)),
            signature_present=bool(parsed.get("signature_present", False)),
            certificate_subject=parsed.get("certificate_subject"),
            certificate_serial=parsed.get("certificate_serial"),
            signing_time=signing_time,
            timestamp_present=bool(parsed.get("timestamp_present", False)),
            timestamp_valid=parsed.get("timestamp_valid"),
            chain_valid=parsed.get("chain_valid"),
            revocation_checked=parsed.get("revocation_checked"),
            validation_summary=parsed.get("validation_summary") or {},
            raw_validation_metadata={
                "provider_transaction_id": parsed.get("provider_transaction_id"),
                "validation_code": parsed.get("validation_code"),
            },
        )

    def healthcheck(self) -> dict[str, Any]:
        try:
            status, parsed = self._post_json(self.validate_url, {"healthcheck": True})
            return {"ok": status < 400, "provider": self.name, "http_status": status, "message": parsed.get("message", "ok")}
        except Exception:
            return {"ok": False, "provider": self.name, "message": "provider unreachable"}
