from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin
from . import models, schemas, services

router = APIRouter(prefix="/accounts/admin", tags=["accounts_admin"])


# ---------------------------------------------------------------------------
# AMO MANAGEMENT (SUPERUSER ONLY)
# ---------------------------------------------------------------------------


def _require_superuser(current_user: models.User) -> models.User:
    """
    Internal helper: platform superuser gate.

    - Blocks system/AI accounts even if they somehow had is_superuser=True.
    - Requires is_superuser=True (GOD mode).
    """
    # System / AI / service accounts must never act as platform superuser.
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot use superuser endpoints.",
        )

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required.",
        )
    return current_user


@router.post(
    "/amos",
    response_model=schemas.AMORead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AMO (platform superuser only)",
)
def create_amo(
    payload: schemas.AMOCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create a new AMO.

    Only the platform SUPERUSER can call this. Normal AMO admins cannot
    create new organisations.
    """
    _require_superuser(current_user)

    existing = (
        db.query(models.AMO)
        .filter(
            (models.AMO.amo_code == payload.amo_code)
            | (models.AMO.login_slug == payload.login_slug)
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AMO with this code or login_slug already exists.",
        )

    amo = models.AMO(
        amo_code=payload.amo_code,
        name=payload.name,
        icao_code=payload.icao_code,
        country=payload.country,
        login_slug=payload.login_slug,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        time_zone=payload.time_zone,
        is_active=True,
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


@router.get(
    "/amos",
    response_model=List[schemas.AMORead],
    summary="List all AMOs (platform superuser only)",
)
def list_amos(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List all AMOs in the platform.

    Only SUPERUSER can see the full list.
    """
    _require_superuser(current_user)
    return db.query(models.AMO).order_by(models.AMO.amo_code.asc()).all()


# ---------------------------------------------------------------------------
# DEPARTMENTS (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/departments",
    response_model=schemas.DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create department within current user's AMO (or any AMO for superuser)",
)
def create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a department.

    - Normal AMO admins: can only create departments in their own AMO.
    - SUPERUSER: can create departments in any AMO.
    """
    # Only admins of this AMO can create departments unless superuser
    if payload.amo_id != current_user.amo_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create department for another AMO.",
        )

    dup = (
        db.query(models.Department)
        .filter(
            models.Department.amo_id == payload.amo_id,
            models.Department.code == payload.code,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department code already exists for this AMO.",
        )

    dept = models.Department(
        amo_id=payload.amo_id,
        code=payload.code,
        name=payload.name,
        default_route=payload.default_route,
        sort_order=payload.sort_order,
        is_active=True,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get(
    "/departments",
    response_model=List[schemas.DepartmentRead],
    summary="List departments (current AMO by default; any AMO for superuser)",
)
def list_departments(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List departments.

    - Normal users / AMO admins: always scoped to their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to inspect another AMO;
      if omitted, sees departments for their own (ROOT/system) AMO.
    """
    q = db.query(models.Department)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.Department.amo_id == amo_id)
    else:
        q = q.filter(models.Department.amo_id == current_user.amo_id)

    return q.order_by(models.Department.sort_order.asc()).all()


# ---------------------------------------------------------------------------
# USER MANAGEMENT (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/users",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user in current AMO (or any AMO for superuser)",
)
def create_user_admin(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a user.

    - Normal AMO admins: payload.amo_id is forced to their AMO.
    - SUPERUSER: can set any amo_id in payload.
    """
    # Force user to current AMO unless superuser explicitly sets another
    if not current_user.is_superuser:
        payload = payload.copy(update={"amo_id": current_user.amo_id})

    # Check duplicates within the chosen AMO
    existing = (
        db.query(models.User)
        .filter(
            models.User.amo_id == payload.amo_id,
            models.User.email == payload.email,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists in the AMO.",
        )

    user = services.create_user(db, payload)
    return user


@router.get(
    "/users",
    response_model=List[schemas.UserRead],
    summary="List users (current AMO by default; any AMO for superuser)",
)
def list_users_admin(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    List users.

    - Normal AMO admins: see only users in their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to list users for that AMO;
      if omitted, sees users for their own (ROOT/system) AMO.
    """
    q = db.query(models.User)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.User.amo_id == amo_id)
    else:
        q = q.filter(models.User.amo_id == current_user.amo_id)

    return q.order_by(models.User.full_name.asc()).all()


