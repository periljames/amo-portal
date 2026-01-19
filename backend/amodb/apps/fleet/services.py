from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models


HOURS_BASED_FIELDS: tuple[str, ...] = (
    "ttesn_after",
    "ttsoh_after",
    "ttshsi_after",
    "pttsn_after",
    "pttso_after",
    "tscoa_after",
)

CYCLES_BASED_FIELDS: tuple[str, ...] = ("tcesn_after", "tcsoh_after")


@dataclass
class DocumentEvaluation:
    status: models.AircraftDocumentStatus
    is_blocking: bool
    days_to_expiry: Optional[int]
    override_active: bool
    missing_evidence: bool


def _is_override_active(doc: models.AircraftDocument, today: date) -> bool:
    if not doc.override_reason or not doc.override_by_user_id:
        return False
    if doc.override_expires_on is None:
        return True
    return doc.override_expires_on >= today


def evaluate_document(doc: models.AircraftDocument, today: Optional[date] = None) -> DocumentEvaluation:
    """
    Compute the effective status for a document and whether it blocks maintenance.

    Rules (aligned with KCARs / KCAA, FAA and EASA expectations):
    - Missing evidence (no stored file) is treated as OVERDUE / blocking.
    - Documents due within alert_window_days are DUE_SOON and block work until renewed.
    - Expired documents are OVERDUE.
    - Quality overrides (with reason) mark the document OVERRIDDEN and clear the block
      until the override expires (if an expiry date is set).
    """
    today = today or date.today()
    override_active = _is_override_active(doc, today)
    missing_evidence = not doc.file_storage_path and not doc.file_original_name

    days_to_expiry: Optional[int] = None
    if doc.expires_on:
        days_to_expiry = (doc.expires_on - today).days

    status = models.AircraftDocumentStatus.CURRENT
    if override_active:
        status = models.AircraftDocumentStatus.OVERRIDDEN
    else:
        if missing_evidence:
            status = models.AircraftDocumentStatus.OVERDUE
        if doc.expires_on:
            if doc.expires_on < today:
                status = models.AircraftDocumentStatus.OVERDUE
            elif doc.expires_on <= today + timedelta(days=doc.alert_window_days or 0):
                status = models.AircraftDocumentStatus.DUE_SOON

    is_blocking = status in {
        models.AircraftDocumentStatus.DUE_SOON,
        models.AircraftDocumentStatus.OVERDUE,
    }
    return DocumentEvaluation(
        status=status,
        is_blocking=is_blocking,
        days_to_expiry=days_to_expiry,
        override_active=override_active,
        missing_evidence=missing_evidence,
    )


def refresh_document_status(doc: models.AircraftDocument, today: Optional[date] = None) -> DocumentEvaluation:
    """
    Recompute and update the stored status for a document (without committing).
    """
    evaluation = evaluate_document(doc, today=today)
    if doc.status != evaluation.status:
        doc.status = evaluation.status
    return evaluation


def collect_document_alerts(
    db: Session,
    *,
    due_within_days: int = 30,
) -> List[dict]:
    """
    Return documents that are due soon or overdue to drive department notifications.
    """
    today = date.today()
    alerts: List[dict] = []
    docs: Iterable[models.AircraftDocument] = (
        db.query(models.AircraftDocument)
        .order_by(models.AircraftDocument.expires_on.asc().nullslast())
        .all()
    )

    for doc in docs:
        evaluation = evaluate_document(doc, today=today)
        if evaluation.status == models.AircraftDocumentStatus.CURRENT:
            if evaluation.days_to_expiry is not None and evaluation.days_to_expiry <= due_within_days:
                evaluation = DocumentEvaluation(
                    status=models.AircraftDocumentStatus.DUE_SOON,
                    is_blocking=True,
                    days_to_expiry=evaluation.days_to_expiry,
                    override_active=evaluation.override_active,
                    missing_evidence=evaluation.missing_evidence,
                )
        if evaluation.status in {
            models.AircraftDocumentStatus.DUE_SOON,
            models.AircraftDocumentStatus.OVERDUE,
        }:
            alerts.append(
                {
                    "id": doc.id,
                    "aircraft_serial_number": doc.aircraft_serial_number,
                    "document_type": doc.document_type,
                    "authority": doc.authority,
                    "status": evaluation.status,
                    "expires_on": doc.expires_on,
                    "days_to_expiry": evaluation.days_to_expiry,
                    "override_active": evaluation.override_active,
                    "missing_evidence": evaluation.missing_evidence,
                    "reference_number": doc.reference_number,
                    "title": doc.title,
                }
            )
    return alerts


