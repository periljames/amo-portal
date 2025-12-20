# backend/amodb/apps/fleet/router.py

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any

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
from . import models, schemas, usage_services

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
    previous_usage = usage_services.get_previous_usage(db, serial_number, payload.date)
    usage_services.apply_usage_calculations(data, previous_usage)
    usage_services.update_maintenance_remaining(db, serial_number, payload.date, data)
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

    previous_usage = usage_services.get_previous_usage(
        db,
        usage.aircraft_serial_number,
        effective_date,
    )
    usage_services.apply_usage_calculations(merged_data, previous_usage)
    usage_services.update_maintenance_remaining(
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
    summary = usage_services.build_usage_summary(db, serial_number)
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
    usage_snapshot = usage_services.get_usage_snapshot(db, serial_number, date.today())

    response: list[schemas.MaintenanceStatusRead] = []
    for status in statuses:
        remaining = usage_services.compute_remaining_fields(status, usage_snapshot)
        response.append(
            schemas.MaintenanceStatusRead(
                id=status.id,
                aircraft_serial_number=status.aircraft_serial_number,
                program_item_id=status.program_item_id,
                last_done_date=status.last_done_date,
                last_done_hours=status.last_done_hours,
                last_done_cycles=status.last_done_cycles,
                next_due_date=status.next_due_date,
                next_due_hours=status.next_due_hours,
                next_due_cycles=status.next_due_cycles,
                remaining_days=remaining["remaining_days"],
                remaining_hours=remaining["remaining_hours"],
                remaining_cycles=remaining["remaining_cycles"],
                program_item=status.program_item,
            )
        )
    return response


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


# ---------------------------------------------------------------------------
# BULK IMPORT (AIRCRAFT)
# ---------------------------------------------------------------------------


@router.post(
    "/import",
    tags=["aircraft"],
    summary="Bulk import / update aircraft from CSV or Excel",
)
async def import_aircraft_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(
        require_roles(*MANAGEMENT_ROLES)
    ),
):
    """
    Bulk import / update aircraft from CSV/Excel.

    - Uses forgiving header mapping, including ATA Spec 2000-style field names.
    - Requires at least an aircraft identifier (AIN/serial_number) and REG.
    - Returns counts plus mapping and skipped-row reasons so users
      understand *why* a row did not import.
    """
    try:
        import pandas as pd  # type: ignore
    except ImportError:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail="pandas is required for import. Install with 'pip install pandas openpyxl'.",
        )

    ext = Path(file.filename).suffix.lower()
    content = await file.read()
    buffer = BytesIO(content)

    if ext in [".csv", ".txt"]:
        df = pd.read_csv(buffer)
    elif ext in [".xlsx", ".xlsm", ".xls"]:
        df = pd.read_excel(buffer)
    elif ext == ".pdf":
        # Placeholder – PDF parsing is messy; we'll support later.
        raise HTTPException(
            status_code=501,
            detail="PDF ingestion not yet implemented. Please upload CSV or Excel export for now.",
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Upload CSV, XLSX, XLSM or XLS.",
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

    created = 0
    updated = 0
    skipped = 0
    skipped_rows: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        row_idx = int(idx) + 2  # +2 to roughly match Excel row (header + 1)

        # Aircraft serial / AIN
        serial_raw_col = colmap["serial_number"]
        reg_raw_col = colmap["registration"]

        serial_value = row.get(serial_raw_col) if serial_raw_col else None
        registration_value = row.get(reg_raw_col) if reg_raw_col else None

        serial = str(serial_value).strip() if serial_value is not None else ""
        registration = (
            str(registration_value).strip() if registration_value is not None else ""
        )

        if not serial and not registration:
            skipped += 1
            skipped_rows.append(
                {
                    "row": row_idx,
                    "reason": "Missing both aircraft serial (AIN) and registration.",
                }
            )
            continue

        if not serial:
            skipped += 1
            skipped_rows.append(
                {
                    "row": row_idx,
                    "reason": "Missing aircraft serial (AIN).",
                }
            )
            continue

        if not registration:
            skipped += 1
            skipped_rows.append(
                {
                    "row": row_idx,
                    "reason": f"Missing registration for aircraft serial {serial}.",
                }
            )
            continue

        ac = db.query(models.Aircraft).get(serial)

        payload: Dict[str, Any] = {
            "serial_number": serial,
            "registration": registration,
            "template": row.get(colmap["template"]) if colmap["template"] else None,
            "make": row.get(colmap["make"]) if colmap["make"] else None,
            "model": row.get(colmap["model"]) if colmap["model"] else None,
            "home_base": row.get(colmap["home_base"]) if colmap["home_base"] else None,
            "owner": row.get(colmap["owner"]) if colmap["owner"] else None,
            # Spec 2000–style coding
            "aircraft_model_code": row.get(colmap["aircraft_model_code"])
            if colmap["aircraft_model_code"]
            else None,
            "operator_code": row.get(colmap["operator_code"])
            if colmap["operator_code"]
            else None,
            "supplier_code": row.get(colmap["supplier_code"])
            if colmap["supplier_code"]
            else None,
            "company_name": row.get(colmap["company_name"])
            if colmap["company_name"]
            else None,
            "internal_aircraft_identifier": row.get(
                colmap["internal_aircraft_identifier"]
            )
            if colmap["internal_aircraft_identifier"]
            else None,
            # Status / utilisation
            "status": "OPEN",
            "is_active": True,
            "last_log_date": row.get(colmap["last_log_date"])
            if colmap["last_log_date"]
            else None,
            "total_hours": row.get(colmap["total_hours"])
            if colmap["total_hours"]
            else None,
            "total_cycles": row.get(colmap["total_cycles"])
            if colmap["total_cycles"]
            else None,
        }

        # Basic clean-up: empty strings -> None
        for key, val in list(payload.items()):
            if isinstance(val, str) and not val.strip():
                payload[key] = None

        if ac is None:
            # New aircraft
            ac = models.Aircraft(**payload)
            db.add(ac)
            created += 1
        else:
            # Update existing master record with latest data
            for field, value in payload.items():
                setattr(ac, field, value)
            updated += 1

    db.commit()

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "column_mapping": colmap,
        "skipped_rows": skipped_rows,
    }


