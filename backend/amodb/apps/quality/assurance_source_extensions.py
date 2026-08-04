from __future__ import annotations

from .assurance_wiring_router import SOURCE_ALIASES, SOURCE_REGISTRY, SourceSpec


# These governed records participate in the readiness model and must also be
# available as first-class evidence, not dashboard-only counts.
SOURCE_REGISTRY.setdefault(
    "OUT_OF_TOLERANCE",
    SourceSpec(
        source_type="OUT_OF_TOLERANCE",
        label="Out-of-tolerance event",
        table="qms_out_of_tolerance_events",
        identity_fields=("id", "reference"),
        label_fields=("reference", "title", "description", "equipment_id"),
        valid_until_fields=("due_date",),
        route_template="/maintenance/{amo_code}/quality/equipment-calibration/out-of-tolerance?event_id={id}",
        description="Calibration out-of-tolerance impact assessment, affected work and corrective follow-up.",
    ),
)

SOURCE_ALIASES.update(
    {
        "OOT": "OUT_OF_TOLERANCE",
        "OUT_OF_TOLERANCE_EVENT": "OUT_OF_TOLERANCE",
        "QUALITY_REPORT": "REPORT",
        "REPORT_EXPORT": "REPORT",
    }
)