def build_aircraft_compliance_summary(
    db: Session,
    serial_number: str,
    *,
    due_within_days: int = 30,
) -> dict:
    today = date.today()
    docs: Iterable[models.AircraftDocument] = (
        db.query(models.AircraftDocument)
        .filter(models.AircraftDocument.aircraft_serial_number == serial_number)
        .order_by(models.AircraftDocument.expires_on.asc().nullslast())
        .all()
    )

    summary = {
        "aircraft_serial_number": serial_number,
        "documents_total": len(docs),
        "blocking_documents": [],
        "due_soon_documents": [],
        "overdue_documents": [],
        "overrides": [],
        "documents": [],
    }

    for doc in docs:
        evaluation = refresh_document_status(doc, today=today)
        item = {
            "id": doc.id,
            "document_type": doc.document_type,
            "authority": doc.authority,
            "status": evaluation.status,
            "is_blocking": evaluation.is_blocking,
            "override_active": evaluation.override_active,
            "days_to_expiry": evaluation.days_to_expiry,
            "expires_on": doc.expires_on,
            "issued_on": doc.issued_on,
            "reference_number": doc.reference_number,
            "title": doc.title,
            "missing_evidence": evaluation.missing_evidence,
            "alert_window_days": doc.alert_window_days,
            "compliance_basis": doc.compliance_basis,
            "file_original_name": doc.file_original_name,
            "file_storage_path": doc.file_storage_path,
            "file_content_type": doc.file_content_type,
            "last_uploaded_at": doc.last_uploaded_at,
            "last_uploaded_by_user_id": doc.last_uploaded_by_user_id,
            "override_expires_on": doc.override_expires_on,
            "override_by_user_id": doc.override_by_user_id,
            "override_recorded_at": doc.override_recorded_at,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }
        summary["documents"].append(item)
        if evaluation.is_blocking:
            summary["blocking_documents"].append(item)
        if evaluation.status == models.AircraftDocumentStatus.DUE_SOON:
            summary["due_soon_documents"].append(item)
        if evaluation.status == models.AircraftDocumentStatus.OVERDUE:
            summary["overdue_documents"].append(item)
        if evaluation.override_active:
            summary["overrides"].append(item)
        # If document is still current but within the requested window, surface it as due soon for notification purposes.
        if (
            evaluation.status == models.AircraftDocumentStatus.CURRENT
            and evaluation.days_to_expiry is not None
            and evaluation.days_to_expiry <= due_within_days
        ):
            summary["due_soon_documents"].append(
                {**item, "status": models.AircraftDocumentStatus.DUE_SOON}
            )

    summary["is_blocking"] = len(summary["blocking_documents"]) > 0
    return summary


def get_blocking_documents(
    db: Session,
    serial_number: str,
) -> List[tuple[models.AircraftDocument, DocumentEvaluation]]:
    """
    Return blocking documents for an aircraft (due soon or overdue without a Quality override).
    """
    docs: Iterable[models.AircraftDocument] = (
        db.query(models.AircraftDocument)
        .filter(models.AircraftDocument.aircraft_serial_number == serial_number)
        .all()
    )
    results: List[tuple[models.AircraftDocument, DocumentEvaluation]] = []
    for doc in docs:
        evaluation = evaluate_document(doc)
        if evaluation.is_blocking:
            results.append((doc, evaluation))
    return results


def get_previous_usage(
    db: Session,
    serial_number: str,
    entry_date: date,
) -> models.AircraftUsage | None:
    return (
        db.query(models.AircraftUsage)
        .filter(
            models.AircraftUsage.aircraft_serial_number == serial_number,
            models.AircraftUsage.date < entry_date,
        )
        .order_by(
            models.AircraftUsage.date.desc(),
            models.AircraftUsage.techlog_no.desc(),
        )
        .first()
    )


def _increment_field(
    data: dict,
    previous_value: float | None,
    field: str,
    delta: float,
) -> None:
    if data.get(field) is not None:
        return
    if previous_value is None:
        return
    data[field] = previous_value + delta


