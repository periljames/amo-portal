# backend/amodb/apps/crs/validation.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..fleet import models as fleet_models
from ..work import models as work_models
from ..accounts import services as accounts_services, models as accounts_models
from . import schemas as crs_schemas


@dataclass
class CRSValidationResult:
    """
    Internal result object used by the validator.

    The API layer will convert this into a HTTP response payload or
    embed it in a CRSPrefill/diagnostics response.
    """
    can_issue: bool
    blockers: List[str]
    warnings: List[str]


def _find_aircraft(
    db: Session,
    work_order: work_models.WorkOrder,
) -> Optional[fleet_models.Aircraft]:
    if not work_order.aircraft_serial_number:
        return None
    return db.query(fleet_models.Aircraft).get(work_order.aircraft_serial_number)


def _check_aircraft_basic(
    ac: Optional[fleet_models.Aircraft],
    work_order: work_models.WorkOrder,
) -> CRSValidationResult:
    blockers: List[str] = []
    warnings: List[str] = []

    if ac is None:
        blockers.append(
            f"Aircraft with serial '{work_order.aircraft_serial_number}' "
            f"referenced by work order {work_order.wo_number} does not exist in the fleet master."
        )
        return CRSValidationResult(can_issue=False, blockers=blockers, warnings=warnings)

    if not ac.is_active:
        blockers.append(
            f"Aircraft {ac.registration} is marked inactive; "
            f"CRS cannot be issued against an inactive aircraft."
        )

    if not ac.registration:
        blockers.append(
            f"Aircraft with serial {ac.serial_number} has no registration recorded."
        )

    if not ac.template and not ac.make:
        warnings.append(
            f"Aircraft {ac.registration} has no type/template defined; "
            f"CRS will not be able to show aircraft type cleanly."
        )

    return CRSValidationResult(
        can_issue=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
    )


def _check_components_for_engines(
    ac: fleet_models.Aircraft,
) -> CRSValidationResult:
    """
    Sanity check that the aircraft has at least an engine configuration loaded.

    This does *not* try to be clever about exact engine count per type.
    It simply enforces that for any check type which would normally touch
    the whole aircraft, we have some engine data on record.
    """
    blockers: List[str] = []
    warnings: List[str] = []

    engines = [
        comp
        for comp in ac.components
        if comp.position and "ENGINE" in comp.position.upper()
    ]

    if not engines:
        blockers.append(
            f"No engine components found for aircraft {ac.registration} "
            f"({ac.serial_number}). At least one engine record must exist "
            f"before a CRS can be issued."
        )
        return CRSValidationResult(
            can_issue=False,
            blockers=blockers,
            warnings=warnings,
        )

    # If only one engine but the position suggests LH/RH mix, warn
    positions = {comp.position.upper().strip() for comp in engines}
    if len(engines) == 1 and any(p.startswith(("LH", "RH")) for p in positions):
        warnings.append(
            f"Only one engine component present for aircraft {ac.registration}, "
            f"but position naming suggests multi-engine configuration. "
            f"Please confirm component data."
        )

    return CRSValidationResult(
        can_issue=True,
        blockers=blockers,
        warnings=warnings,
    )


def _check_user_authorisation(
    db: Session,
    current_user: accounts_models.User,
    issue_date: date,
) -> CRSValidationResult:
    blockers: List[str] = []
    warnings: List[str] = []

    try:
        auth = accounts_services.get_valid_authorisation_for_user_and_date(
            db=db,
            user_id=current_user.id,
            on_date=issue_date,
        )
    except accounts_services.NoValidAuthorisationError:
        blockers.append(
            "The current user has no valid authorisation for the selected CRS issue date."
        )
        return CRSValidationResult(
            can_issue=False,
            blockers=blockers,
            warnings=warnings,
        )

    # You can refine this: check auth covers specific aircraft category, etc.
    # For now we just warn if licence number is missing.
    if not current_user.licence_number:
        warnings.append(
            "User has a valid internal authorisation but no licence number recorded; "
            "please ensure licensing data is up to date."
        )

    return CRSValidationResult(
        can_issue=True,
        blockers=blockers,
        warnings=warnings,
    )


def _find_overdue_mandatory_ads_sbs(
    db: Session,
    aircraft_serial_number: str,
) -> List[fleet_models.MaintenanceStatus]:
    """
    Use MaintenanceStatus + MaintenanceProgramItem to find any mandatory
    AD/SB items that are overdue (remaining < 0 in hours/cycles/days).

    We rely on Planning logic to keep remaining_* up to date.
    """
    q = (
        db.query(fleet_models.MaintenanceStatus)
        .join(
            fleet_models.MaintenanceProgramItem,
            fleet_models.MaintenanceStatus.program_item_id
            == fleet_models.MaintenanceProgramItem.id,
        )
        .filter(
            fleet_models.MaintenanceStatus.aircraft_serial_number
            == aircraft_serial_number,
            fleet_models.MaintenanceProgramItem.is_mandatory.is_(True),
            fleet_models.MaintenanceProgramItem.category.in_(
                [
                    fleet_models.MaintenanceProgramCategoryEnum.AD,
                    fleet_models.MaintenanceProgramCategoryEnum.SB,
                ]
            ),
            or_(
                fleet_models.MaintenanceStatus.remaining_hours < 0,
                fleet_models.MaintenanceStatus.remaining_cycles < 0,
                fleet_models.MaintenanceStatus.remaining_days < 0,
            ),
        )
    )
    return q.all()


