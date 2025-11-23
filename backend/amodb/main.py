# backend/amodb/main.py

from datetime import datetime
import base64
import json
import zlib
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db  # engine kept for Alembic usage / tooling
from .security import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    require_admin,
    get_password_hash,
)
from .user_id import generate_user_id

# App routers
from .apps.fleet.router import router as fleet_router
from .apps.work.router import router as work_router
from .apps.crs.router import router as crs_router

# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------

# IMPORTANT:
# Schema creation is now handled by Alembic migrations.
# Do NOT call Base.metadata.create_all() here in production.
# (You can temporarily uncomment the next line on a throwaway dev DB.)
# Base.metadata.create_all(bind=engine)

app = FastAPI(title="AMO Portal API", version="1.0.0")

# CORS – open for now, we’ll tighten later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RETENTION_YEARS = 3  # 36 months for archived users


# --------------------------------------------------------------------
# UTILITIES: ACTIVITY + ARCHIVE SNAPSHOTS
# --------------------------------------------------------------------


def log_activity(
    db: Session,
    actor: Optional[models.User],
    target_user: Optional[models.User],
    action: str,
    description: str = "",
) -> None:
    """
    Lightweight audit log helper.
    """
    activity = models.UserActivity(
        actor_id=actor.id if actor else None,
        target_user_id=target_user.id if target_user else None,
        action=action,
        description=description,
        created_at=datetime.utcnow(),
    )
    db.add(activity)
    db.commit()


def compress_user_snapshot(user: models.User) -> str:
    payload = {
        "id": user.id,
        "user_code": user.user_code,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "amo_code": user.amo_code,
        "department_code": user.department_code,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "is_amo_admin": user.is_amo_admin,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }
    raw = json.dumps(payload).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return base64.b64encode(compressed).decode("ascii")


def decompress_user_snapshot(data_b64: str) -> dict:
    compressed = base64.b64decode(data_b64.encode("ascii"))
    raw = zlib.decompress(compressed)
    return json.loads(raw.decode("utf-8"))


def retention_cutoff(archived_at: datetime) -> datetime:
    return archived_at.replace(year=archived_at.year + RETENTION_YEARS)


# --------------------------------------------------------------------
# HEALTH
# --------------------------------------------------------------------


