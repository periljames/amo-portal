from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from openpyxl import Workbook

from amodb.apps.reliability import workbook_parity
from amodb.apps.reliability import workbook_parity_imports


def test_import_filename_is_sanitized_and_path_components_are_removed():
    assert workbook_parity_imports._sanitize_filename("../../208B RELIABILITY PROGRAMME(1).xlsm") == "208B_RELIABILITY_PROGRAMME_1_.xlsm"
    assert workbook_parity_imports._sanitize_filename("   ") == "workbook.xlsx"


def test_header_matching_is_explicit_and_rejects_ambiguous_columns():
    aliases = {
        "event_date": {"DATE"},
        "occurrence_date": {"DATE", "OCCURRENCE DATE"},
        "aircraft_serial_number": {"AIRCRAFT"},
    }
    mapping, errors = workbook_parity_imports._match_headers(["DATE", "AIRCRAFT"], aliases)
    assert mapping == {"2": "aircraft_serial_number"}
    assert errors == ["Column 1 'DATE' is ambiguous: event_date, occurrence_date."]


def test_preview_row_retains_exact_decimal_and_formula_errors():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.FI]
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([date(2026, 8, 1), "5Y-SLK", "TECHNICAL_DELAY", 100, 98, "240.500", "Starter-generator interruption", "=1+1"])
    cells = tuple(sheet[1])
    header_map = {
        "1": "event_date",
        "2": "aircraft_serial_number",
        "3": "interruption_type",
        "4": "departures",
        "5": "dispatch_successes",
        "6": "flight_hours_denominator",
        "7": "defect_description",
        "8": "action_taken",
    }
    raw, mapped, errors, row_hash = workbook_parity_imports._build_preview_row(
        workbook_parity.WorkbookDatasetCode.FI,
        definition,
        2,
        cells,
        header_map,
        "a" * 64,
        "FI",
    )
    assert raw["6"] == "240.500"
    assert mapped["event_date"] == "2026-08-01"
    assert mapped["payload"]["flight_hours_denominator"] == "240.500"
    assert any("formula" in error.lower() for error in errors)
    assert len(row_hash) == 64


def test_preview_row_reports_missing_controlled_fields_without_coercion():
    definition = workbook_parity.DATASET_CATALOG[workbook_parity.WorkbookDatasetCode.ADD]
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["not-a-date", "5Y-SLK", "MEL", "TL-1", "Weather radar inoperative", "MEL 34-41-01", "C", "OPEN"])
    cells = tuple(sheet[1])
    header_map = {
        "1": "event_date",
        "2": "aircraft_serial_number",
        "3": "deferral_type",
        "4": "tech_log_reference",
        "5": "defect_description",
        "6": "mel_cdl_reference",
        "7": "category",
        "8": "status",
    }
    _, mapped, errors, _ = workbook_parity_imports._build_preview_row(
        workbook_parity.WorkbookDatasetCode.ADD,
        definition,
        2,
        cells,
        header_map,
        "b" * 64,
        "ADD",
    )
    assert mapped["event_date"] is None
    assert any("Event Date must be an ISO date" in error for error in errors)
    assert any("Event Date is required" in error for error in errors)
    assert any("Occurrence date is required" in error for error in errors)


def test_import_router_exposes_preview_progress_commit_and_retry():
    router = APIRouter(prefix="/reliability")
    workbook_parity_imports.register(router)
    paths = {route.path for route in router.routes}
    assert {
        "/reliability/workbook-parity/imports/preview",
        "/reliability/workbook-parity/imports",
        "/reliability/workbook-parity/imports/{batch_id}",
        "/reliability/workbook-parity/imports/{batch_id}/commit",
        "/reliability/workbook-parity/imports/{batch_id}/retry",
    } <= paths
