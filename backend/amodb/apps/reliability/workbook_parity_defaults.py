from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from .workbook_parity import DATASET_CATALOG, DEFAULT_LAYOUTS, ReliabilityWorkbookFieldMapping, WorkbookDatasetCode

WORKBOOK_PROFILES: tuple[dict[str, str], ...] = (
    {"code": "SAFARILINK-C208B-RP", "name": "Safarilink Cessna 208B Reliability Programme", "family": "C208B"},
    {"code": "SAFARILINK-DHC8-RP", "name": "Safarilink DHC8 Reliability Programme", "family": "DHC8"},
    {"code": "GENERIC-ANALYSIS-TEMPLATE", "name": "Generic Reliability Analysis Template", "family": "OPERATOR"},
)

SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "flight_hours": ("A/C HOURS", "AIRCRAFT HOURS", "FH", "BLOCK HOURS"),
    "flight_cycles": ("A/C CYCLES", "AIRCRAFT CYCLES", "FC", "LANDINGS"),
    "source_reference": ("TECH LOG REF", "LOGBOOK REF", "SOURCE"),
    "occurred_at": ("DATE/TIME", "OCCURRENCE DATE", "DATE OF INCIDENT"),
    "incident_number": ("INCIDENT NO", "REPORT NO", "REFERENCE"),
    "logbook_reference": ("TECH LOG SECTOR", "TLB REF", "LOG REF"),
    "defect_description": ("DEFECT", "PIREP", "MAREP", "DESCRIPTION"),
    "action_taken": ("RECTIFICATION", "ACTION", "CORRECTIVE ACTION"),
    "start_at": ("OOS START", "GROUNDING START", "FROM"),
    "end_at": ("OOS END", "RETURN TO SERVICE", "TO"),
    "scheduled_available_hours": ("AVAILABLE HOURS", "SCHEDULED HOURS", "PLANNED AVAILABILITY"),
    "removed_at": ("DATE REMOVED", "REMOVAL DATE", "OFF DATE"),
    "off_part_number": ("OFF P/N", "REMOVED P/N", "PART NUMBER OFF"),
    "off_serial_number": ("OFF S/N", "REMOVED S/N", "SERIAL NUMBER OFF"),
    "on_part_number": ("ON P/N", "INSTALLED P/N", "PART NUMBER ON"),
    "on_serial_number": ("ON S/N", "INSTALLED S/N", "SERIAL NUMBER ON"),
    "hours_at_removal": ("HOURS AT REMOVAL", "TSN HOURS", "COMPONENT HOURS"),
    "cycles_at_removal": ("CYCLES AT REMOVAL", "CSN", "COMPONENT CYCLES"),
    "check_type": ("CHECK", "MAINTENANCE CHECK", "PACKAGE"),
    "workpack_reference": ("WORKPACK", "WORK PACKAGE", "WP REF"),
    "finding_description": ("FINDING", "NON ROUTINE", "DEFECT FOUND"),
    "damage_reference": ("DAMAGE REF", "STRUCTURAL ITEM", "DENT CHART REF"),
    "allowable_limits_reference": ("SRM REF", "ALLOWABLE LIMIT", "APPROVED DATA"),
    "repeat_key": ("RECURRING KEY", "REPEAT DEFECT KEY", "DEFECT GROUP"),
    "occurrence_count": ("NO OF OCCURRENCES", "REPEATS", "COUNT"),
    "engine_position": ("ENG POS", "ENGINE", "POSITION"),
    "engine_serial_number": ("ENG S/N", "ENGINE SERIAL NUMBER", "ESN"),
    "itt_c": ("ITT", "EGT", "T5"),
    "ng_pct": ("NG", "N1", "GAS GENERATOR SPEED"),
    "nh_pct": ("NH", "N2", "HIGH PRESSURE SPEED"),
    "fuel_flow": ("FF", "FUEL FLOW", "FUEL FLOW PPH"),
    "oil_analysis_status": ("SOAP STATUS", "OIL ANALYSIS", "SPECTROMETRIC STATUS"),
    "borescope_status": ("BSI STATUS", "BORESCOPE", "BORESCOPE RESULT"),
    "trend_status": ("TREND", "ECTM STATUS", "ENGINE HEALTH STATUS"),
}