@app.get("/", tags=["health"])
def read_root():
    return {"status": "ok", "message": "AMO Portal backend is running"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------
# AUTH
# --------------------------------------------------------------------


@app.post("/auth/token", response_model=schemas.Token, tags=["auth"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Standard email + password login.

    Returns bearer token with:
      - sub = user.id
      - role / amo_code / department_code / flags in claims
    """
    user = authenticate_user(db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.utcnow()
    db.add(user)
    db.commit()

    access_token = create_access_token(user=user)

    log_activity(
        db,
        actor=user,
        target_user=user,
        action="login",
        description="User logged in",
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --------------------------------------------------------------------
# BOOTSTRAP FIRST ADMIN (REPLACES create_initial_admin.py)
# --------------------------------------------------------------------


@app.post(
    "/auth/bootstrap-admin",
    response_model=schemas.UserRead,
    tags=["auth"],
    status_code=status.HTTP_201_CREATED,
)
def bootstrap_first_admin(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    """
    One-time endpoint to create the very first superuser.

    Rules:
    - Only works if there are NO users in the system.
    - Creates a superuser + AMO admin with role="admin".
    - After the first user exists, this endpoint is disabled.
    """
    existing = db.query(models.User).count()
    if existing > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bootstrap admin is already created.",
        )

    # Generate user_code from name
    parts = payload.full_name.strip().split()
    first = parts[0] if parts else ""
    last = parts[-1] if parts else ""

    existing_codes = [row[0] for row in db.query(models.User.user_code).all() if row[0]]
    user_code = generate_user_id(first_name=first, last_name=last, existing_ids=existing_codes)

    user = models.User(
        user_code=user_code,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role or "admin",
        amo_code=payload.amo_code,
        department_code=payload.department_code,
        is_active=True,
        is_superuser=True,
        is_amo_admin=True,
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db,
        actor=user,
        target_user=user,
        action="bootstrap_admin",
        description="Initial superuser created via bootstrap endpoint.",
    )
    return user


# --------------------------------------------------------------------
# USERS
# --------------------------------------------------------------------


@app.post("/users/", response_model=schemas.UserRead, tags=["users"])
def create_user(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a new user. Only admins/quality/HR (and superusers/AMO admins)
    can do this.
    """
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    rows = db.query(models.User.user_code).all()
    existing_ids = [row[0] for row in rows if row[0]]

    parts = user_in.full_name.strip().split()
    first = parts[0] if parts else ""
    last = parts[-1] if parts else ""

    user_code = generate_user_id(
        first_name=first,
        last_name=last,
        existing_ids=existing_ids,
        prefer_style="LAST4",
    )

    user = models.User(
        user_code=user_code,
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role or "user",
        amo_code=user_in.amo_code or current_user.amo_code,
        department_code=user_in.department_code,
        is_active=True,
        is_superuser=False,
        is_amo_admin=False,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db,
        actor=current_user,
        target_user=user,
        action="user_create",
        description=f"User {user.email} created",
    )
    return user


@app.get("/users/", response_model=List[schemas.UserRead], tags=["users"])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List users. At this stage we allow any active user to see the list.
    You can later restrict this to admins only if desired.
    """
    users = (
        db.query(models.User)
        .order_by(models.User.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return users


@app.get("/users/me", response_model=schemas.UserRead, tags=["users"])
def read_current_user(
    current_user: models.User = Depends(get_current_active_user),
):
    return current_user


@app.get("/users/{user_id}", response_model=schemas.UserRead, tags=["users"])
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.put("/users/{user_id}", response_model=schemas.UserRead, tags=["users"])
def update_user(
    user_id: int,
    user_in: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Basic updates anyone can do on themselves
    if user_in.full_name is not None:
        user.full_name = user_in.full_name

    if user_in.amo_code is not None:
        # In many orgs only admin/HR should change AMO/department.
        if not (current_user.is_superuser or current_user.is_amo_admin):
            raise HTTPException(
                status_code=403,
                detail="Only admins can change AMO code",
            )
        user.amo_code = user_in.amo_code

    if user_in.department_code is not None:
        if not (current_user.is_superuser or current_user.is_amo_admin):
            raise HTTPException(
                status_code=403,
                detail="Only admins can change department",
            )
        user.department_code = user_in.department_code

    # Privileged updates
    if user_in.role is not None:
        if not (current_user.is_superuser or current_user.is_amo_admin):
            raise HTTPException(
                status_code=403,
                detail="Only admins can change roles",
            )
        user.role = user_in.role

    if user_in.is_active is not None:
        if not (current_user.is_superuser or current_user.is_amo_admin):
            raise HTTPException(
                status_code=403,
                detail="Only admins can deactivate users",
            )
        user.is_active = user_in.is_active

    if user_in.is_superuser is not None or user_in.is_amo_admin is not None:
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=403,
                detail="Only a superuser can change admin flags",
            )
        if user_in.is_superuser is not None:
            user.is_superuser = user_in.is_superuser
        if user_in.is_amo_admin is not None:
            user.is_amo_admin = user_in.is_amo_admin

    if user_in.password is not None:
        # User can change their own password;
        # admins can also reset passwords if you allow it.
        user.hashed_password = get_password_hash(user_in.password)

    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db,
        actor=current_user,
        target_user=user,
        action="user_update",
        description=f"User {user.email} updated",
    )
    return user


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["users"])
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    archived_at = datetime.utcnow()
    delete_after = retention_cutoff(archived_at)
    snapshot_b64 = compress_user_snapshot(user)

    archived = models.ArchivedUser(
        original_user_id=user.id,
        user_code=user.user_code,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        amo_code=user.amo_code,
        department_code=user.department_code,
        archived_at=archived_at,
        delete_after=delete_after,
        compressed_snapshot_b64=snapshot_b64,
    )
    db.add(archived)

    db.delete(user)
    db.commit()

    log_activity(
        db,
        actor=current_user,
        target_user=None,
        action="user_delete_archive",
        description=f"User {archived.email} archived for 36 months",
    )
    return None


# --------------------------------------------------------------------
# RETENTION & ARCHIVE
# --------------------------------------------------------------------


@app.get(
    "/retention/archived-users",
    response_model=List[schemas.ArchivedUserSummary],
    tags=["retention"],
)
def list_archived_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    items = (
        db.query(models.ArchivedUser)
        .order_by(models.ArchivedUser.archived_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items


@app.get(
    "/retention/archived-users/{archived_id}",
    response_model=schemas.ArchivedUserDetail,
    tags=["retention"],
)
def get_archived_user(
    archived_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    item = (
        db.query(models.ArchivedUser)
        .filter(models.ArchivedUser.id == archived_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Archived user not found")

    snapshot = decompress_user_snapshot(item.compressed_snapshot_b64)
    return schemas.ArchivedUserDetail(
        id=item.id,
        user_code=item.user_code,
        email=item.email,
        full_name=item.full_name,
        role=item.role,
        amo_code=item.amo_code,
        department_code=item.department_code,
        archived_at=item.archived_at,
        delete_after=item.delete_after,
        snapshot=snapshot,
    )


@app.post("/retention/cleanup", tags=["retention"])
def retention_cleanup(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    now = datetime.utcnow()
    expired_archives: List[models.ArchivedUser] = (
        db.query(models.ArchivedUser)
        .filter(models.ArchivedUser.delete_after <= now)
        .all()
    )

    count_archived = len(expired_archives)
    count_activities = 0

    for archived in expired_archives:
        acts = (
            db.query(models.UserActivity)
            .filter(
                (models.UserActivity.actor_id == archived.original_user_id)
                | (models.UserActivity.target_user_id == archived.original_user_id)
            )
            .all()
        )
        count_activities += len(acts)
        for a in acts:
            db.delete(a)
        db.delete(archived)

    db.commit()

    log_activity(
        db,
        actor=current_user,
        target_user=None,
        action="retention_cleanup",
        description=f"Deleted {count_archived} archived users and {count_activities} activities",
    )

    return {
        "status": "ok",
        "archived_deleted": count_archived,
        "activities_deleted": count_activities,
    }


# --------------------------------------------------------------------
# REGISTER APP ROUTERS
# --------------------------------------------------------------------

# Fleet / aircraft master data
app.include_router(fleet_router)

# Work orders + tasks (must exist before CRS)
app.include_router(work_router)

# CRS (tied to aircraft + work orders)
app.include_router(crs_router)
