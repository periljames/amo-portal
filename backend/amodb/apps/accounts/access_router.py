"""Tenant role framework and current-user access context endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin
from amodb.apps.audit import services as audit_services

from . import access_control, models, schemas


admin_router = APIRouter(tags=["accounts_access"])
context_router = APIRouter(tags=["accounts_access"])


def _tenant_id(current_user: models.User, requested_amo_id: str | None = None) -> str:
    if requested_amo_id and current_user.is_superuser:
        value = requested_amo_id
    else:
        value = getattr(current_user, "effective_amo_id", None) or current_user.amo_id
    if requested_amo_id and not current_user.is_superuser and str(requested_amo_id) != str(value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant administrators cannot inspect another tenant's access framework.",
        )
    if not value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Select a tenant before managing its access profiles.",
        )
    return str(value)


def _profile_read(db: Session, row: models.AuthRoleDefinition) -> schemas.TenantAccessProfileRead:
    try:
        base_role = models.AccountRole(row.base_role_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Access profile {row.tenant_code or row.id} has an invalid base persona.",
        ) from exc
    return schemas.TenantAccessProfileRead(
        id=str(row.id),
        amo_id=str(row.amo_id),
        code=str(row.tenant_code or row.code),
        display_name=str(row.display_name or row.tenant_code or row.code),
        base_role_key=base_role,
        category=str(row.category or "CUSTOM"),
        reports_to_role_code=row.reports_to_role_code,
        description=row.description,
        is_system=bool(row.is_system),
        is_regulated=bool(row.is_regulated),
        is_editable=bool(row.is_editable),
        is_active=bool(row.is_active),
        version=int(row.version or 1),
        module_permissions=access_control.profile_module_permissions(row),
        assigned_user_count=access_control.profile_assignment_count(db, profile_id=str(row.id)),
    )


def _framework(db: Session, *, amo_id: str) -> schemas.TenantAccessFrameworkRead:
    rows = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.amo_id == amo_id,
    ).options(
        selectinload(models.AuthRoleDefinition.capabilities).selectinload(
            models.AuthRoleCapabilityBinding.capability
        )
    ).order_by(
        models.AuthRoleDefinition.is_regulated.desc(),
        models.AuthRoleDefinition.category.asc(),
        models.AuthRoleDefinition.display_name.asc(),
    ).all()
    return schemas.TenantAccessFrameworkRead(
        modules=[
            schemas.AccessModuleRead(
                code=code, label=label, category=category, description=description
            )
            for code, label, category, description in access_control.MODULE_CATALOGUE
        ],
        profiles=[_profile_read(db, row) for row in rows],
        initialized=bool(rows),
    )


@admin_router.get(
    "/access-framework",
    response_model=schemas.TenantAccessFrameworkRead,
    summary="List tenant access profiles and module catalogue",
)
def get_access_framework(
    amo_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return _framework(db, amo_id=_tenant_id(current_user, amo_id))


@admin_router.post(
    "/access-framework/initialize",
    response_model=schemas.TenantAccessFrameworkInitializeResult,
    summary="Apply the AMO/MRO organization and access-profile framework",
)
def initialize_access_framework(
    amo_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    tenant_id = _tenant_id(current_user, amo_id)
    try:
        outcome = access_control.ensure_tenant_access_profiles(db, amo_id=tenant_id)
        audit_services.log_event(
            db,
            amo_id=tenant_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.access_framework",
            entity_id=tenant_id,
            action="INITIALIZED",
            after=outcome,
            metadata={"module": "accounts", "basis": "KCAR_2025_LN20_AMO_STRUCTURE"},
            critical=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return schemas.TenantAccessFrameworkInitializeResult(**outcome)


@admin_router.post(
    "/access-profiles",
    response_model=schemas.TenantAccessProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tenant access profile",
)
def create_access_profile(
    payload: schemas.TenantAccessProfileCreate,
    amo_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    tenant_id = _tenant_id(current_user, amo_id)
    try:
        row = access_control.create_access_profile(
            db,
            amo_id=tenant_id,
            tenant_code=payload.code,
            display_name=payload.display_name,
            base_role_key=payload.base_role_key.value,
            category=payload.category,
            description=payload.description,
            reports_to_role_code=payload.reports_to_role_code,
            module_permissions=payload.module_permissions,
            actor_user_id=str(current_user.id),
        )
        audit_services.log_event(
            db,
            amo_id=tenant_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.access_profile",
            entity_id=str(row.id),
            action="CREATED",
            after={"code": row.tenant_code, "base_role_key": row.base_role_key},
            metadata={"module": "accounts"},
            critical=True,
        )
        db.commit()
        db.refresh(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return _profile_read(db, row)


@admin_router.put(
    "/access-profiles/{profile_id}",
    response_model=schemas.TenantAccessProfileRead,
    summary="Update tenant terminology and module access",
)
def update_access_profile(
    profile_id: str,
    payload: schemas.TenantAccessProfileUpdate,
    amo_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    tenant_id = _tenant_id(current_user, amo_id)
    row = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.id == profile_id,
        models.AuthRoleDefinition.amo_id == tenant_id,
    ).options(selectinload(models.AuthRoleDefinition.capabilities)).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Access profile not found")
    before = {
        "display_name": row.display_name,
        "base_role_key": row.base_role_key,
        "module_permissions": access_control.profile_module_permissions(row),
        "is_active": row.is_active,
        "version": row.version,
    }
    try:
        row = access_control.update_access_profile(
            db,
            profile=row,
            display_name=payload.display_name,
            description=payload.description,
            category=payload.category,
            reports_to_role_code=payload.reports_to_role_code,
            base_role_key=payload.base_role_key.value if payload.base_role_key else None,
            module_permissions=payload.module_permissions,
            is_active=payload.is_active,
            expected_version=payload.expected_version,
            actor_user_id=str(current_user.id),
            update_fields=set(payload.model_fields_set),
        )
        audit_services.log_event(
            db,
            amo_id=tenant_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.access_profile",
            entity_id=str(row.id),
            action="UPDATED",
            before=before,
            after={
                "display_name": row.display_name,
                "base_role_key": row.base_role_key,
                "module_permissions": access_control.profile_module_permissions(row),
                "is_active": row.is_active,
                "version": row.version,
            },
            metadata={"module": "accounts"},
            critical=True,
        )
        db.commit()
        db.refresh(row)
    except ValueError as exc:
        db.rollback()
        code = status.HTTP_409_CONFLICT if "changed" in str(exc) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return _profile_read(db, row)


@admin_router.put(
    "/users/{user_id}/access-profile",
    response_model=schemas.UserRead,
    summary="Assign a user's primary tenant access profile",
)
def assign_user_access_profile(
    user_id: str,
    payload: schemas.UserAccessProfileAssignment,
    amo_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    tenant_id = _tenant_id(current_user, amo_id)
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.amo_id == tenant_id,
    ).with_for_update().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        profile = access_control.assign_primary_access_profile(
            db,
            user=user,
            profile_id=payload.access_profile_id,
            actor_user_id=str(current_user.id),
        )
        audit_services.log_event(
            db,
            amo_id=tenant_id,
            actor_user_id=str(current_user.id),
            entity_type="accounts.user_access_profile",
            entity_id=str(user.id),
            action="ASSIGNED",
            after={"access_profile_id": profile.id, "base_role_key": profile.base_role_key},
            metadata={"module": "accounts"},
            critical=True,
        )
        db.commit()
        db.refresh(user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return access_control.attach_user_access(db, user)


@context_router.get(
    "/access-profiles",
    response_model=list[schemas.TenantAccessProfileOptionRead],
    summary="List active tenant access profiles for governed selectors",
)
def list_active_access_profiles(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    tenant_id = _tenant_id(current_user)
    rows = db.query(models.AuthRoleDefinition).filter(
        models.AuthRoleDefinition.amo_id == tenant_id,
        models.AuthRoleDefinition.is_active.is_(True),
    ).order_by(
        models.AuthRoleDefinition.category.asc(),
        models.AuthRoleDefinition.display_name.asc(),
        models.AuthRoleDefinition.tenant_code.asc(),
    ).all()
    result: list[schemas.TenantAccessProfileOptionRead] = []
    for row in rows:
        try:
            base_role = models.AccountRole(row.base_role_key)
        except (TypeError, ValueError):
            continue
        if base_role in {models.AccountRole.SUPERUSER, models.AccountRole.AMO_ADMIN}:
            continue
        result.append(schemas.TenantAccessProfileOptionRead(
            id=str(row.id),
            code=str(row.tenant_code or row.code),
            display_name=str(row.display_name or row.tenant_code or row.code),
            base_role_key=base_role,
            category=str(row.category or "CUSTOM"),
            is_regulated=bool(row.is_regulated),
        ))
    return result


@context_router.get(
    "/access-context",
    response_model=schemas.UserAccessContextRead,
    summary="Return the signed-in user's effective tenant access context",
)
def get_access_context(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    access_control.attach_user_access(db, current_user)
    return schemas.UserAccessContextRead(
        user_id=str(current_user.id),
        access_profile_id=getattr(current_user, "access_profile_id", None),
        access_profile_name=str(getattr(current_user, "access_profile_name", None) or current_user.role.value),
        base_role_key=current_user.role,
        is_amo_admin=bool(current_user.is_amo_admin),
        is_superuser=bool(current_user.is_superuser),
        capability_codes=list(getattr(current_user, "capability_codes", [])),
        module_access=dict(getattr(current_user, "module_access", {})),
    )
