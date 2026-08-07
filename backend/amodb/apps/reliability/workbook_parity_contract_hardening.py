"""Contract hardening and canonical dataset extensions for workbook parity.

This module is imported before the mapping defaults and statistical router are
constructed. It repairs the recovered contract without rewriting the historical
implementation in place and keeps the additions tenant-scoped through the
existing workbook record model and canonical Reliability events.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import HTTPException
from pydantic import model_validator

from . import models as reliability_models
from . import workbook_parity as wp


class WorkbookDatasetCode(str, Enum):
    AU = "AU"
    AI = "AI"
    FI = "FI"
    PM = "PM"
    OOS = "OOS"
    RM = "RM"
    SM = "SM"
    SR = "SR"
    SB = "SB"
    CS = "CS"
    AS = "AS"
    UR = "UR"
    STRUCTURES = "STRUCTURES"
    RECURRING = "RECURRING"
    ECTM = "ECTM"
    ADD = "ADD"


class DatasetDefinition(wp.DatasetDefinition):
    code: WorkbookDatasetCode


class WorkbookRecordCreate(wp.WorkbookRecordCreate):
    dataset_code: WorkbookDatasetCode


class MappingCreate(wp.MappingCreate):
    dataset_code: WorkbookDatasetCode


class StatisticalAlertRequest(wp.StatisticalAlertRequest):
    dataset_code: WorkbookDatasetCode | None = None

    @model_validator(mode="after")
    def validate_extended_contract(self):
        return super().validate_contract()


def _dataset_code(value: Any) -> WorkbookDatasetCode:
    """Normalise string or cross-module enum values into this contract enum."""
    return WorkbookDatasetCode(getattr(value, "value", value))


def _new_dataset(
    code: WorkbookDatasetCode,
    name: str,
    sheets: list[str],
    description: str,
    event_type: str,
    fields: list[wp.FieldDefinition],
) -> DatasetDefinition:
    return DatasetDefinition(
        code=code,
        name=name,
        workbook_sheet_names=sheets,
        description=description,
        event_type=event_type,
        fields=fields,
    )


def _extend_catalogue() -> None:
    converted: dict[WorkbookDatasetCode, DatasetDefinition] = {}
    for old_code, definition in wp.DATASET_CATALOG.items():
        converted[WorkbookDatasetCode(old_code.value)] = DatasetDefinition.model_validate(definition.model_dump())

    converted[WorkbookDatasetCode.FI] = _new_dataset(
        WorkbookDatasetCode.FI,
        "Flight interruptions",
        ["FI", "FLIGHT INTERRUPTIONS", "INTERRUPTIONS"],
        "Controlled technical-delay, cancellation, return, turnback, diversion, shutdown and aborted-takeoff evidence with retained rate numerators and denominators.",
        "TECHNICAL_DELAY",
        [
            wp._field("reporting_period", "Reporting period", "date", required=True),
            wp._field("occurred_at", "Interruption date and time", "datetime"),
            wp._field("interruption_type", "Interruption type", "select", required=True, options=["TECHNICAL_DELAY", "TECHNICAL_CANCELLATION", "RETURN_TO_GATE", "AIR_TURNBACK", "DIVERSION", "IN_FLIGHT_SHUTDOWN", "ABORTED_TAKEOFF"]),
            wp._field("departures", "Departures", "integer", required=True),
            wp._field("technical_delays", "Technical delays", "integer"),
            wp._field("delay_minutes", "Technical delay duration", "integer", unit="min"),
            wp._field("technical_cancellations", "Technical cancellations", "integer"),
            wp._field("return_to_gate", "Returns to gate", "integer"),
            wp._field("air_turnback", "Air turnbacks", "integer"),
            wp._field("diversion", "Diversions", "integer"),
            wp._field("in_flight_shutdown", "In-flight shutdowns", "integer"),
            wp._field("aborted_takeoff", "Aborted takeoffs", "integer"),
            wp._field("dispatch_successes", "Successful technical dispatches", "integer"),
            wp._field("scheduled_departures", "Scheduled departures", "integer"),
            wp._field("completed_departures", "Completed departures", "integer"),
            wp._field("ata_interruptions", "ATA interruption numerator", "integer"),
            wp._field("flight_hours_denominator", "Flight-hour denominator", "decimal", unit="FH"),
            wp._field("station", "Station"),
            wp._field("route", "Route"),
            wp._field("defect_description", "Technical cause / defect", "textarea", required=True),
            wp._field("action_taken", "Corrective action", "textarea"),
        ],
    )
    converted[WorkbookDatasetCode.SR] = _new_dataset(
        WorkbookDatasetCode.SR,
        "Shop reports",
        ["SR", "SHOP REPORTS", "SHOP FINDINGS"],
        "Component shop-visit findings linked to removal evidence, confirmed faults, no-fault-found outcomes, supplier action and release documentation.",
        "SHOP_FINDING",
        [
            wp._field("component_description", "Component description", required=True),
            wp._field("component_part_number", "Part number", required=True),
            wp._field("component_serial_number", "Serial number", required=True),
            wp._field("shop_visit_reference", "Shop visit reference", required=True),
            wp._field("removal_record_number", "Removal linkage"),
            wp._field("induction_date", "Induction date", "date", required=True),
            wp._field("release_date", "Release date", "date"),
            wp._field("confirmed_fault", "Confirmed fault", "boolean"),
            wp._field("no_fault_found", "No fault found", "boolean"),
            wp._field("failure_mode", "Failure mode"),
            wp._field("finding_description", "Shop finding", "textarea", required=True),
            wp._field("root_cause", "Root cause", "textarea"),
            wp._field("corrective_action", "Corrective action", "textarea", required=True),
            wp._field("supplier", "Supplier / repair agency", required=True),
            wp._field("warranty", "Warranty applicable", "boolean"),
            wp._field("cost", "Controlled cost", "decimal"),
            wp._field("release_document_reference", "Release-document reference", required=True),
        ],
    )
    converted[WorkbookDatasetCode.ADD] = _new_dataset(
        WorkbookDatasetCode.ADD,
        "Deferred defects / MEL / CDL",
        ["ADD", "DEFERRED DEFECTS", "MEL CDL", "MEL/CDL"],
        "Controlled MEL/CDL deferrals, limits, extensions, repetitive relationships, rectification and approval evidence linked to canonical deferral events.",
        "MEL_DEFERRAL",
        [
            wp._field("deferral_type", "Deferral type", "select", required=True, options=["MEL", "CDL"]),
            wp._field("tech_log_reference", "Technical-log reference", required=True),
            wp._field("defect_description", "Deferred defect", "textarea", required=True),
            wp._field("occurrence_date", "Occurrence date", "date", required=True),
            wp._field("mel_cdl_reference", "MEL / CDL reference", required=True),
            wp._field("category", "Category", required=True),
            wp._field("limit_value", "Calendar / unit limit", "decimal"),
            wp._field("limit_unit", "Limit unit", "select", options=["DAYS", "HOURS", "CYCLES", "SECTORS", "CALENDAR"]),
            wp._field("expiry_date", "Expiry date", "date"),
            wp._field("transfer_log_reference", "Transfer-log reference"),
            wp._field("rectification_date", "Rectification date", "date"),
            wp._field("status", "Deferral status", "select", required=True, options=["OPEN", "EXTENDED", "RECTIFIED", "CLOSED", "EXPIRED"]),
            wp._field("remarks", "Remarks", "textarea"),
            wp._field("extension_history", "Extension history", "textarea"),
            wp._field("repetitive_defect_key", "Repetitive-defect relationship"),
            wp._field("approval_reference", "Approval evidence"),
            wp._field("closure_reference", "Closure evidence"),
        ],
    )

    for field in converted[WorkbookDatasetCode.RM].fields:
        if field.key == "reason_code":
            field.required = False
            break
    else:
        raise RuntimeError("Reliability RM reason_code field is missing from the catalogue")

    wp.DATASET_CATALOG = converted


def _extend_models() -> None:
    wp.WorkbookDatasetCode = WorkbookDatasetCode
    wp.DatasetDefinition = DatasetDefinition
    wp.WorkbookRecordCreate = WorkbookRecordCreate
    wp.MappingCreate = MappingCreate
    wp.StatisticalAlertRequest = StatisticalAlertRequest
    DatasetDefinition.model_rebuild(force=True)
    WorkbookRecordCreate.model_rebuild(force=True)
    MappingCreate.model_rebuild(force=True)
    StatisticalAlertRequest.model_rebuild(force=True)


def _extend_normalisation() -> None:
    original = wp._normalise_payload

    def normalise(dataset: DatasetDefinition, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        normalised, derived = original(dataset, payload)
        code = _dataset_code(dataset.code)
        if code == WorkbookDatasetCode.FI:
            departures = Decimal(str(normalised.get("departures") or 0))
            dispatch_successes = normalised.get("dispatch_successes")
            scheduled_departures = normalised.get("scheduled_departures")
            completed_departures = normalised.get("completed_departures")
            ata_interruptions = normalised.get("ata_interruptions")
            flight_hours = normalised.get("flight_hours_denominator")
            if dispatch_successes not in (None, ""):
                successes = Decimal(str(dispatch_successes))
                if departures <= 0:
                    derived["dispatch_reliability_pct"] = None
                    derived["dispatch_reliability_withheld_reason"] = "Departures denominator is missing or zero."
                elif successes > departures:
                    raise HTTPException(status_code=422, detail="Successful technical dispatches cannot exceed departures.")
                else:
                    derived["dispatch_reliability_pct"] = format((successes / departures * Decimal("100")).quantize(Decimal("0.001")), "f")
                    derived["dispatch_reliability_numerator"] = int(successes)
                    derived["dispatch_reliability_denominator"] = int(departures)
            if completed_departures not in (None, ""):
                scheduled = Decimal(str(scheduled_departures or 0))
                completed = Decimal(str(completed_departures))
                if scheduled <= 0:
                    derived["schedule_completion_pct"] = None
                    derived["schedule_completion_withheld_reason"] = "Scheduled departures denominator is missing or zero."
                elif completed > scheduled:
                    raise HTTPException(status_code=422, detail="Completed departures cannot exceed scheduled departures.")
                else:
                    derived["schedule_completion_pct"] = format((completed / scheduled * Decimal("100")).quantize(Decimal("0.001")), "f")
                    derived["schedule_completion_numerator"] = int(completed)
                    derived["schedule_completion_denominator"] = int(scheduled)
            if ata_interruptions not in (None, ""):
                exposure = Decimal(str(flight_hours or 0))
                numerator = Decimal(str(ata_interruptions))
                if exposure <= 0:
                    derived["ata_interruption_rate_per_100_fh"] = None
                    derived["ata_interruption_rate_withheld_reason"] = "Flight-hour denominator is missing or zero."
                else:
                    derived["ata_interruption_rate_per_100_fh"] = format((numerator / exposure * Decimal("100")).quantize(Decimal("0.001")), "f")
                    derived["ata_interruption_rate_numerator"] = int(numerator)
                    derived["ata_interruption_rate_denominator_fh"] = format(exposure, "f")
        elif code == WorkbookDatasetCode.SR:
            induction = date.fromisoformat(normalised["induction_date"])
            release_raw = normalised.get("release_date")
            if release_raw:
                release = date.fromisoformat(release_raw)
                if release < induction:
                    raise HTTPException(status_code=422, detail="Shop release date cannot precede induction date.")
                derived["shop_turnaround_days"] = (release - induction).days
            if normalised.get("confirmed_fault") and normalised.get("no_fault_found"):
                raise HTTPException(status_code=422, detail="A shop report cannot be both a confirmed fault and no-fault-found.")
        elif code == WorkbookDatasetCode.ADD:
            occurred = date.fromisoformat(normalised["occurrence_date"])
            rectification_raw = normalised.get("rectification_date")
            expiry_raw = normalised.get("expiry_date")
            if expiry_raw and date.fromisoformat(expiry_raw) < occurred:
                raise HTTPException(status_code=422, detail="Deferral expiry cannot precede the occurrence date.")
            if rectification_raw:
                rectified = date.fromisoformat(rectification_raw)
                if rectified < occurred:
                    raise HTTPException(status_code=422, detail="Rectification date cannot precede the occurrence date.")
                derived["closure_duration_days"] = (rectified - occurred).days
        return normalised, derived

    wp._normalise_payload = normalise


def _extend_canonical_mapping() -> None:
    original = wp._event_type_for

    def event_type_for(record: wp.ReliabilityWorkbookRecord):
        code = _dataset_code(record.dataset_code)
        if code == WorkbookDatasetCode.FI:
            mapping = {
                "TECHNICAL_DELAY": reliability_models.ReliabilityEventTypeEnum.TECHNICAL_DELAY,
                "TECHNICAL_CANCELLATION": reliability_models.ReliabilityEventTypeEnum.TECHNICAL_CANCELLATION,
                "RETURN_TO_GATE": reliability_models.ReliabilityEventTypeEnum.RETURN_TO_GATE,
                "AIR_TURNBACK": reliability_models.ReliabilityEventTypeEnum.AIR_TURNBACK,
                "DIVERSION": reliability_models.ReliabilityEventTypeEnum.DIVERSION,
                "IN_FLIGHT_SHUTDOWN": reliability_models.ReliabilityEventTypeEnum.IN_FLIGHT_SHUTDOWN,
                "ABORTED_TAKEOFF": reliability_models.ReliabilityEventTypeEnum.ABORTED_TAKEOFF,
            }
            return mapping[str(record.payload.get("interruption_type") or "TECHNICAL_DELAY")]
        if code == WorkbookDatasetCode.SR:
            return reliability_models.ReliabilityEventTypeEnum.NO_FAULT_FOUND if record.payload.get("no_fault_found") else reliability_models.ReliabilityEventTypeEnum.SHOP_FINDING
        if code == WorkbookDatasetCode.ADD:
            return reliability_models.ReliabilityEventTypeEnum.CDL_DEFERRAL if record.payload.get("deferral_type") == "CDL" else reliability_models.ReliabilityEventTypeEnum.MEL_DEFERRAL
        return original(record)

    wp._event_type_for = event_type_for


def _extend_layouts() -> None:
    required_sections = {
        "FI": {"code": "FI", "title": "Flight interruptions", "kind": "DATASET", "dataset_code": "FI"},
        "SR": {"code": "SR", "title": "Shop reports", "kind": "DATASET", "dataset_code": "SR"},
        "ADD": {"code": "ADD", "title": "Deferred defects / MEL / CDL", "kind": "DATASET", "dataset_code": "ADD"},
    }
    for layout in wp.DEFAULT_LAYOUTS:
        if layout["code"] == "OPERATOR-RP":
            layout["sections"] = [
                {"code": code.value, "title": definition.name, "kind": "DATASET", "dataset_code": code.value}
                for code, definition in wp.DATASET_CATALOG.items()
            ] + [{"code": "ALERTS", "title": "Statistical alert calculations", "kind": "STATISTICAL_ALERTS"}]
            continue
        existing = {str(section.get("dataset_code")) for section in layout["sections"] if section.get("kind") == "DATASET"}
        alert_index = next((index for index, section in enumerate(layout["sections"]) if section.get("kind") == "STATISTICAL_ALERTS"), len(layout["sections"]))
        for code, definition in required_sections.items():
            if code not in existing:
                layout["sections"].insert(alert_index, dict(definition))
                alert_index += 1


def apply() -> None:
    _extend_models()
    _extend_catalogue()
    _extend_normalisation()
    _extend_canonical_mapping()
    _extend_layouts()


apply()
