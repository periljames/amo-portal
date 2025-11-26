# backend/amodb/apps/fleet/router.py

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import List

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
from . import models, schemas

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


# ---------------- BASIC AIRCRAFT CRUD ----------------


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
    existing = db.query(models.Aircraft).get(payload.serial_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aircraft with serial {payload.serial_number} already exists.",
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


# ---------------- COMPONENTS CRUD ----------------


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


# ---------------- AIRCRAFT USAGE ----------------


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
    for field, value in data.items():
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


# ---------------- MAINTENANCE PROGRAMME ITEMS ----------------
# Note: paths are under /aircraft/maintenance-program/... because this router
# has prefix="/aircraft".


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


# ---------------- MAINTENANCE STATUS (READ-ONLY) ----------------


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


# ---------------- BULK IMPORT (AIRCRAFT) ----------------


def _normalise_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _map_aircraft_columns(raw_cols: List[str]) -> dict:
    """
    Map incoming header names onto our canonical field names.
    Very forgiving about spaces / case.
    """
    norm = {_normalise_header(c): c for c in raw_cols}

    def pick(*candidates):
        for cand in candidates:
            if cand in norm:
                return norm[cand]
        return None

    return {
        "serial_number": pick("serial_number", "aircraft", "ac_serial"),
        "registration": pick("registration", "reg"),
        "template": pick("template"),
        "make": pick("make"),
        "model": pick("model"),
        "home_base": pick("home_base", "base"),
        "owner": pick("owner"),
        "last_log_date": pick("last_log_date", "date"),
        "total_hours": pick("total_hours", "hours"),
        "total_cycles": pick("total_cycles", "cycles"),
    }


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
            detail="File must include at least aircraft serial number and registration columns.",
        )

    created = 0
    updated = 0

    for _, row in df.iterrows():
        serial = str(row[colmap["serial_number"]]).strip()
        if not serial:
            continue

        registration = str(row[colmap["registration"]]).strip()
        if not registration:
            # Without registration it's probably junk row
            continue

        ac = db.query(models.Aircraft).get(serial)

        payload = {
            "serial_number": serial,
            "registration": registration,
            "template": row.get(colmap["template"]) if colmap["template"] else None,
            "make": row.get(colmap["make"]) if colmap["make"] else None,
            "model": row.get(colmap["model"]) if colmap["model"] else None,
            "home_base": row.get(colmap["home_base"]) if colmap["home_base"] else None,
            "owner": row.get(colmap["owner"]) if colmap["owner"] else None,
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

        if ac is None:
            ac = models.Aircraft(**payload)
            db.add(ac)
            created += 1
        else:
            # Update existing
            for field, value in payload.items():
                setattr(ac, field, value)
            updated += 1

    db.commit()

    return {
        "status": "ok",
        "created": created,
        "updated": updated,
    }


# ---------------- BULK IMPORT (COMPONENTS) ----------------


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

    # Expected columns (case-insensitive, spaces ignored):
    # position, ata, part_number, serial_number, description,
    # installed_date, installed_hours, installed_cycles,
    # current_hours, current_cycles, notes
    norm_cols = {_normalise_header(c): c for c in df.columns}

    def col(name):
        return norm_cols.get(name)

    created = 0

    for _, row in df.iterrows():
        position_col = col("position")
        if not position_col:
            raise HTTPException(
                status_code=400,
                detail="Component file must have a 'position' column.",
            )

        position = str(row[position_col]).strip()
        if not position:
            continue

        comp = models.AircraftComponent(
            aircraft_serial_number=serial_number,
            position=position,
            ata=row.get(col("ata")) if col("ata") else None,
            part_number=row.get(col("part_number")) if col("part_number") else None,
            serial_number=row.get(col("serial_number")) if col("serial_number") else None,
            description=row.get(col("description")) if col("description") else None,
            installed_date=row.get(col("installed_date"))
            if col("installed_date")
            else None,
            installed_hours=row.get(col("installed_hours"))
            if col("installed_hours")
            else None,
            installed_cycles=row.get(col("installed_cycles"))
            if col("installed_cycles")
            else None,
            current_hours=row.get(col("current_hours"))
            if col("current_hours")
            else None,
            current_cycles=row.get(col("current_cycles"))
            if col("current_cycles")
            else None,
            notes=row.get(col("notes")) if col("notes") else None,
        )
        db.add(comp)
        created += 1

    db.commit()

    return {
        "status": "ok",
        "aircraft_serial_number": serial_number,
        "components_created": created,
    }