def _check_overdue_ads_sbs(
    db: Session,
    ac: fleet_models.Aircraft,
) -> CRSValidationResult:
    blockers: List[str] = []
    warnings: List[str] = []

    overdue = _find_overdue_mandatory_ads_sbs(db, ac.serial_number)
    if not overdue:
        return CRSValidationResult(
            can_issue=True,
            blockers=blockers,
            warnings=warnings,
        )

    for status in overdue:
        item = status.program_item  # relationship from MaintenanceStatus
        over_bits: List[str] = []
        if status.remaining_hours is not None and status.remaining_hours < 0:
            over_bits.append(f"{abs(status.remaining_hours):.1f} hours")
        if status.remaining_cycles is not None and status.remaining_cycles < 0:
            over_bits.append(f"{abs(status.remaining_cycles):.0f} cycles")
        if status.remaining_days is not None and status.remaining_days < 0:
            over_bits.append(f"{abs(status.remaining_days):.0f} days")

        over_text = ", ".join(over_bits) if over_bits else "overdue"

        blockers.append(
            f"Mandatory {item.category.value} task "
            f"({item.ata_chapter} / {item.task_code}) "
            f"'{item.description[:60]}...' is {over_text} on aircraft "
            f"{ac.registration}."
        )

    return CRSValidationResult(
        can_issue=False,
        blockers=blockers,
        warnings=warnings,
    )


def _check_work_order_basic(
    wo: work_models.WorkOrder,
) -> CRSValidationResult:
    blockers: List[str] = []
    warnings: List[str] = []

    if not wo.tasks or len(wo.tasks) == 0:
        blockers.append(
            f"Work order {wo.wo_number} has no tasks; at least one "
            f"task must be present before issuing a CRS."
        )

    # If you have statuses like 'OPEN', 'CLOSED', etc., you can enforce here.
    if hasattr(wo, "status"):
        status_value = (wo.status or "").upper()
        if status_value in {"CLOSED", "CANCELLED"}:
            blockers.append(
                f"Work order {wo.wo_number} is in status '{wo.status}'; "
                f"CRS can only be issued for open/in-progress work orders."
            )

    # Only allow certain check types to generate CRS, e.g. 200HR, A, C
    allowed_types = {"200HR", "A", "C"}
    if wo.check_type and wo.check_type.upper() not in allowed_types:
        blockers.append(
            f"Work order {wo.wo_number} has check type '{wo.check_type}', "
            f"which is not configured to generate a CRS."
        )

    return CRSValidationResult(
        can_issue=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
    )


def validate_crs_readiness_for_work_order(
    db: Session,
    wo: work_models.WorkOrder,
    current_user: accounts_models.User,
    issue_date: Optional[date] = None,
) -> CRSValidationResult:
    """
    Main entry point: determines whether a CRS *may* be issued for the
    given work order and user as of `issue_date`.

    It does NOT create anything; it only reports blockers/warnings.
    """
    blockers: List[str] = []
    warnings: List[str] = []

    if issue_date is None:
        issue_date = date.today()

    # 1) Fetch aircraft
    ac = _find_aircraft(db, wo)

    # 2) Aircraft basic checks
    ac_result = _check_aircraft_basic(ac, wo)
    blockers.extend(ac_result.blockers)
    warnings.extend(ac_result.warnings)
    if not ac_result.can_issue:
        return CRSValidationResult(False, blockers, warnings)

    assert ac is not None  # for type checkers

    # 3) Engine/config sanity
    comp_result = _check_components_for_engines(ac)
    blockers.extend(comp_result.blockers)
    warnings.extend(comp_result.warnings)
    if not comp_result.can_issue:
        return CRSValidationResult(False, blockers, warnings)

    # 4) User authorisation
    auth_result = _check_user_authorisation(db, current_user, issue_date)
    blockers.extend(auth_result.blockers)
    warnings.extend(auth_result.warnings)
    if not auth_result.can_issue:
        return CRSValidationResult(False, blockers, warnings)

    # 5) Work order basic checks
    wo_result = _check_work_order_basic(wo)
    blockers.extend(wo_result.blockers)
    warnings.extend(wo_result.warnings)
    if not wo_result.can_issue:
        return CRSValidationResult(False, blockers, warnings)

    # 6) Overdue mandatory ADs / SBs
    ad_result = _check_overdue_ads_sbs(db, ac)
    blockers.extend(ad_result.blockers)
    warnings.extend(ad_result.warnings)
    if not ad_result.can_issue:
        return CRSValidationResult(False, blockers, warnings)

    # If we got here, no blockers
    return CRSValidationResult(True, blockers, warnings)
