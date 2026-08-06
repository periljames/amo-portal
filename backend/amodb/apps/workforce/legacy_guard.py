"""Strict guard for the former tenant-wide default-pattern bootstrap."""
from __future__ import annotations

import os
from functools import wraps


def install_legacy_default_pattern_guard(hr_service_module) -> None:
    original = hr_service_module.bootstrap_default_day_pattern
    if getattr(original, "_workforce_legacy_guard", False):
        return

    @wraps(original)
    def guarded(*args, **kwargs):
        if os.getenv("WORKFORCE_ALLOW_LEGACY_TENANT_PATTERN_BOOTSTRAP", "0") != "1":
            raise ValueError(
                "The tenant-wide default-pattern operation is disabled. Preview an explicit or filtered personnel selection and submit the durable default-pattern bulk operation instead."
            )
        return original(*args, **kwargs)

    guarded._workforce_legacy_guard = True
    hr_service_module.bootstrap_default_day_pattern = guarded
