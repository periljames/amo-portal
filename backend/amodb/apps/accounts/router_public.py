# backend/amodb/apps/accounts/router_public.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, schemas, services

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=schemas.Token,
    summary="Login with AMO slug, email and password",
)
def login(
    payload: schemas.LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Normal login:

    - `amo_slug` = AMO login slug (e.g. `maintenance.safa03`)
    - `email`    = user email
    - `password` = user password

    Special case for global superuser:
    - If `amo_slug` is empty / `system` / `root`, the platform owner
      (SUPERUSER) can log in even if their AMO is the ROOT AMO.
    """
    user = services.authenticate_user(
        db=db,
        login_req=payload,
        ip=None,
        user_agent="swagger-ui",
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email, password or AMO slug.",
        )

    token, expires_in = services.issue_access_token_for_user(user)

    return schemas.Token(
        access_token=token,
        expires_in=expires_in,
        user=user,
        amo=user.amo,
        department=user.department,
    )


# ---------------------------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------------------------


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password reset email",
)
def request_password_reset(
    payload: schemas.PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """
    Request a password reset.

    - We do NOT reveal whether the account exists.
    - For now, the raw token is returned in the response for testing.
    - In production you would email the token or a reset link.
    """
    amo = (
        db.query(models.AMO)
        .filter(
            models.AMO.login_slug == payload.amo_slug,
            models.AMO.is_active.is_(True),
        )
        .first()
    )

    # If AMO or user not found, always return generic 202.
    if not amo:
        return {"message": "If the account exists, a reset email will be sent."}

    user = services.get_active_user_by_email(
        db=db,
        amo_id=amo.id,
        email=payload.email,
    )
    if not user:
        return {"message": "If the account exists, a reset email will be sent."}

    raw_token = services.create_password_reset_token(
        db=db,
        user=user,
        ip=None,
        user_agent="swagger-ui",
    )

    # WARNING: token in response is for development only.
    return {
        "message": "If the account exists, a reset email will be sent.",
        "token_demo_only": raw_token,
    }


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
    summary="Confirm password reset using token",
)
def confirm_password_reset(
    payload: schemas.PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    user = services.redeem_password_reset_token(
        db=db,
        raw_token=payload.token,
        new_password=payload.new_password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )
    return {"message": "Password has been reset successfully."}


# ---------------------------------------------------------------------------
# CURRENT USER
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=schemas.UserRead,
    summary="Get current logged-in user",
)
def read_current_user(
    current_user: models.User = Depends(get_current_active_user),
):
    return current_user


# ---------------------------------------------------------------------------
# BOOTSTRAP: FIRST SUPERUSER
# ---------------------------------------------------------------------------


@router.post(
    "/first-superuser",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Bootstrap first platform superuser",
    description=(
        "Bootstrap endpoint used once when the platform is empty.\n\n"
        "**Behaviour:**\n"
        "- If any user already exists, this endpoint returns **400**.\n"
        "- If no AMO exists, a default `ROOT` AMO is created automatically.\n"
        "- Creates a user with:\n"
        "  - `role = SUPERUSER`\n"
        "  - `is_superuser = True`\n"
        "  - `is_amo_admin = True`\n\n"
        "The caller does NOT supply `amo_id` or licence fields; these are "
        "handled on the server."
    ),
)
def create_first_superuser(
    payload: schemas.FirstSuperuserCreate,
    db: Session = Depends(get_db),
):
    # 1) Ensure there are no users yet
    existing_user = db.query(models.User).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Users already exist; bootstrap endpoint is disabled.",
        )

    # 2) Find (or create) a ROOT AMO for the platform owner
    root_amo = (
        db.query(models.AMO)
        .order_by(models.AMO.created_at.asc())
        .first()
    )
    if root_amo is None:
        root_amo = models.AMO(
            amo_code="ROOT",
            name="Platform Root AMO",
            icao_code=None,
            country=None,
            login_slug="system",  # reserved slug for global superuser login
            contact_email=payload.email,
            contact_phone=payload.phone,
            time_zone="UTC",
            is_active=True,
        )
        db.add(root_amo)
        db.commit()
        db.refresh(root_amo)

    # 3) Build a normal UserCreate with forced SUPERUSER role and ROOT AMO
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()  # <- fixed: call strip(), not .strip
    full_name = (payload.full_name or f"{first_name} {last_name}").strip()

    user_create = schemas.UserCreate(
        email=payload.email,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        role=models.AccountRole.SUPERUSER,
        position_title=payload.position_title or "System Owner",
        phone=payload.phone,
        regulatory_authority=None,
        licence_number=None,
        licence_state_or_country=None,
        licence_expires_on=None,
        amo_id=root_amo.id,
        department_id=None,
        staff_code=payload.staff_code,
        password=payload.password,
    )

    # 4) Use the normal user-creation path (enforces uniqueness, hashing, etc.)
    try:
        user = services.create_user(db, user_create)
    except ValueError as exc:
        # e.g. invalid AMO id (should not normally happen here)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # 5) Elevate flags and save
    user.is_superuser = True
    user.is_amo_admin = True
    db.add(user)
    db.commit()
    db.refresh(user)

    return user
