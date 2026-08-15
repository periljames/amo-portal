from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from amodb.apps.audit.models import AuditEvent
from amodb.apps.tasks.models import Task, TaskStatus
from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user
from . import models
from .admin_profile_access import active_admin_profile_session


router = APIRouter(prefix="/home", tags=["department_home"])

SUPPORTED_DEPARTMENTS = {
    "planning",
    "production",
    "maintenance",
    "quality",
    "document-control",
    "reliability",
    "safety",
    "stores",
    "workshops",
}

ROLE_DEPARTMENTS: dict[str, set[str]] = {
    "ACCOUNTABLE_EXECUTIVE": {
        "planning", "production", "maintenance", "quality", "document-control",
        "reliability", "safety", "stores", "workshops",
    },
    "BASE_MAINTENANCE_MANAGER": {"production", "maintenance"},
    "LINE_MAINTENANCE_MANAGER": {"production", "maintenance"},
    "WORKSHOP_MANAGER": {"maintenance", "workshops"},
    "PLANNING_ENGINEER": {"planning"},
    "PRODUCTION_ENGINEER": {"production", "maintenance"},
    "CERTIFYING_ENGINEER": {"production", "maintenance"},
    "CERTIFYING_TECHNICIAN": {"production", "maintenance"},
    "TECHNICIAN": {"maintenance"},
    "QUALITY_MANAGER": {"quality", "document-control"},
    "QUALITY_INSPECTOR": {"quality", "document-control"},
    "AUDITOR": {"quality"},
    "SAFETY_MANAGER": {"safety"},
    "STORES": {"stores"},
    "STORES_MANAGER": {"stores"},
    "STOREKEEPER": {"stores"},
    "PROCUREMENT_OFFICER": {"stores"},
}

