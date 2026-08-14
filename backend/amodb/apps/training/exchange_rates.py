"""Cached, attributable exchange-rate quotes for governed training budgets."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


DEFAULT_PROVIDER_URL = "https://open.er-api.com/v6/latest/{base}"
PROVIDER_NAME = "ExchangeRate-API open access"
ATTRIBUTION_URL = "https://www.exchangerate-api.com"
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


class ExchangeRateUnavailable(RuntimeError):
    pass


def _currency(value: str) -> str:
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError("Currency codes must be three ISO letters.")
    return code


def _cache_seconds() -> int:
    try:
        return max(300, min(86_400, int(os.getenv("TRAINING_FX_CACHE_SECONDS", "3600"))))
    except ValueError:
        return 3600


def get_exchange_rate_quote(base: str, quote: str) -> dict[str, Any]:
    base_code = _currency(base)
    quote_code = _currency(quote)
    now = datetime.now(timezone.utc)
    if base_code == quote_code:
        return {
            "base_currency": base_code,
            "quote_currency": quote_code,
            "rate": Decimal("1"),
            "rate_date": now.date(),
            "quoted_at": now,
            "next_update_at": None,
            "provider": "Identity rate",
            "source_url": None,
            "attribution_url": None,
            "cached": True,
        }

    cache_key = base_code
    cached = None
    served_from_cache = False
    with _CACHE_LOCK:
        entry = _CACHE.get(cache_key)
        if entry and entry[0] > time.time():
            cached = entry[1]
            served_from_cache = True

    if cached is None:
        template = os.getenv("TRAINING_FX_PROVIDER_URL", DEFAULT_PROVIDER_URL)
        url = template.format(base=base_code)
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AMO-Training-OS/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:  # nosec B310 - URL is administrator configuration
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise ExchangeRateUnavailable(f"The configured exchange-rate provider could not be reached: {exc}") from exc
        if str(payload.get("result") or "success").lower() != "success" or not isinstance(payload.get("rates"), dict):
            detail = payload.get("error-type") or payload.get("error") or "invalid provider response"
            raise ExchangeRateUnavailable(f"The configured exchange-rate provider rejected the quote: {detail}")
        cached = payload
        with _CACHE_LOCK:
            _CACHE[cache_key] = (time.time() + _cache_seconds(), payload)

    raw_rate = cached.get("rates", {}).get(quote_code)
    try:
        rate = Decimal(str(raw_rate))
    except (InvalidOperation, TypeError):
        raise ExchangeRateUnavailable(f"The provider does not publish a {base_code}/{quote_code} rate.")
    if rate <= 0:
        raise ExchangeRateUnavailable(f"The provider returned an invalid {base_code}/{quote_code} rate.")

    update_unix = cached.get("time_last_update_unix")
    next_update_unix = cached.get("time_next_update_unix")
    quoted_at = datetime.fromtimestamp(int(update_unix), tz=timezone.utc) if update_unix else now
    next_update_at = datetime.fromtimestamp(int(next_update_unix), tz=timezone.utc) if next_update_unix else None
    return {
        "base_currency": base_code,
        "quote_currency": quote_code,
        "rate": rate,
        "rate_date": quoted_at.date(),
        "quoted_at": quoted_at,
        "next_update_at": next_update_at,
        "provider": PROVIDER_NAME,
        "source_url": os.getenv("TRAINING_FX_PROVIDER_URL", DEFAULT_PROVIDER_URL).format(base=base_code),
        "attribution_url": ATTRIBUTION_URL,
        "cached": served_from_cache,
    }
