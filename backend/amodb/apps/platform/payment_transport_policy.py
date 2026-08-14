"""Shared hosted-payment transport safety helpers.

The provider adapters remain authoritative for network calls. This module keeps a
small stable policy surface for callback/redirect validation and durable M-PESA
callback minimization without retaining phone or full provider callback payloads.
"""
from __future__ import annotations

from typing import Any

from .commercial_integrations import _require_secure_callback, _trusted_hosted_redirect


def minimized_mpesa_callback(
    payload: dict[str, Any],
    *,
    invoice_id: str | None = None,
) -> dict[str, Any]:
    body = payload.get("Body") if isinstance(payload, dict) else None
    callback = body.get("stkCallback") if isinstance(body, dict) else None
    callback = callback if isinstance(callback, dict) else {}

    checkout_request_id = str(callback.get("CheckoutRequestID") or "").strip()
    result_code = int(callback.get("ResultCode") or 0)
    result_desc = str(callback.get("ResultDesc") or "").strip()
    receipt: str | None = None
    amount_kes: int | float | None = None

    metadata = callback.get("CallbackMetadata")
    items = metadata.get("Item") if isinstance(metadata, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "")
        if name == "Amount":
            amount_kes = item.get("Value")
        elif name == "MpesaReceiptNumber":
            receipt = str(item.get("Value") or "").strip() or None

    return {
        "invoice_id": invoice_id,
        "checkout_request_id": checkout_request_id,
        "result_code": result_code,
        "result_desc": result_desc,
        "amount_kes": amount_kes,
        "receipt_number": receipt,
        "data_minimized": True,
    }


__all__ = [
    "_require_secure_callback",
    "_trusted_hosted_redirect",
    "minimized_mpesa_callback",
]
