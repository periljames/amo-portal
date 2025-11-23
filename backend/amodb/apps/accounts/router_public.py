# backend/amodb/apps/accounts/router_public.py

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, schemas, services

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# ONE-TIME SUPERUSER CREATION
# ---------------------------------------------------------------------------


@router.post(
    "/first-superuser",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create the very first platform superuser (one-time only)",
)
def create_first_superuser(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    """
    Open endpoint used ONLY on a brand-new system.

    - If ANY user already exists, this returns 403.
    - Creates a SUPERUSER not tied to a specific AMO initially, or you can
      treat this as your first AMO admin by setting amo_id accordingly.

    Frontend: show this form only if the backend reports zero users.
    """
    user_count = db.query(models.User).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser already provisioned.",
        )

    user = services.create_user(db, payload)
    user.is_superuser = True
    user.is_amo_admin = True  # first user can administer initial AMO
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=schemas.Token,
    summary="Login with email/password for a specific AMO slug",
)
def login(
    login_req: schemas.LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Password-based login with:

    - AMO slug (multi-tenant)
    - Email
    - Password

    Includes:
    - lockout after repeated failures,
    - security event logging,
    - JWT with amo_id / department_id / role in payload.
    """
    ip: Optional[str] = request.client.host if request.client else None
    ua: Optional[str] = request.headers.get("User-Agent")

    user = services.authenticate_user(
        db=db,
        login_req=login_req,
        ip=ip,
        user_agent=ua,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or account locked.",
        )

    token, expires_in = services.issue_access_token_for_user(user)

    amo = user.amo
    dept = user.department

    return schemas.Token(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=user,
        amo=amo,
        department=dept,
    )


# ---------------------------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------------------------


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_200_OK,
    summary="Request password reset (email with token is sent)",
)
def request_password_reset(
    payload: schemas.PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Password reset request.

    - Always returns 200 to avoid leaking whether the email exists.
    - If the user exists, a reset token is generated.
    - In production, you must send the token via email (or SMS/SSO).
    """
    ip: Optional[str] = request.client.host if request.client else None
    ua: Optional[str] = request.headers.get("User-Agent")

    user = services.get_user_for_login(
        db=db,
        amo_slug=payload.amo_slug,
        email=payload.email,
    )
    if user and user.is_active:
        raw_token = services.create_password_reset_token(
            db=db,
            user=user,
            ip=ip,
            user_agent=ua,
        )
        # TODO: integrate real email sending.
        # For now, you might log raw_token server-side during dev.

    return {"status": "ok"}


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_200_OK,
    summary="Confirm password reset with token",
)
def confirm_password_reset(
    payload: schemas.PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    """
    Redeem a password reset token and set a new password.

    Returns 400 if token invalid/expired/used.
    """
    user = services.redeem_password_reset_token(
        db=db,
        raw_token=payload.token,
        new_password=payload.new_password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token.",
        )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# CURRENT USER ENDPOINT
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=schemas.UserRead,
    summary="Get current logged-in user",
)
def get_me(
    current_user: models.User = Depends(get_current_active_user),
):
    return current_user
