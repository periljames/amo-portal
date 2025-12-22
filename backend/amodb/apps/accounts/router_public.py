# backend/amodb/apps/accounts/router_public.py

from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, schemas, services

router = APIRouter(prefix="/auth", tags=["auth"])

RESERVED_PLATFORM_SLUGS = {"", "system", "root"}
RESET_LINK_BASE_URL = (
    os.getenv("PORTAL_BASE_URL")
    or os.getenv("FRONTEND_BASE_URL")
    or ""
).strip()


def _client_ip(request: Request) -> str | None:
    try:
        return request.client.host if request.client else None
    except Exception:
        return None


def _user_agent(request: Request) -> str | None:
    try:
        return request.headers.get("user-agent")
    except Exception:
        return None


def _normalise_amo_slug(amo_slug: str | None) -> str:
    v = (amo_slug or "").strip()
    if v.lower() in RESERVED_PLATFORM_SLUGS:
        return "system"
    return v


def _build_reset_link(*, amo_slug: str, token: str) -> str | None:
    if not RESET_LINK_BASE_URL:
        return None
    base = RESET_LINK_BASE_URL.rstrip("/")
    query = urlencode({"token": token, "amo": amo_slug})
    return f"{base}/reset-password?{query}"


def _maybe_send_email(
    background_tasks: BackgroundTasks,
    to_email: str | None,
    subject: str,
    body: str,
) -> None:
    """
    Optional email hook (safe-by-default).
    If SMTP env vars are not set, this does nothing.

    Env expected:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    """
    if not to_email or not isinstance(to_email, str) or "@" not in to_email:
        return

    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    sender = os.getenv("SMTP_FROM")

    if not (host and port and sender):
        return

    def _send() -> None:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(host, int(port)) as s:
            s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)

    background_tasks.add_task(_send)


def _maybe_send_sms(
    background_tasks: BackgroundTasks,
    to_phone: str | None,
    message: str,
) -> None:
    """
    Optional WhatsApp hook (safe-by-default).
    If WHATSAPP_WEBHOOK_URL is not set, this does nothing.

    Env expected:
      WHATSAPP_WEBHOOK_URL
      WHATSAPP_WEBHOOK_BEARER (optional)
    """
    if not to_phone or not isinstance(to_phone, str):
        return

    url = os.getenv("WHATSAPP_WEBHOOK_URL")
    if not url:
        return

    token = os.getenv("WHATSAPP_WEBHOOK_BEARER")

    def _send() -> None:
        payload = json.dumps({"to": to_phone, "message": message}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=10):
            pass

    background_tasks.add_task(_send)


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
    request: Request,
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
    payload.amo_slug = _normalise_amo_slug(payload.amo_slug)

    try:
        user = services.authenticate_user(
            db=db,
            login_req=payload,
            ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
    except services.AuthenticationError as exc:
        detail = str(exc) or "Incorrect email, password or AMO slug."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
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
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Request a password reset.

    - We do NOT reveal whether the account exists.
    - For now, the raw token is returned in the response for testing.
    - In production you would email the token or a reset link.
    """
    payload.amo_slug = _normalise_amo_slug(payload.amo_slug)

    amo = (
        db.query(models.AMO)
        .filter(
            models.AMO.login_slug == payload.amo_slug,
            models.AMO.is_active.is_(True),
        )
        .first()
    )

    if not amo:
        return {"message": "If the account exists, a reset link will be sent."}

    user = services.get_active_user_by_email(
        db=db,
        amo_id=amo.id,
        email=payload.email,
    )
    if not user:
        return {"message": "If the account exists, a reset link will be sent."}

    raw_token = services.create_password_reset_token(
        db=db,
        user=user,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )

    reset_link = _build_reset_link(amo_slug=payload.amo_slug, token=raw_token)
    delivery = payload.delivery_method
    subject = "Reset your AMO Portal password"
    message = (
        f"Use this link to reset your password: {reset_link}"
        if reset_link
        else f"Use this reset token to set a new password: {raw_token}"
    )

    if delivery in {"email", "both"}:
        _maybe_send_email(background_tasks, getattr(user, "email", None), subject, message)

    if delivery in {"whatsapp", "both"}:
        _maybe_send_whatsapp(
            background_tasks, getattr(user, "phone", None), message
        )
    return {
        "message": "If the account exists, a reset link will be sent.",
        "reset_link": reset_link,
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
    try:
        user = services.redeem_password_reset_token(
            db=db,
            raw_token=payload.token,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
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
    existing_user = db.query(models.User).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Users already exist; bootstrap endpoint is disabled.",
        )

    # Prefer an explicit ROOT/system AMO if it exists; otherwise create it.
    root_amo = (
        db.query(models.AMO)
        .filter(
            (models.AMO.login_slug == "system") | (models.AMO.amo_code == "ROOT")
        )
        .order_by(models.AMO.created_at.asc())
        .first()
    )

    if root_amo is None:
        root_amo = models.AMO(
            amo_code="ROOT",
            name="Platform Root AMO",
            icao_code=None,
            country=None,
            login_slug="system",
            contact_email=payload.email,
            contact_phone=payload.phone,
            time_zone="UTC",
            is_active=True,
        )
        db.add(root_amo)
        db.commit()
        db.refresh(root_amo)

    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
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

    try:
        user = services.create_user(db, user_create)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    user.is_superuser = True
    user.is_amo_admin = True
    db.add(user)
    db.commit()
    db.refresh(user)

    return user
