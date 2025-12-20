# backend/amodb/apps/fleet/router.py

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user, require_roles
from amodb.apps.accounts import models as account_models
from . import models, ocr as ocr_service, schemas, services

# Roles allowed to manage aircraft, components, usage
MANAGEMENT_ROLES = [
    "SUPERUSER",
    "AMO_ADMIN",
    "PLANNING_ENGINEER",
    "PRODUCTION_ENGINEER",
]

# Roles allowed to manage maintenance programme template items
PROGRAM_WRITE_ROLES = [
    "SUPERUSER",
    "AMO_ADMIN",
    "PLANNING_ENGINEER",
]

router = APIRouter(
    prefix="/aircraft",
    tags=["aircraft"],
    # Require an authenticated, active user for everything in this router
    dependencies=[Depends(get_current_active_user)],
)

# ---------------------------------------------------------------------------
# BASIC AIRCRAFT CRUD
# ---------------------------------------------------------------------------


@router.get("/", response_model=List[schemas.AircraftRead])
def list_aircraft(
    skip: int = 0,
    limit: int = 100,
    only_active: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(models.Aircraft)
    if only_active:
        query = query.filter(models.Aircraft.is_active.is_(True))
    return (
        query.order_by(models.Aircraft.serial_number.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{serial_number}", response_model=schemas.AircraftRead)
def get_aircraft(serial_number: str, db: Session = Depends(get_db)):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return ac


@router.post(
    "/",
    response_model=schemas.AircraftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_aircraft(
    payload: schemas.AircraftCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    # Check serial_number (AIN-style)
    existing = db.query(models.Aircraft).get(payload.serial_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aircraft with serial {payload.serial_number} already exists.",
        )

    # Extra safety: avoid duplicate registration on a different AIN
    reg_conflict = (
        db.query(models.Aircraft)
        .filter(models.Aircraft.registration == payload.registration)
        .first()
    )
    if reg_conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Registration {payload.registration} is already assigned to "
                f"aircraft {reg_conflict.serial_number}."
            ),
        )

    ac = models.Aircraft(**payload.model_dump())
    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac


@router.put("/{serial_number}", response_model=schemas.AircraftRead)
def update_aircraft(
    serial_number: str,
    payload: schemas.AircraftUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    data = payload.model_dump(exclude_unset=True)

    # If registration is changing, ensure no conflicts
    new_reg = data.get("registration")
    if new_reg and new_reg != ac.registration:
        reg_conflict = (
            db.query(models.Aircraft)
            .filter(
                models.Aircraft.registration == new_reg,
                models.Aircraft.serial_number != serial_number,
            )
            .first()
        )
        if reg_conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Registration {new_reg} is already assigned to "
                    f"aircraft {reg_conflict.serial_number}."
                ),
            )

    for field, value in data.items():
        setattr(ac, field, value)

    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac


@router.delete("/{serial_number}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_aircraft(
    serial_number: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    """
    Soft-delete: mark as inactive instead of dropping the row.
    Keeps history and allows future reactivation.
    """
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    ac.is_active = False
    db.add(ac)
    db.commit()
    return


# ---------------------------------------------------------------------------
# COMPONENTS CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/{serial_number}/components",
    response_model=List[schemas.AircraftComponentRead],
)
def list_components(
    serial_number: str,
    db: Session = Depends(get_db),
):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return ac.components


@router.post(
    "/{serial_number}/components",
    response_model=schemas.AircraftComponentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_component(
    serial_number: str,
    payload: schemas.AircraftComponentCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    data = payload.model_dump(exclude_unset=True)
    # Ensure the component is always attached to the path aircraft
    data["aircraft_serial_number"] = serial_number

    comp = models.AircraftComponent(**data)
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.put(
    "/components/{component_id}",
    response_model=schemas.AircraftComponentRead,
)
def update_component(
    component_id: int,
    payload: schemas.AircraftComponentUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    comp = (
        db.query(models.AircraftComponent)
        .filter(models.AircraftComponent.id == component_id)
        .first()
    )
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(comp, field, value)

    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.delete("/components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_component(
    component_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    comp = (
        db.query(models.AircraftComponent)
        .filter(models.AircraftComponent.id == component_id)
        .first()
    )
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    db.delete(comp)
    db.commit()
    return


# ---------------------------------------------------------------------------
# AIRCRAFT USAGE
# ---------------------------------------------------------------------------


@router.get(
    "/{serial_number}/usage",
    response_model=List[schemas.AircraftUsageRead],
)
def list_usage_entries(
    serial_number: str,
    skip: int = 0,
    limit: int = 100,
    start_date: date | None = None,
    end_date: date | None = None,
    techlog_no: str | None = None,
    db: Session = Depends(get_db),
):
    # Ensure aircraft exists
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    query = db.query(models.AircraftUsage).filter(
        models.AircraftUsage.aircraft_serial_number == serial_number
    )

    if start_date is not None:
        query = query.filter(models.AircraftUsage.date >= start_date)
    if end_date is not None:
        query = query.filter(models.AircraftUsage.date <= end_date)
    if techlog_no is not None:
        query = query.filter(models.AircraftUsage.techlog_no == techlog_no)

    return (
        query.order_by(
            models.AircraftUsage.date.asc(),
            models.AircraftUsage.techlog_no.asc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post(
    "/{serial_number}/usage",
    response_model=schemas.AircraftUsageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_usage_entry(
    serial_number: str,
    payload: schemas.AircraftUsageCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    # Ensure aircraft exists
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    # Uniqueness check: aircraft + date + techlog_no
    existing = (
        db.query(models.AircraftUsage)
        .filter(
            models.AircraftUsage.aircraft_serial_number == serial_number,
            models.AircraftUsage.date == payload.date,
            models.AircraftUsage.techlog_no == payload.techlog_no,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Usage entry for this aircraft, date and techlog already exists.",
        )

    data = payload.model_dump()
    previous_usage = services.get_previous_usage(db, serial_number, payload.date)
    services.apply_usage_calculations(data, previous_usage)
    services.update_maintenance_remaining(db, serial_number, payload.date, data)
    usage = models.AircraftUsage(
        aircraft_serial_number=serial_number,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
        **data,
    )

    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


@router.put(
    "/usage/{usage_id}",
    response_model=schemas.AircraftUsageRead,
)
def update_usage_entry(
    usage_id: int,
    payload: schemas.AircraftUsageUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    usage = (
        db.query(models.AircraftUsage)
        .filter(models.AircraftUsage.id == usage_id)
        .first()
    )
    if not usage:
        raise HTTPException(status_code=404, detail="Usage entry not found")

    # Optimistic concurrency check
    if payload.last_seen_updated_at != usage.updated_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Usage entry has been modified by another user.",
        )

    data = payload.model_dump(
        exclude_unset=True,
        exclude={"last_seen_updated_at"},
    )
    
    effective_date = data.get("date", usage.date)
    merged_data = {
        "date": effective_date,
        "techlog_no": data.get("techlog_no", usage.techlog_no),
        "station": data.get("station", usage.station),
        "block_hours": data.get("block_hours", usage.block_hours),
        "cycles": data.get("cycles", usage.cycles),
        "ttaf_after": data.get("ttaf_after", usage.ttaf_after),
        "tca_after": data.get("tca_after", usage.tca_after),
        "ttesn_after": data.get("ttesn_after", usage.ttesn_after),
        "tcesn_after": data.get("tcesn_after", usage.tcesn_after),
        "ttsoh_after": data.get("ttsoh_after", usage.ttsoh_after),
        "ttshsi_after": data.get("ttshsi_after", usage.ttshsi_after),
        "tcsoh_after": data.get("tcsoh_after", usage.tcsoh_after),
        "pttsn_after": data.get("pttsn_after", usage.pttsn_after),
        "pttso_after": data.get("pttso_after", usage.pttso_after),
        "tscoa_after": data.get("tscoa_after", usage.tscoa_after),
        "hours_to_mx": data.get("hours_to_mx", usage.hours_to_mx),
        "days_to_mx": data.get("days_to_mx", usage.days_to_mx),
        "remarks": data.get("remarks", usage.remarks),
        "note": data.get("note", usage.note),
    }

    previous_usage = services.get_previous_usage(db, usage.aircraft_serial_number, effective_date)
    services.apply_usage_calculations(merged_data, previous_usage)
    services.update_maintenance_remaining(
        db,
        usage.aircraft_serial_number,
        effective_date,
        merged_data,
    )

    for field, value in merged_data.items():
        setattr(usage, field, value)

    usage.updated_by_user_id = current_user.id

    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


@router.delete(
    "/usage/{usage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_usage_entry(
    usage_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    usage = (
        db.query(models.AircraftUsage)
        .filter(models.AircraftUsage.id == usage_id)
        .first()
    )
    if not usage:
        raise HTTPException(status_code=404, detail="Usage entry not found")

    db.delete(usage)
    db.commit()
    return


@router.get(
    "/{serial_number}/usage/summary",
    response_model=schemas.AircraftUsageSummary,
)
def get_usage_summary(
    serial_number: str,
    db: Session = Depends(get_db),
):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    summary = services.build_usage_summary(db, serial_number)
    return summary


# ---------------------------------------------------------------------------
# MAINTENANCE PROGRAMME ITEMS
# (under /aircraft/maintenance-program/...)
# ---------------------------------------------------------------------------


@router.get(
    "/maintenance-program/items",
    response_model=List[schemas.MaintenanceProgramItemRead],
)
def list_maintenance_program_items(
    aircraft_template: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(models.MaintenanceProgramItem)
    if aircraft_template is not None:
        query = query.filter(
            models.MaintenanceProgramItem.aircraft_template == aircraft_template
        )

    return (
        query.order_by(
            models.MaintenanceProgramItem.aircraft_template.asc(),
            models.MaintenanceProgramItem.ata_chapter.asc(),
            models.MaintenanceProgramItem.task_code.asc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post(
    "/maintenance-program/items",
    response_model=schemas.MaintenanceProgramItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_maintenance_program_item(
    payload: schemas.MaintenanceProgramItemCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*PROGRAM_WRITE_ROLES)
    ),
):
    item = models.MaintenanceProgramItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put(
    "/maintenance-program/items/{item_id}",
    response_model=schemas.MaintenanceProgramItemRead,
)
def update_maintenance_program_item(
    item_id: int,
    payload: schemas.MaintenanceProgramItemUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*PROGRAM_WRITE_ROLES)
    ),
):
    item = (
        db.query(models.MaintenanceProgramItem)
        .filter(models.MaintenanceProgramItem.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Maintenance program item not found")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)

    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# MAINTENANCE STATUS (READ-ONLY)
# ---------------------------------------------------------------------------


@router.get(
    "/{serial_number}/maintenance-status",
    response_model=List[schemas.MaintenanceStatusRead],
)
def list_maintenance_status_for_aircraft(
    serial_number: str,
    db: Session = Depends(get_db),
):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    statuses = (
        db.query(models.MaintenanceStatus)
        .filter(models.MaintenanceStatus.aircraft_serial_number == serial_number)
        .all()
    )
    return statuses


# ---------------------------------------------------------------------------
# IMPORT HELPERS (ATA Spec 2000–aware)
# ---------------------------------------------------------------------------


def _normalise_header(name: str) -> str:
    """
    Normalise a column header to a forgiving key:
    - strip spaces
    - lower-case
    - remove common punctuation (space, slash, dash, dot)
    so that 'A/C REG', 'A-C REG.' -> 'ac_reg'.
    """
    cleaned = name.strip().lower()
    for ch in [" ", "-", "/", "."]:
        cleaned = cleaned.replace(ch, "_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned


def _map_aircraft_columns(raw_cols: List[str]) -> Dict[str, str | None]:
    """
    Map incoming header names onto our canonical field names.

    Canonical fields (left) vs typical incoming names (right):
    - serial_number (AIN): serial_number, aircraft, ac_serial, ain, aircraft_id, aircraft_identifier
    - registration (REG): registration, reg, ac_reg, aircraft_registration
    - template (aircraft_template/model): template, aircraft_template, aircraft_model, model_code
    - make: make, manufacturer, mfr
    - model: model, subtype, series
    - home_base: home_base, base, home_station, station
    - owner: owner, operator_name, company_name, who
    - aircraft_model_code: aircraft_model_code, model_code, model_id
    - operator_code (OPR): operator_code, opr, operator, airline_code
    - supplier_code (SPL): supplier_code, spl, supplier
    - company_name (WHO): who, company_name, operator_name
    - internal_aircraft_identifier: internal_id, internal_aircraft_id, fleet_id
    - last_log_date: last_log_date, date
    - total_hours: total_hours, hours, ttaf, tt_hours, total_time
    - total_cycles: total_cycles, cycles, ldg, landings
    """
    norm = {_normalise_header(c): c for c in raw_cols}

    def pick(*candidates: str) -> str | None:
        for cand in candidates:
            if cand in norm:
                return norm[cand]
        return None

    return {
        # Mandatory
        "serial_number": pick(
            "serial_number",
            "aircraft",
            "ac_serial",
            "ac_sn",
            "aircraft_sn",
            "ain",
            "aircraft_identification_number",
            "aircraft_id",
            "aircraft_identifier",
        ),
        "registration": pick(
            "registration",
            "reg",
            "ac_reg",
            "aircraft_registration",
        ),
        # Core configuration
        "template": pick(
            "template",
            "aircraft_template",
            "aircraft_model",
            "model_code",
        ),
        "make": pick(
            "make",
            "manufacturer",
            "mfr",
        ),
        "model": pick(
            "model",
            "subtype",
            "series",
        ),
        "home_base": pick(
            "home_base",
            "base",
            "home_station",
            "station",
        ),
        "owner": pick(
            "owner",
            "operator_name",
            "company_name",
            "who",
        ),
        # Spec 2000–style extra coding
        "aircraft_model_code": pick(
            "aircraft_model_code",
            "model_code",
            "model_id",
        ),
        "operator_code": pick(
            "operator_code",
            "opr",
            "operator",
            "airline_code",
        ),
        "supplier_code": pick(
            "supplier_code",
            "spl",
            "supplier",
        ),
        "company_name": pick(
            "company_name",
            "who",
            "operator_name",
        ),
        "internal_aircraft_identifier": pick(
            "internal_aircraft_identifier",
            "internal_id",
            "internal_aircraft_id",
            "fleet_id",
        ),
        # Utilisation snapshot
        "last_log_date": pick("last_log_date", "date"),
        "total_hours": pick(
            "total_hours",
            "hours",
            "ttaf",
            "tt_hours",
            "total_time",
        ),
        "total_cycles": pick(
            "total_cycles",
            "cycles",
            "ldg",
            "landings",
        ),
    }


def _coerce_import_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        import pandas as pd  # type: ignore

        if pd.isna(value):
            return None
    except ImportError:  # pragma: no cover
        pass
    if hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except Exception:  # pragma: no cover - defensive
            pass
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _build_aircraft_payload(
    row: Dict[str, Any], colmap: Dict[str, str | None]
) -> Dict[str, Any]:
    serial_raw_col = colmap["serial_number"]
    reg_raw_col = colmap["registration"]

    serial_value = row.get(serial_raw_col) if serial_raw_col else None
    registration_value = row.get(reg_raw_col) if reg_raw_col else None

    serial = (
        str(_coerce_import_value(serial_value)).strip()
        if serial_value is not None
        else ""
    )
    registration = (
        str(_coerce_import_value(registration_value)).strip()
        if registration_value is not None
        else ""
    )

    payload: Dict[str, Any] = {
        "serial_number": serial,
        "registration": registration,
        "template": _coerce_import_value(row.get(colmap["template"]))
        if colmap["template"]
        else None,
        "make": _coerce_import_value(row.get(colmap["make"]))
        if colmap["make"]
        else None,
        "model": _coerce_import_value(row.get(colmap["model"]))
        if colmap["model"]
        else None,
        "home_base": _coerce_import_value(row.get(colmap["home_base"]))
        if colmap["home_base"]
        else None,
        "owner": _coerce_import_value(row.get(colmap["owner"]))
        if colmap["owner"]
        else None,
        # Spec 2000–style coding
        "aircraft_model_code": _coerce_import_value(
            row.get(colmap["aircraft_model_code"])
        )
        if colmap["aircraft_model_code"]
        else None,
        "operator_code": _coerce_import_value(row.get(colmap["operator_code"]))
        if colmap["operator_code"]
        else None,
        "supplier_code": _coerce_import_value(row.get(colmap["supplier_code"]))
        if colmap["supplier_code"]
        else None,
        "company_name": _coerce_import_value(row.get(colmap["company_name"]))
        if colmap["company_name"]
        else None,
        "internal_aircraft_identifier": _coerce_import_value(
            row.get(colmap["internal_aircraft_identifier"])
        )
        if colmap["internal_aircraft_identifier"]
        else None,
        # Status / utilisation
        "status": "OPEN",
        "is_active": True,
        "last_log_date": _coerce_import_value(row.get(colmap["last_log_date"]))
        if colmap["last_log_date"]
        else None,
        "total_hours": _coerce_import_value(row.get(colmap["total_hours"]))
        if colmap["total_hours"]
        else None,
        "total_cycles": _coerce_import_value(row.get(colmap["total_cycles"]))
        if colmap["total_cycles"]
        else None,
    }

    for key, val in list(payload.items()):
        if isinstance(val, str) and not val.strip():
            payload[key] = None

    payload["serial_number"] = payload.get("serial_number") or ""
    payload["registration"] = payload.get("registration") or ""

    return payload


def _map_component_columns(raw_cols: List[str]) -> Dict[str, str | None]:
    """
    Map incoming header names onto canonical component fields.
    """
    norm = {_normalise_header(c): c for c in raw_cols}

    def pick(*candidates: str) -> str | None:
        for cand in candidates:
            if cand in norm:
                return norm[cand]
        return None

    return {
        "position": pick("position", "pos", "component_position", "location"),
        "ata": pick("ata", "ata_chapter", "ata_system"),
        "part_number": pick(
            "part_number",
            "part_no",
            "partnum",
            "pn",
            "pnr",
        ),
        "serial_number": pick(
            "serial_number",
            "serial_no",
            "serialnum",
            "sn",
            "sno",
        ),
        "description": pick("description", "desc"),
        "installed_date": pick("installed_date", "inst_date"),
        "installed_hours": pick("installed_hours"),
        "installed_cycles": pick("installed_cycles"),
        "current_hours": pick("current_hours"),
        "current_cycles": pick("current_cycles"),
        "notes": pick("notes", "remark", "remarks"),
        "manufacturer_code": pick("manufacturer_code", "mfr", "mfr_code"),
        "operator_code": pick("operator_code", "opr", "operator"),
    }


def _build_component_payload(
    row: Dict[str, Any], colmap: Dict[str, str | None]
) -> Dict[str, Any]:
    def to_str(value: Any) -> str | None:
        if value is None:
            return None
        coerced = _coerce_import_value(value)
        if coerced is None:
            return None
        return str(coerced).strip()

    def pick_value(key: str) -> Any:
        raw_col = colmap.get(key)
        if not raw_col:
            return None
        return _coerce_import_value(row.get(raw_col))

    return {
        "position": to_str(pick_value("position")) or "",
        "ata": to_str(pick_value("ata")),
        "part_number": to_str(pick_value("part_number")),
        "serial_number": to_str(pick_value("serial_number")),
        "description": to_str(pick_value("description")),
        "installed_date": pick_value("installed_date"),
        "installed_hours": pick_value("installed_hours"),
        "installed_cycles": pick_value("installed_cycles"),
        "current_hours": pick_value("current_hours"),
        "current_cycles": pick_value("current_cycles"),
        "notes": to_str(pick_value("notes")),
        "manufacturer_code": to_str(pick_value("manufacturer_code")),
        "operator_code": to_str(pick_value("operator_code")),
    }


def _validate_aircraft_payload(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    serial = payload.get("serial_number") or ""
    registration = payload.get("registration") or ""

    if not serial and not registration:
        errors.append("Missing both aircraft serial (AIN) and registration.")
    elif not serial:
        errors.append("Missing aircraft serial (AIN).")
    elif not registration:
        errors.append(f"Missing registration for aircraft serial {serial}.")

    return {"errors": errors, "warnings": warnings}


def _validate_component_payload(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    position = (payload.get("position") or "").strip()
    part_number = (payload.get("part_number") or "").strip()
    serial_number = (payload.get("serial_number") or "").strip()

    if not position:
        errors.append("Missing component position.")

    if (part_number and not serial_number) or (serial_number and not part_number):
        warnings.append("Part/serial number pair is incomplete.")

    return {"errors": errors, "warnings": warnings}


def _serialize_import_template(
    template: models.AircraftImportTemplate,
) -> Dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "template_type": template.template_type,
        "aircraft_template": template.aircraft_template,
        "model_code": template.model_code,
        "operator_code": template.operator_code,
    }


def _pick_import_template(
    payload: Dict[str, Any],
    templates: List[models.AircraftImportTemplate],
) -> Optional[models.AircraftImportTemplate]:
    template_value = (payload.get("template") or "").strip()
    model_code = (payload.get("aircraft_model_code") or "").strip()
    operator_code = (payload.get("operator_code") or "").strip()

    best_template: Optional[models.AircraftImportTemplate] = None
    best_score = 0

    for template in templates:
        score = 0
        if template.aircraft_template and template_value:
            if template.aircraft_template.lower() == template_value.lower():
                score += 3
        if template.model_code and model_code:
            if template.model_code.lower() == model_code.lower():
                score += 2
        if template.operator_code and operator_code:
            if template.operator_code.lower() == operator_code.lower():
                score += 1
        if score > best_score:
            best_score = score
            best_template = template

    return best_template


# ---------------------------------------------------------------------------
# IMPORT TEMPLATES (AIRCRAFT)
# ---------------------------------------------------------------------------


@router.get(
    "/import/templates",
    response_model=List[schemas.AircraftImportTemplateRead],
    tags=["aircraft"],
)
def list_import_templates(
    aircraft_template: Optional[str] = None,
    model_code: Optional[str] = None,
    operator_code: Optional[str] = None,
    template_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.AircraftImportTemplate)
    if template_type is not None:
        query = query.filter(
            models.AircraftImportTemplate.template_type == template_type
        )
    if aircraft_template is not None:
        query = query.filter(
            models.AircraftImportTemplate.aircraft_template == aircraft_template
        )
    if model_code is not None:
        query = query.filter(models.AircraftImportTemplate.model_code == model_code)
    if operator_code is not None:
        query = query.filter(
            models.AircraftImportTemplate.operator_code == operator_code
        )
    return query.order_by(models.AircraftImportTemplate.name.asc()).all()


@router.post(
    "/import/templates",
    response_model=schemas.AircraftImportTemplateRead,
    status_code=status.HTTP_201_CREATED,
    tags=["aircraft"],
)
def create_import_template(
    payload: schemas.AircraftImportTemplateCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    existing = (
        db.query(models.AircraftImportTemplate)
        .filter(models.AircraftImportTemplate.name == payload.name)
        .filter(
            models.AircraftImportTemplate.template_type
            == payload.template_type
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template with name {payload.name} already exists "
                f"for type {payload.template_type}."
            ),
        )
    template = models.AircraftImportTemplate(**payload.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.put(
    "/import/templates/{template_id}",
    response_model=schemas.AircraftImportTemplateRead,
    tags=["aircraft"],
)
def update_import_template(
    template_id: int,
    payload: schemas.AircraftImportTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    template = db.query(models.AircraftImportTemplate).get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    data = payload.model_dump(exclude_unset=True)
    new_name = data.get("name")
    target_type = data.get("template_type", template.template_type)
    if new_name and (
        new_name != template.name or target_type != template.template_type
    ):
        name_conflict = (
            db.query(models.AircraftImportTemplate)
            .filter(models.AircraftImportTemplate.name == new_name)
            .filter(
                models.AircraftImportTemplate.template_type == target_type
            )
            .first()
        )
        if name_conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Template with name {new_name} already exists "
                    f"for type {target_type}."
                ),
            )

    for field, value in data.items():
        setattr(template, field, value)

    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.delete(
    "/import/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["aircraft"],
)
def delete_import_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    template = db.query(models.AircraftImportTemplate).get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return


# ---------------------------------------------------------------------------
# BULK IMPORT (AIRCRAFT)
# ---------------------------------------------------------------------------


@router.post(
    "/import/preview",
    tags=["aircraft"],
    summary="Preview aircraft import with mapping and validation",
)
async def preview_aircraft_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    """
    Preview bulk import / update aircraft from CSV/Excel.

    Returns normalised rows, column mapping, validation issues and summary counts
    for new/update/invalid rows.
    """
    try:
        import pandas as pd  # type: ignore
    except ImportError:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="pandas is required for import. Install with 'pip install pandas openpyxl'.",
        )

    content = await file.read()
    buffer = BytesIO(content)
    file_type = ocr_service.detect_file_type(content, file.filename)
    ocr_info: Dict[str, Any] | None = None

    ext = Path(file.filename).suffix.lower()
    if file_type == "csv":
        df = pd.read_csv(buffer)
    elif file_type == "excel" and ext in [".xlsx", ".xlsm", ".xls"]:
        df = pd.read_excel(buffer)
    elif file_type in ["pdf", "image"]:
        try:
            ocr_table = ocr_service.extract_table_from_bytes(content, file_type)
        except ocr_service.OCRDependencyError as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        df = pd.DataFrame(ocr_table.rows, columns=ocr_table.headers)
        ocr_info = {
            "confidence": ocr_table.confidence,
            "samples": ocr_table.samples,
            "text": ocr_table.text,
            "file_type": file_type,
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. Upload CSV, XLSX, XLSM, XLS, PDF, or an image."
            ),
        )

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data.")

    colmap = _map_aircraft_columns(list(df.columns))
    if not colmap["serial_number"] or not colmap["registration"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "File must include at least aircraft serial/identifier (AIN) and "
                "registration columns. Accepted examples: "
                "AIN, serial_number, aircraft_id, registration, REG, AC REG."
            ),
        )

    rows: List[Dict[str, Any]] = []
    serials: List[str] = []
    seen_serials: Dict[str, int] = {}
    templates = (
        db.query(models.AircraftImportTemplate)
        .filter(models.AircraftImportTemplate.template_type == "aircraft")
        .all()
    )

    for idx, row in df.iterrows():
        row_idx = int(idx) + 2
        payload = _build_aircraft_payload(row.to_dict(), colmap)
        serial = payload.get("serial_number") or ""
        if serial:
            serials.append(serial)
            seen_serials[serial] = seen_serials.get(serial, 0) + 1
        suggested = _pick_import_template(payload, templates) if templates else None
        rows.append(
            {
                "row_number": row_idx,
                "data": payload,
                "suggested_template": _serialize_import_template(suggested)
                if suggested
                else None,
            }
        )

    existing_serials: set[str] = set()
    if serials:
        existing_serials = {
            serial
            for (serial,) in db.query(models.Aircraft.serial_number)
            .filter(models.Aircraft.serial_number.in_(serials))
            .all()
        }

    new_count = 0
    update_count = 0
    invalid_count = 0

    for row in rows:
        payload = row["data"]
        validation = _validate_aircraft_payload(payload)
        errors = validation["errors"]
        warnings = validation["warnings"]
        serial = payload.get("serial_number") or ""

        if serial and seen_serials.get(serial, 0) > 1:
            warnings.append("Duplicate serial number in uploaded file.")

        if errors:
            action = "invalid"
            invalid_count += 1
        else:
            if serial in existing_serials:
                action = "update"
                update_count += 1
            else:
                action = "new"
                new_count += 1

        row["errors"] = errors
        row["warnings"] = warnings
        row["action"] = action

    return {
        "rows": rows,
        "column_mapping": colmap,
        "summary": {
            "new": new_count,
            "update": update_count,
            "invalid": invalid_count,
        },
        "ocr": ocr_info,
    }


@router.post(
    "/import",
    tags=["aircraft"],
    summary="Bulk import / update aircraft from CSV or Excel",
)
async def import_aircraft_file(
    payload: schemas.AircraftImportRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    """
    Bulk import / update aircraft from approved rows.

    - Requires at least an aircraft identifier (AIN/serial_number) and REG.
    - Returns counts plus skipped-row reasons so users understand
      why a row did not import.
    """
    created = 0
    updated = 0
    skipped = 0
    skipped_rows: List[Dict[str, Any]] = []

    for row in payload.rows:
        row_idx = row.row_number
        row_data = row.model_dump(exclude={"row_number"})

        validation = _validate_aircraft_payload(row_data)
        if validation["errors"]:
            skipped += 1
            skipped_rows.append(
                {
                    "row": row_idx,
                    "reason": "; ".join(validation["errors"]),
                }
            )
            continue

        serial = str(row_data.get("serial_number") or "").strip()
        registration = str(row_data.get("registration") or "").strip()

        row_data["serial_number"] = serial
        row_data["registration"] = registration

        for key, val in list(row_data.items()):
            if isinstance(val, str) and not val.strip():
                row_data[key] = None

        ac = db.query(models.Aircraft).get(serial)

        if ac is None:
            # New aircraft
            ac = models.Aircraft(**row_data)
            db.add(ac)
            created += 1
        else:
            # Update existing master record with latest data
            for field, value in row_data.items():
                setattr(ac, field, value)
            updated += 1

    db.commit()

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "skipped_rows": skipped_rows,
    }


# ---------------------------------------------------------------------------
# BULK IMPORT (COMPONENTS)
# ---------------------------------------------------------------------------


@router.post(
    "/{serial_number}/components/import/preview",
    tags=["aircraft"],
    summary="Preview component import with normalization and dedupe hints",
)
async def preview_components_import(
    serial_number: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    """
    Preview components for an aircraft before importing.

    Returns normalized rows, validation errors/warnings, and dedupe hints
    based on part/serial number pairs.
    """
    try:
        import pandas as pd  # type: ignore
    except ImportError:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="pandas is required for import. Install with 'pip install pandas openpyxl'.",
        )

    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    ext = Path(file.filename).suffix.lower()
    content = await file.read()
    buffer = BytesIO(content)

    if ext in [".csv", ".txt"]:
        df = pd.read_csv(buffer)
    elif ext in [".xlsx", ".xlsm", ".xls"]:
        df = pd.read_excel(buffer)
    elif ext == ".pdf":
        raise HTTPException(
            status_code=501,
            detail="PDF ingestion for components not yet implemented. Use CSV/Excel for now.",
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Upload CSV, XLSX, XLSM or XLS.",
        )

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data.")

    colmap = _map_component_columns(list(df.columns))
    if not colmap["position"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Component file must have a 'position' column "
                "(examples: position, pos)."
            ),
        )

    existing_components = (
        db.query(models.AircraftComponent)
        .filter(models.AircraftComponent.aircraft_serial_number == serial_number)
        .all()
    )
    existing_by_position = {
        (comp.position or "").strip().lower(): comp for comp in existing_components
    }
    existing_by_pn_sn: Dict[tuple[str, str], List[models.AircraftComponent]] = {}
    for comp in existing_components:
        pn = (comp.part_number or "").strip().lower()
        sn = (comp.serial_number or "").strip().lower()
        if pn and sn:
            existing_by_pn_sn.setdefault((pn, sn), []).append(comp)

    seen_in_file: Dict[tuple[str, str], List[str]] = {}
    rows: List[Dict[str, Any]] = []
    new_count = 0
    update_count = 0
    invalid_count = 0

    for idx, row in df.iterrows():
        row_idx = int(idx) + 2  # approx Excel row number
        payload = _build_component_payload(row.to_dict(), colmap)
        validation = _validate_component_payload(payload)
        errors = validation["errors"]
        warnings = validation["warnings"]
        position = payload.get("position") or ""
        existing_component = (
            existing_by_position.get(position.lower()) if position else None
        )
        dedupe_suggestions: List[Dict[str, Any]] = []

        part_number = (payload.get("part_number") or "").strip()
        serial = (payload.get("serial_number") or "").strip()
        if part_number and serial:
            key = (part_number.lower(), serial.lower())
            if key in seen_in_file:
                warnings.append("Duplicate part/serial pair found in upload.")
                dedupe_suggestions.append(
                    {
                        "source": "file",
                        "part_number": part_number,
                        "serial_number": serial,
                        "positions": seen_in_file[key],
                    }
                )
            if key in existing_by_pn_sn:
                warnings.append("Part/serial pair already exists on this aircraft.")
                dedupe_suggestions.append(
                    {
                        "source": "existing",
                        "part_number": part_number,
                        "serial_number": serial,
                        "positions": [
                            comp.position for comp in existing_by_pn_sn[key]
                        ],
                    }
                )
            seen_in_file.setdefault(key, []).append(position or f"row {row_idx}")

        if errors:
            action = "invalid"
            invalid_count += 1
        else:
            if existing_component:
                action = "update"
                update_count += 1
            else:
                action = "new"
                new_count += 1

        rows.append(
            {
                "row_number": row_idx,
                "data": payload,
                "errors": errors,
                "warnings": warnings,
                "action": action,
                "existing_component": {
                    "position": existing_component.position,
                    "part_number": existing_component.part_number,
                    "serial_number": existing_component.serial_number,
                }
                if existing_component
                else None,
                "dedupe_suggestions": dedupe_suggestions,
            }
        )

    return {
        "rows": rows,
        "column_mapping": colmap,
        "summary": {
            "new": new_count,
            "update": update_count,
            "invalid": invalid_count,
        },
    }


@router.post(
    "/{serial_number}/components/import/confirm",
    tags=["aircraft"],
    summary="Confirm component import for approved rows",
)
async def confirm_components_import(
    serial_number: str,
    payload: schemas.AircraftComponentImportRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    existing_components = (
        db.query(models.AircraftComponent)
        .filter(models.AircraftComponent.aircraft_serial_number == serial_number)
        .all()
    )
    existing_by_position = {
        (comp.position or "").strip().lower(): comp for comp in existing_components
    }

    created = 0
    updated = 0
    skipped = 0
    skipped_rows: List[Dict[str, Any]] = []

    for row in payload.rows:
        row_idx = row.row_number
        row_data = row.model_dump(exclude={"row_number"})

        for key, value in list(row_data.items()):
            if isinstance(value, str) and not value.strip():
                row_data[key] = None

        validation = _validate_component_payload(row_data)
        if validation["errors"]:
            skipped += 1
            skipped_rows.append(
                {
                    "row": row_idx,
                    "reason": "; ".join(validation["errors"]),
                }
            )
            continue

        position = (row_data.get("position") or "").strip()
        if not position:
            skipped += 1
            skipped_rows.append(
                {"row": row_idx, "reason": "Missing component position."}
            )
            continue

        comp = existing_by_position.get(position.lower())
        if comp is None:
            comp = models.AircraftComponent(
                aircraft_serial_number=serial_number,
                position=position,
            )
            created += 1
        else:
            updated += 1

        for field, value in row_data.items():
            setattr(comp, field, value)

        db.add(comp)
        existing_by_position[position.lower()] = comp

    db.commit()

    return {
        "status": "ok",
        "aircraft_serial_number": serial_number,
        "components_created": created,
        "components_updated": updated,
        "components_skipped": skipped,
        "skipped_rows": skipped_rows,
    }


@router.post(
    "/{serial_number}/components/import",
    tags=["aircraft"],
    summary="Bulk import components for a single aircraft from CSV/Excel",
)
async def import_components_file(
    serial_number: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    """
    Bulk import components for a single aircraft.

    Accepts Spec 2000-style and conventional column names for:
    - position
    - ATA chapter
    - part number (PN, PNR)
    - serial number (SN, SNO)
    - manufacturer/operator codes (MFR, OPR)
    - installed/current hours/cycles
    """
    try:
        import pandas as pd  # type: ignore
    except ImportError:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="pandas is required for import. Install with 'pip install pandas openpyxl'.",
        )

    ac = db.query(models.Aircraft).get(serial_number)
    if not ac:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    ext = Path(file.filename).suffix.lower()
    content = await file.read()
    buffer = BytesIO(content)

    if ext in [".csv", ".txt"]:
        df = pd.read_csv(buffer)
    elif ext in [".xlsx", ".xlsm", ".xls"]:
        df = pd.read_excel(buffer)
    elif ext == ".pdf":
        raise HTTPException(
            status_code=501,
            detail="PDF ingestion for components not yet implemented. Use CSV/Excel for now.",
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Upload CSV, XLSX, XLSM or XLS.",
        )

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data.")

    colmap = _map_component_columns(list(df.columns))
    if not colmap["position"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Component file must have a 'position' column "
                "(examples: position, pos)."
            ),
        )

    created = 0
    skipped = 0
    skipped_rows: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        row_idx = int(idx) + 2  # approx Excel row number

        payload = _build_component_payload(row.to_dict(), colmap)
        position = payload.get("position") or ""

        if not position:
            skipped += 1
            skipped_rows.append(
                {"row": row_idx, "reason": "Missing component position."}
            )
            continue

        comp = models.AircraftComponent(
            aircraft_serial_number=serial_number,
            position=position,
            ata=payload.get("ata"),
            part_number=payload.get("part_number"),
            serial_number=payload.get("serial_number"),
            description=payload.get("description"),
            installed_date=payload.get("installed_date"),
            installed_hours=payload.get("installed_hours"),
            installed_cycles=payload.get("installed_cycles"),
            current_hours=payload.get("current_hours"),
            current_cycles=payload.get("current_cycles"),
            notes=payload.get("notes"),
            manufacturer_code=payload.get("manufacturer_code"),
            operator_code=payload.get("operator_code"),
        )

        db.add(comp)
        created += 1

    db.commit()

    return {
        "status": "ok",
        "aircraft_serial_number": serial_number,
        "components_created": created,
        "components_skipped": skipped,
        "skipped_rows": skipped_rows,
    }
