"""Strict guard for the former tenant-wide default-pattern bootstrap."""
from __future__ import annotations

from functools import wraps


RETIRED_DEFAULT_PATTERN_MESSAGE = (
    "Automatic tenant-wide DAY creation is retired. Create real shift types and "
    "enable an explicit department, position or contract rule on a work pattern."
)


def install_legacy_default_pattern_guard(hr_service_module) -> None:
    original = hr_service_module.bootstrap_default_day_pattern
    if getattr(original, "_workforce_legacy_guard", False):
        return

    @wraps(original)
    def guarded(*args, **kwargs):
        raise ValueError(RETIRED_DEFAULT_PATTERN_MESSAGE)

    guarded._workforce_legacy_guard = True
    hr_service_module.bootstrap_default_day_pattern = guarded
