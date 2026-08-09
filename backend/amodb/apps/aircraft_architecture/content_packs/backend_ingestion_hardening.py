from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import backend_ingestion


_INSTALLED = False
_ORIGINAL_NORMALIZE = None


def _contains_formula(value: Any) -> bool:
    if isinstance(value, str):
        return value.lstrip().startswith("=")
    if isinstance(value, dict):
        return any(_contains_formula(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_formula(item) for item in value)
    return False


def normalize_oem_workbook(**kwargs):
    preview, candidates = _ORIGINAL_NORMALIZE(**kwargs)
    hardened = []
    for candidate in candidates:
        if candidate.row_kind not in {"TASK", "RESOURCE"} or not _contains_formula(
            candidate.source_json
        ):
            hardened.append(candidate)
            continue
        issues = list(candidate.issues)
        issues.append(
            {
                "code": "FORMULA_REVIEW_REQUIRED",
                "message": (
                    "Controlled OEM engineering content contains a workbook formula. "
                    "The formula is retained as source evidence but cannot become an "
                    "authoritative maintenance value without engineering reconciliation."
                ),
            }
        )
        hardened.append(
            replace(
                candidate,
                status="REVIEW_REQUIRED",
                issues=issues,
            )
        )
    return preview, hardened


def install() -> None:
    global _INSTALLED, _ORIGINAL_NORMALIZE
    if _INSTALLED:
        return
    _ORIGINAL_NORMALIZE = backend_ingestion.normalize_oem_workbook
    backend_ingestion.normalize_oem_workbook = normalize_oem_workbook
    _INSTALLED = True
