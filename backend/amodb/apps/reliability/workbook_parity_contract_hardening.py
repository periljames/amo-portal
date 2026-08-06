"""Targeted contract corrections for the Reliability workbook-parity catalogue."""
from __future__ import annotations

from .workbook_parity import DATASET_CATALOG, WorkbookDatasetCode


def apply() -> None:
    """Keep scheduled removals valid while enforcing a reason for unscheduled removals.

    The dataset-level validator in ``workbook_parity`` already requires a failure
    mode or reason code when ``removal_type`` is ``UNSCHEDULED``. Marking the
    field globally required incorrectly rejected scheduled removals before that
    conditional rule could run.
    """
    for field in DATASET_CATALOG[WorkbookDatasetCode.RM].fields:
        if field.key == "reason_code":
            field.required = False
            return
    raise RuntimeError("Reliability RM reason_code field is missing from the catalogue")


apply()