def apply_usage_calculations(
    data: dict,
    previous_usage: models.AircraftUsage | None,
) -> None:
    block_hours = data.get("block_hours") or 0
    cycles = data.get("cycles") or 0

    previous_ttaf = previous_usage.ttaf_after if previous_usage else 0
    previous_tca = previous_usage.tca_after if previous_usage else 0

    if data.get("ttaf_after") is None:
        data["ttaf_after"] = (previous_ttaf or 0) + block_hours
    if data.get("tca_after") is None:
        data["tca_after"] = (previous_tca or 0) + cycles

    if previous_usage:
        for field in HOURS_BASED_FIELDS:
            _increment_field(data, getattr(previous_usage, field), field, block_hours)
        for field in CYCLES_BASED_FIELDS:
            _increment_field(data, getattr(previous_usage, field), field, cycles)


def update_maintenance_remaining(
    db: Session,
    serial_number: str,
    entry_date: date,
    data: dict,
) -> None:
    statuses: Iterable[models.MaintenanceStatus] = (
        db.query(models.MaintenanceStatus)
        .filter(models.MaintenanceStatus.aircraft_serial_number == serial_number)
        .all()
    )
    hours_values: list[float] = []
    day_values: list[int] = []

    for status in statuses:
        if status.remaining_hours is not None:
            hours_values.append(status.remaining_hours)
        if status.remaining_days is not None:
            day_values.append(status.remaining_days)
        if status.remaining_days is None and status.next_due_date is not None:
            delta_days = (status.next_due_date - entry_date).days
            day_values.append(delta_days)

    if data.get("hours_to_mx") is None and hours_values:
        data["hours_to_mx"] = min(hours_values)
    if data.get("days_to_mx") is None and day_values:
        data["days_to_mx"] = min(day_values)


def build_usage_summary(
    db: Session,
    serial_number: str,
) -> dict:
    latest_usage = (
        db.query(models.AircraftUsage)
        .filter(models.AircraftUsage.aircraft_serial_number == serial_number)
        .order_by(
            models.AircraftUsage.date.desc(),
            models.AircraftUsage.techlog_no.desc(),
        )
        .first()
    )

    if not latest_usage:
        return {
            "aircraft_serial_number": serial_number,
            "total_hours": None,
            "total_cycles": None,
            "seven_day_daily_average_hours": None,
            "next_due_program_item_id": None,
            "next_due_task_code": None,
            "next_due_date": None,
            "next_due_hours": None,
            "next_due_cycles": None,
        }

    latest_date = latest_usage.date
    range_start = latest_date - timedelta(days=6)

    recent_entries = (
        db.query(models.AircraftUsage)
        .filter(
            models.AircraftUsage.aircraft_serial_number == serial_number,
            models.AircraftUsage.date >= range_start,
            models.AircraftUsage.date <= latest_date,
        )
        .all()
    )
    total_recent_hours = sum(entry.block_hours for entry in recent_entries)
    seven_day_average = total_recent_hours / 7 if recent_entries else None

    statuses: Iterable[models.MaintenanceStatus] = (
        db.query(models.MaintenanceStatus)
        .filter(models.MaintenanceStatus.aircraft_serial_number == serial_number)
        .all()
    )

    next_due_status = None
    next_due_score = None
    for status in statuses:
        if status.next_due_date:
            score = (status.next_due_date, status.next_due_hours or 0, status.next_due_cycles or 0)
        elif status.next_due_hours is not None:
            score = (date.max, status.next_due_hours, status.next_due_cycles or 0)
        elif status.next_due_cycles is not None:
            score = (date.max, float("inf"), status.next_due_cycles)
        else:
            continue
        if next_due_score is None or score < next_due_score:
            next_due_score = score
            next_due_status = status

    next_due_item = next_due_status.program_item if next_due_status else None

    return {
        "aircraft_serial_number": serial_number,
        "total_hours": latest_usage.ttaf_after,
        "total_cycles": latest_usage.tca_after,
        "seven_day_daily_average_hours": seven_day_average,
        "next_due_program_item_id": next_due_status.program_item_id if next_due_status else None,
        "next_due_task_code": next_due_item.task_code if next_due_item else None,
        "next_due_date": next_due_status.next_due_date if next_due_status else None,
        "next_due_hours": next_due_status.next_due_hours if next_due_status else None,
        "next_due_cycles": next_due_status.next_due_cycles if next_due_status else None,
    }