@router.put(
    "/users/{user_id}",
    response_model=schemas.UserRead,
    summary="Update user (scoped to current AMO for admins; any AMO for superuser)",
)
def update_user_admin(
    user_id: str,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Update a user.

    - Normal AMO admins: can only update users in their AMO.
    - SUPERUSER: can update any user by id (no AMO restriction).
    """
    q = db.query(models.User).filter(models.User.id == user_id)
    if not current_user.is_superuser:
        q = q.filter(models.User.amo_id == current_user.amo_id)

    user = q.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not in your AMO.",
        )

    # Only superuser can toggle is_superuser; AMO admin can toggle is_amo_admin
    update_data = payload.model_dump(exclude_unset=True)
    if (
        "is_amo_admin" in update_data
        and not current_user.is_amo_admin
        and not current_user.is_superuser
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot modify is_amo_admin flag.",
        )

    user = services.update_user(db, user, payload)
    return user


# ---------------------------------------------------------------------------
# AUTHORISATIONS (AMO ADMIN / QUALITY MANAGER / SUPERUSER)
# ---------------------------------------------------------------------------


def _require_quality_or_admin(user: models.User) -> models.User:
    """
    Helper gate for authorisation management.

    - SUPERUSER or AMO admin always allowed.
    - QUALITY_MANAGER allowed for their AMO.
    - System/AI accounts are blocked even if flags are set.
    """
    # Again, system/AI accounts must not manage authorisations.
    if getattr(user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot manage authorisations.",
        )

    if user.is_superuser or user.is_amo_admin:
        return user
    if user.role == models.AccountRole.QUALITY_MANAGER:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Quality Manager or AMO Admin required.",
    )


@router.post(
    "/authorisation-types",
    response_model=schemas.AuthorisationTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create authorisation type for an AMO",
)
def create_authorisation_type(
    payload: schemas.AuthorisationTypeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create an authorisation type.

    - Normal admins / QMs: can only create for their AMO.
    - SUPERUSER: can create for any AMO by setting payload.amo_id.
    """
    _require_quality_or_admin(current_user)

    if not current_user.is_superuser and payload.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create authorisation type for another AMO.",
        )

    dup = (
        db.query(models.AuthorisationType)
        .filter(
            models.AuthorisationType.amo_id == payload.amo_id,
            models.AuthorisationType.code == payload.code,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Authorisation code already exists for this AMO.",
        )

    atype = models.AuthorisationType(
        amo_id=payload.amo_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        maintenance_scope=payload.maintenance_scope,
        regulation_reference=payload.regulation_reference,
        can_issue_crs=payload.can_issue_crs,
        requires_dual_sign=payload.requires_dual_sign,
        requires_valid_licence=payload.requires_valid_licence,
        is_active=True,
    )
    db.add(atype)
    db.commit()
    db.refresh(atype)
    return atype


@router.get(
    "/authorisation-types",
    response_model=List[schemas.AuthorisationTypeRead],
    summary="List authorisation types (current AMO by default; any AMO for superuser)",
)
def list_authorisation_types(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List authorisation types.

    - Normal users / admins: see types only for their AMO.
    - SUPERUSER: can optionally pass `amo_id` to view another AMO; if omitted,
      sees types for their own (ROOT/system) AMO.
    """
    q = db.query(models.AuthorisationType)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.AuthorisationType.amo_id == amo_id)
    else:
        q = q.filter(models.AuthorisationType.amo_id == current_user.amo_id)

    return q.order_by(models.AuthorisationType.code.asc()).all()


@router.post(
    "/user-authorisations",
    response_model=schemas.UserAuthorisationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant authorisation to user",
)
def grant_user_authorisation(
    payload: schemas.UserAuthorisationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Grant a specific authorisation type to a user.

    - SUPERUSER: can grant for any AMO as long as user and type share the same AMO.
    - AMO Admin / QM: can only grant within their AMO.
    """
    _require_quality_or_admin(current_user)

    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    atype = (
        db.query(models.AuthorisationType)
        .filter(models.AuthorisationType.id == payload.authorisation_type_id)
        .first()
    )

    if not user or not atype:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User or authorisation type not found.",
        )

    # Ensure user and authorisation type belong to the same AMO
    if user.amo_id != atype.amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User and authorisation type must belong to the same AMO.",
        )

    # Non-superusers must be in the same AMO as the target user/type
    if not current_user.is_superuser and user.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User or authorisation type invalid for this AMO.",
        )

    ua = models.UserAuthorisation(
        user_id=user.id,
        authorisation_type_id=atype.id,
        scope_text=payload.scope_text,
        effective_from=payload.effective_from,
        expires_at=payload.expires_at,
        granted_by_user_id=payload.granted_by_user_id or current_user.id,
    )
    db.add(ua)
    db.commit()
    db.refresh(ua)
    return ua