def default_mapping_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile in WORKBOOK_PROFILES:
        for dataset_code, definition in DATASET_CATALOG.items():
            sheet = definition.workbook_sheet_names[0]
            for field in definition.fields:
                aliases = list(dict.fromkeys((field.label, field.key, *SOURCE_ALIASES.get(field.key, ()))))
                rows.append({
                    "profile_code": profile["code"], "profile_name": profile["name"], "workbook_family": profile["family"],
                    "dataset_code": dataset_code.value, "source_sheet": sheet, "source_column": field.label,
                    "canonical_field": field.key, "data_type": field.data_type, "required": field.required, "unit": field.unit,
                    "aliases": aliases,
                    "transform": {"trim": field.data_type in {"text", "textarea", "select"}, "uppercase": field.data_type == "select", "exact_numeric": field.data_type in {"decimal", "integer"}},
                })
    return rows


DEFAULT_MAPPING_ROWS = default_mapping_rows()


def mapping_contract() -> dict[str, Any]:
    expected = {code.value: {field.key for field in definition.fields} for code, definition in DATASET_CATALOG.items()}
    required = {code.value: {field.key for field in definition.fields if field.required} for code, definition in DATASET_CATALOG.items()}
    result: dict[str, Any] = {"profiles": {}, "datasets": {}}
    for profile in WORKBOOK_PROFILES:
        mapped: dict[str, set[str]] = defaultdict(set)
        for row in DEFAULT_MAPPING_ROWS:
            if row["profile_code"] == profile["code"]:
                mapped[row["dataset_code"]].add(row["canonical_field"])
        result["profiles"][profile["code"]] = {
            code: {"mapped_fields": len(mapped[code]), "expected_fields": len(fields), "missing_fields": sorted(fields - mapped[code]), "missing_required_fields": sorted(required[code] - mapped[code]), "coverage_pct": round(len(mapped[code] & fields) / max(len(fields), 1) * 100, 1)}
            for code, fields in expected.items()
        }
    for code, definition in DATASET_CATALOG.items():
        result["datasets"][code.value] = {"name": definition.name, "sheet_names": definition.workbook_sheet_names, "field_count": len(definition.fields), "required_count": sum(field.required for field in definition.fields)}
    return result


def layout_contract() -> dict[str, Any]:
    required = {code.value for code in WorkbookDatasetCode}
    layouts = {}
    for layout in DEFAULT_LAYOUTS:
        datasets = {str(section.get("dataset_code")) for section in layout["sections"] if section.get("kind") == "DATASET"}
        layouts[layout["code"]] = {"datasets": sorted(datasets), "missing_datasets": sorted(required - datasets), "has_statistical_alerts": any(section.get("kind") == "STATISTICAL_ALERTS" for section in layout["sections"])}
    return {"required_datasets": sorted(required), "layouts": layouts}


def _amo_id(user: account_models.User) -> str:
    amo_id = user.effective_amo_id
    if not amo_id:
        raise HTTPException(status_code=403, detail="A tenant context is required.")
    return str(amo_id)


def register(router: APIRouter) -> None:
    @router.post("/workbook-parity/mappings/seed-defaults")
    def seed_default_mappings(current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user)
        existing = {(row.profile_code, row.dataset_code, row.source_sheet, row.source_column): row for row in db.query(ReliabilityWorkbookFieldMapping).filter(ReliabilityWorkbookFieldMapping.amo_id == amo_id).all()}
        created = repaired = 0
        for definition in DEFAULT_MAPPING_ROWS:
            key = (definition["profile_code"], definition["dataset_code"], definition["source_sheet"], definition["source_column"])
            row = existing.get(key)
            if row is None:
                db.add(ReliabilityWorkbookFieldMapping(amo_id=amo_id, created_by_user_id=current_user.id, active=True, **definition)); created += 1; continue
            changed = False
            for field_name, value in definition.items():
                if getattr(row, field_name) != value: setattr(row, field_name, value); changed = True
            if not row.active: row.active = True; changed = True
            repaired += int(changed)
        db.commit()
        return {"profiles": [profile["code"] for profile in WORKBOOK_PROFILES], "expected_rows": len(DEFAULT_MAPPING_ROWS), "created": created, "repaired": repaired, "total_active": db.query(func.count(ReliabilityWorkbookFieldMapping.id)).filter(ReliabilityWorkbookFieldMapping.amo_id == amo_id, ReliabilityWorkbookFieldMapping.active.is_(True)).scalar() or 0, "contract": mapping_contract()}

    @router.get("/workbook-parity/contracts")
    def read_parity_contracts(current_user: account_models.User = Depends(get_current_active_user)):
        _amo_id(current_user)
        return {"mapping": mapping_contract(), "report_layouts": layout_contract()}