# ---------------------------------------------------------------------------
# BULK IMPORT (COMPONENTS)
# ---------------------------------------------------------------------------


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

    norm_cols = {_normalise_header(c): c for c in df.columns}

    def col(*names: str) -> str | None:
        for name in names:
            if name in norm_cols:
                return norm_cols[name]
        return None

    position_col = col("position", "pos")
    if not position_col:
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

        position_raw = row.get(position_col)
        position = str(position_raw).strip() if position_raw is not None else ""

        if not position:
            skipped += 1
            skipped_rows.append(
                {"row": row_idx, "reason": "Missing component position."}
            )
            continue

        comp = models.AircraftComponent(
            aircraft_serial_number=serial_number,
            position=position,
            ata=row.get(col("ata")),
            part_number=row.get(
                col("part_number", "pn", "pnr", "part_no", "partnum")
            ),
            serial_number=row.get(
                col("serial_number", "sn", "sno", "serial_no", "serialnum")
            ),
            description=row.get(col("description", "desc")),
            installed_date=row.get(col("installed_date", "inst_date")),
            installed_hours=row.get(col("installed_hours")),
            installed_cycles=row.get(col("installed_cycles")),
            current_hours=row.get(col("current_hours")),
            current_cycles=row.get(col("current_cycles")),
            notes=row.get(col("notes", "remark", "remarks")),
            manufacturer_code=row.get(col("manufacturer_code", "mfr", "mfr_code")),
            operator_code=row.get(col("operator_code", "opr", "operator")),
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