QUICK_ACTIONS: dict[str, list[tuple[str, str, str]]] = {
    "planning": [
        ("Open forecast", "Review upcoming maintenance exposure", "/planning/forecast-due-list"),
        ("Work packages", "Prepare and control maintenance packages", "/planning/work-packages"),
        ("Compliance actions", "Review AD, SB and compliance work", "/planning/compliance-actions"),
    ],
    "production": [
        ("Control board", "Review active production workload", "/production/control-board"),
        ("Work execution", "Open assigned work orders", "/production/work-order-execution"),
        ("Release preparation", "Review work awaiting release", "/production/release-prep"),
    ],
    "maintenance": [
        ("Work orders", "Open maintenance work", "/maintenance/work-orders"),
        ("Defects", "Review unresolved defects", "/maintenance/defects"),
        ("Inspections", "Open inspection activity", "/maintenance/inspections"),
    ],
    "quality": [
        ("Quality dashboard", "Review current Quality exposure", "/quality"),
        ("Audit programme", "Review audits and schedules", "/quality/audits"),
        ("CAR register", "Review corrective actions", "/quality/cars/register"),
    ],
    "document-control": [
        ("Controlled library", "Open current controlled information", "/document-control/library"),
        ("Drafts", "Review documents in workflow", "/document-control/drafts"),
        ("Review planner", "Review upcoming document reviews", "/document-control/reviews"),
    ],
    "reliability": [
        ("Reliability reports", "Review fleet reliability analysis", "/reliability/reports"),
        ("EHM dashboard", "Review engine health status", "/ehm/dashboard"),
        ("EHM uploads", "Import engine health data", "/ehm/uploads"),
    ],
    "safety": [
        ("Safety operations", "Review assigned safety operations", "/safety/operations"),
        ("Safety configuration", "Review safety workspace configuration", "/safety/settings"),
    ],
    "stores": [
        ("Stores operations", "Review assigned procurement and stores work", "/stores/operations"),
        ("Stores configuration", "Review procurement and stores configuration", "/stores/settings"),
    ],
    "workshops": [
        ("Workshop operations", "Review assigned workshop work", "/workshops/operations"),
        ("Workshop configuration", "Review workshop configuration", "/workshops/settings"),
    ],
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _is_overdue(value: datetime | None, now: datetime) -> bool:
    comparable = _as_utc(value)
    return comparable is not None and comparable < now


def _role(user: models.User) -> str:
    value = getattr(getattr(user, "role", None), "value", getattr(user, "role", ""))
    return str(value or "").upper()


def _normalise_department(value: str | None) -> str | None:
    if not value:
        return None
    normalised = value.strip().lower().replace("_", "-")
    aliases = {
        "doc-control": "document-control",
        "document control": "document-control",
        "procurement": "stores",
        "procurement-stores": "stores",
        "quality-assurance": "quality",
    }
    return aliases.get(normalised, normalised)


def _resolve_amo(db: Session, amo_code: str) -> models.AMO:
    amo = (
        db.query(models.AMO)
        .filter(
            models.AMO.is_active.is_(True),
            or_(models.AMO.amo_code == amo_code, models.AMO.login_slug == amo_code),
        )
        .first()
    )
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO tenant was not found.")
    return amo


def _assert_tenant(user: models.User, amo: models.AMO) -> None:
    if getattr(user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform superusers must use a governed support session.",
        )
    effective_amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if not effective_amo_id or str(effective_amo_id) != str(amo.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this AMO tenant.")


def _admin_profile_active(db: Session, user: models.User, amo: models.AMO) -> bool:
    return active_admin_profile_session(db, user, amo)


def _allowed_departments(db: Session, user: models.User, amo: models.AMO) -> set[str]:
    """Resolve department authorization only from writer-side state."""
    allowed = set(ROLE_DEPARTMENTS.get(_role(user), set()))
    if getattr(user, "department_id", None):
        department = (
            db.query(models.Department)
            .filter(
                models.Department.id == user.department_id,
                models.Department.amo_id == amo.id,
                models.Department.is_active.is_(True),
            )
            .first()
        )
        if department:
            code = _normalise_department(department.code)
            if code:
                allowed.add(code)
    if _admin_profile_active(db, user, amo):
        allowed.update(SUPPORTED_DEPARTMENTS)
    return allowed


def _safe_task_route(task: Task, amo_code: str, department: str) -> str:
    metadata = task.metadata_json if isinstance(task.metadata_json, dict) else {}
    route = metadata.get("route") if isinstance(metadata, dict) else None
    expected_prefix = f"/maintenance/{amo_code}/"
    if not isinstance(route, str) or not route.startswith(expected_prefix):
        return f"/maintenance/{amo_code}/{department}"
    return route


def _task_payload(task: Task, amo_code: str, department: str) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "priority": int(task.priority or 3),
        "status": getattr(task.status, "value", task.status),
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "route": _safe_task_route(task, amo_code, department),
        "entity_type": task.entity_type,
        "entity_id": task.entity_id,
    }


@router.get("/{amo_code}/{department}")
def get_department_home(
    amo_code: str,
    department: str,
    response: Response,
    current_user: models.User = Depends(get_current_active_user),
    authorization_db: Session = Depends(get_db),
    read_db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    # Tenant membership, role, department assignment, grants and profile-session
    # state are authoritative decisions and therefore use the writer. The replica
    # is consulted only after authorization to compose operational payload data.
    amo = _resolve_amo(authorization_db, amo_code)
    _assert_tenant(current_user, amo)
    department_code = _normalise_department(department)
    if not department_code or department_code not in SUPPORTED_DEPARTMENTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department workspace was not found.")
    if department_code not in _allowed_departments(authorization_db, current_user, amo):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Department access is not permitted for this user.")

    now = _utcnow()
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]
    assigned_query = read_db.query(Task).filter(
        Task.amo_id == amo.id,
        Task.owner_user_id == current_user.id,
        Task.status.in_(open_statuses),
    )
    approval_query = read_db.query(Task).filter(
        Task.amo_id == amo.id,
        Task.supervisor_user_id == current_user.id,
        Task.status.in_(open_statuses),
    )
    ordering = (Task.priority.asc(), Task.due_at.is_(None), Task.due_at.asc())
    assigned_total = assigned_query.count()
    approvals_total = approval_query.count()
    assigned = assigned_query.order_by(*ordering).limit(12).all()
    approvals = approval_query.order_by(*ordering).limit(8).all()
    schedule = (
        assigned_query
        .filter(Task.due_at.isnot(None), Task.due_at <= now + timedelta(days=30))
        .order_by(Task.due_at.asc())
        .limit(12)
        .all()
    )
    overdue = assigned_query.filter(Task.due_at.isnot(None), Task.due_at < now).count()
    due_soon = assigned_query.filter(
        Task.due_at.isnot(None),
        and_(Task.due_at >= now, Task.due_at <= now + timedelta(days=7)),
    ).count()
    high_priority = assigned_query.filter(Task.priority <= 2).count()

    recent_activity = (
        read_db.query(AuditEvent)
        .filter(AuditEvent.amo_id == amo.id, AuditEvent.actor_user_id == current_user.id)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(10)
        .all()
    )

    base = f"/maintenance/{amo_code}"
    quick_actions = [
        {"id": f"{department_code}-{index}", "label": label, "description": description, "route": f"{base}{suffix}"}
        for index, (label, description, suffix) in enumerate(QUICK_ACTIONS.get(department_code, []), start=1)
    ]
    alerts = [
        {
            "id": f"overdue-{task.id}",
            "tone": "danger",
            "title": task.title,
            "message": "Assigned task is overdue.",
            "route": _safe_task_route(task, amo_code, department_code),
        }
        for task in assigned
        if _is_overdue(task.due_at, now)
    ][:6]

    response.headers["Cache-Control"] = "private, max-age=20, stale-while-revalidate=120"
    response.headers["Vary"] = "Authorization"
    return {
        "contract": "department-home.v1",
        "amo": {"id": str(amo.id), "code": amo.amo_code, "slug": amo.login_slug, "name": amo.name},
        "department": department_code,
        "generated_at": now.isoformat(),
        "summary": {
            "assigned_open": assigned_total,
            "approvals_open": approvals_total,
            "overdue": overdue,
            "due_soon": due_soon,
            "high_priority": high_priority,
        },
        "alerts": alerts,
        "assigned_work": [_task_payload(task, amo_code, department_code) for task in assigned],
        "approvals": [_task_payload(task, amo_code, department_code) for task in approvals],
        "schedule": [_task_payload(task, amo_code, department_code) for task in schedule],
        "recent_activity": [
            {
                "id": str(event.id),
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in recent_activity
        ],
        "quick_actions": quick_actions,
        "news": [],
        "source_health": {
            "tasks": "healthy",
            "activity": "healthy",
            "news": "not_configured",
        },
    }
