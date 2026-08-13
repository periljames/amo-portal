from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import governance_models as gm
from .workspace_capabilities import document_control_capabilities, reader_capabilities
from .workspace_router import OPEN_CHANGE_STATUSES, OPEN_WORKFLOW_STATES, dashboard as _get_full_dashboard
from .workspace_service import can_read_manual, is_control_user, resolve_tenant, role_value


router = APIRouter(prefix="/workspace", tags=["Document Control Dashboard"])

WORKFLOW_RESPONSIBILITY: dict[str, set[str]] = {
    "TECHNICAL_REVIEW": {"TECHNICAL_REVIEWER"},
    "CORRECTIONS_REQUIRED": {"DOCUMENT_OWNER", "DOCUMENT_CONTROLLER"},
    "TECHNICAL_APPROVED": {"DOCUMENT_CONTROLLER"},
    "QUALITY_REVIEW": {"QUALITY_REVIEWER"},
    "QUALITY_APPROVED": {"DOCUMENT_CONTROLLER"},
    "ACCOUNTABLE_MANAGER_APPROVAL": {"APPROVER", "ACCOUNTABLE_ROLE"},
    "AUTHORITY_SUBMITTED": {"DOCUMENT_CONTROLLER"},
    "AUTHORITY_APPROVED": {"DOCUMENT_CONTROLLER"},
    "SCHEDULED_FOR_EFFECTIVITY": {"DOCUMENT_CONTROLLER"},
}


def _reader_dashboard(
    db: Session,
    *,
    tenant_slug: str,
    current_user: account_models.User,
) -> dict:
    tenant = resolve_tenant(db, tenant_slug, current_user)
    candidates = (
        db.query(manual_models.Manual, dm.DocumentControlProfile)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant.amo_id),
        )
        .filter(manual_models.Manual.tenant_id == tenant.id)
        .all()
    )
    visible = [manual for manual, profile in candidates if can_read_manual(current_user, profile)]
    effective = [manual for manual in visible if manual.current_published_rev_id is not None]
    metrics = {
        "document_records": len(visible),
        "revision_records": len(effective),
        "draft_revisions": 0,
        "effective_publications": len(effective),
        "open_change_requests": 0,
        "active_workflows": 0,
        "authority_pending": 0,
        "temporary_revisions_in_force": 0,
        "temporary_revisions_expiring_30_days": 0,
        "pending_acknowledgements": 0,
        "overdue_acknowledgements": 0,
        "reviews_due_60_days": 0,
        "external_currency_checks_due": 0,
        "issued_controlled_copies": 0,
        "control_profiles_missing": 0,
        "document_owners_unassigned": 0,
        "review_dates_missing": 0,
        "documents_without_effective_issue": 0,
        "critical_acknowledgement_gaps": 0,
    }
    return {
        "default_workspace": "LIBRARY",
        "capabilities": reader_capabilities(),
        "metrics": metrics,
        "recent_activity": [],
    }


def _controller_control_gaps(
    db: Session,
    *,
    tenant: manual_models.Tenant,
) -> dict[str, int]:
    """Return evidence-control gaps without exposing them to ordinary readers."""
    profiles_missing = (
        db.query(manual_models.Manual)
        .outerjoin(
            dm.DocumentControlProfile,
            (dm.DocumentControlProfile.manual_id == manual_models.Manual.id)
            & (dm.DocumentControlProfile.tenant_id == tenant.amo_id),
        )
        .filter(manual_models.Manual.tenant_id == tenant.id, dm.DocumentControlProfile.id.is_(None))
        .count()
    )
    owners_unassigned = (
        db.query(dm.DocumentControlProfile)
        .filter(dm.DocumentControlProfile.tenant_id == tenant.amo_id, dm.DocumentControlProfile.owner_user_id.is_(None))
        .count()
    )
    review_dates_missing = (
        db.query(dm.DocumentControlProfile)
        .filter(dm.DocumentControlProfile.tenant_id == tenant.amo_id, dm.DocumentControlProfile.next_review_due.is_(None))
        .count()
    )
    documents_without_effective_issue = (
        db.query(manual_models.Manual)
        .filter(manual_models.Manual.tenant_id == tenant.id, manual_models.Manual.current_published_rev_id.is_(None))
        .count()
    )
    critical_acknowledgement_gaps = (
        db.query(dm.DocumentControlProfile)
        .filter(
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.criticality == "CRITICAL",
            dm.DocumentControlProfile.acknowledgement_required.is_(False),
        )
        .count()
    )
    return {
        "control_profiles_missing": profiles_missing,
        "document_owners_unassigned": owners_unassigned,
        "review_dates_missing": review_dates_missing,
        "documents_without_effective_issue": documents_without_effective_issue,
        "critical_acknowledgement_gaps": critical_acknowledgement_gaps,
    }


def _responsibilities_for_user(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    current_user: account_models.User,
) -> dict[str, set[str]]:
    today = date.today()
    role = role_value(current_user)
    role_aliases = {role, role.replace("_", " "), role.replace("_", " ").title()}
    assignee_conditions = [gm.DocumentResponsibilityAssignment.assignee_user_id == current_user.id]
    if current_user.department_id:
        assignee_conditions.append(gm.DocumentResponsibilityAssignment.assignee_department_id == current_user.department_id)
    if role:
        assignee_conditions.append(gm.DocumentResponsibilityAssignment.assignee_role.in_(sorted(role_aliases)))

    assignments = (
        db.query(gm.DocumentResponsibilityAssignment)
        .filter(
            gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
            gm.DocumentResponsibilityAssignment.confirmation_status == "CONFIRMED",
            gm.DocumentResponsibilityAssignment.effective_from <= today,
            or_(
                gm.DocumentResponsibilityAssignment.effective_to.is_(None),
                gm.DocumentResponsibilityAssignment.effective_to >= today,
            ),
            or_(*assignee_conditions),
        )
        .all()
    )
    by_manual: dict[str, set[str]] = {}
    for assignment in assignments:
        by_manual.setdefault(assignment.manual_id, set()).add(assignment.responsibility_type)
    return by_manual


def _readable_document_labels(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    current_user: account_models.User,
    manual_ids: set[str],
) -> dict[str, dict[str, str]]:
    if not manual_ids:
        return {}
    profiles = {
        row.manual_id: row
        for row in db.query(dm.DocumentControlProfile).filter(
            dm.DocumentControlProfile.tenant_id == tenant.amo_id,
            dm.DocumentControlProfile.manual_id.in_(manual_ids),
        ).all()
    }
    result: dict[str, dict[str, str]] = {}
    for manual in db.query(manual_models.Manual).filter(
        manual_models.Manual.tenant_id == tenant.id,
        manual_models.Manual.id.in_(manual_ids),
    ).all():
        if can_read_manual(current_user, profiles.get(manual.id)):
            result[manual.id] = {"id": manual.id, "code": manual.code, "title": manual.title}
    return result


def _without_internal_sort(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "_sort_at"}


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _date_sort(value: date | None) -> datetime | None:
    return datetime.combine(value, datetime.min.time()) if value else None


def _my_work(
    db: Session,
    *,
    tenant_slug: str,
    current_user: account_models.User,
) -> list[dict[str, Any]]:
    """Return bounded work attributable to the current user.

    Tenant totals are deliberately excluded. Tasks enter this queue only when
    ownership/custody is explicit or a confirmed responsibility assignment maps
    the current workflow decision to the user, their department, or their role.
    """
    tenant = resolve_tenant(db, tenant_slug, current_user)
    now = datetime.utcnow()
    today = date.today()
    tasks: list[dict[str, Any]] = []
    manual_ids: set[str] = set()

    changes = (
        db.query(dm.DocumentChangeRequest)
        .filter(
            dm.DocumentChangeRequest.tenant_id == tenant.amo_id,
            dm.DocumentChangeRequest.owner_user_id == current_user.id,
            dm.DocumentChangeRequest.status.in_(OPEN_CHANGE_STATUSES),
        )
        .order_by(dm.DocumentChangeRequest.due_at.asc().nullslast(), dm.DocumentChangeRequest.updated_at.desc())
        .limit(20)
        .all()
    )
    for row in changes:
        manual_ids.add(row.manual_id)
        due = _naive(row.due_at)
        tasks.append({
            "id": f"change:{row.id}",
            "kind": "CHANGE_REQUEST",
            "manual_id": row.manual_id,
            "entity_id": row.id,
            "title": row.title,
            "status": row.status,
            "priority": "OVERDUE" if due and due < now else row.priority,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "action_label": "Review change",
            "target_path": f"/maintenance/{tenant_slug}/document-control/change-proposals/{row.id}",
            "_sort_at": due,
        })

    reviews = (
        db.query(dm.DocumentReviewPlan)
        .filter(
            dm.DocumentReviewPlan.tenant_id == tenant.amo_id,
            dm.DocumentReviewPlan.owner_user_id == current_user.id,
            dm.DocumentReviewPlan.status.in_(["SCHEDULED", "IN_PROGRESS"]),
        )
        .order_by(dm.DocumentReviewPlan.due_at.asc())
        .limit(20)
        .all()
    )
    for row in reviews:
        manual_ids.add(row.manual_id)
        due = _naive(row.due_at)
        tasks.append({
            "id": f"review:{row.id}",
            "kind": "PERIODIC_REVIEW",
            "manual_id": row.manual_id,
            "entity_id": row.id,
            "title": "Periodic document review",
            "status": row.status,
            "priority": "OVERDUE" if due and due < now else "DUE",
            "due_at": row.due_at.isoformat(),
            "action_label": "Open review",
            "target_path": f"/maintenance/{tenant_slug}/document-control/library/{row.manual_id}?tab=compliance#document-control-record-actions",
            "_sort_at": due,
        })

    acknowledgements = (
        db.query(dm.DocumentDistributionRecipient, dm.DocumentDistributionCampaign)
        .join(dm.DocumentDistributionCampaign, dm.DocumentDistributionCampaign.id == dm.DocumentDistributionRecipient.campaign_id)
        .filter(
            dm.DocumentDistributionRecipient.tenant_id == tenant.amo_id,
            dm.DocumentDistributionRecipient.recipient_user_id == current_user.id,
            dm.DocumentDistributionRecipient.status == "PENDING",
        )
        .order_by(dm.DocumentDistributionRecipient.due_at.asc().nullslast())
        .limit(20)
        .all()
    )
    for recipient, campaign in acknowledgements:
        manual_ids.add(campaign.manual_id)
        due = _naive(recipient.due_at)
        tasks.append({
            "id": f"acknowledgement:{recipient.id}",
            "kind": "ACKNOWLEDGEMENT",
            "manual_id": campaign.manual_id,
            "entity_id": recipient.id,
            "title": campaign.title,
            "status": recipient.status,
            "priority": "OVERDUE" if due and due < now else "DUE",
            "due_at": recipient.due_at.isoformat() if recipient.due_at else campaign.due_at.isoformat() if campaign.due_at else None,
            "action_label": "Read and acknowledge",
            "target_path": f"/maintenance/{tenant_slug}/publications/{campaign.manual_id}/rev/{campaign.revision_id}/read",
            "_sort_at": due,
        })

    authority_rows = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            dm.DocumentAuthoritySubmission.submitted_by_user_id == current_user.id,
            dm.DocumentAuthoritySubmission.status.in_(["SUBMITTED", "IN_REVIEW", "QUERY_RECEIVED"]),
        )
        .order_by(dm.DocumentAuthoritySubmission.response_due_at.asc().nullslast(), dm.DocumentAuthoritySubmission.updated_at.asc())
        .limit(20)
        .all()
    )
    for row in authority_rows:
        manual_ids.add(row.manual_id)
        due = _naive(row.response_due_at)
        query_received = row.status == "QUERY_RECEIVED"
        tasks.append({
            "id": f"authority:{row.id}",
            "kind": "AUTHORITY_ACTION",
            "manual_id": row.manual_id,
            "entity_id": row.id,
            "title": "Authority query requires response" if query_received else f"Authority submission {row.submission_reference}",
            "status": row.status,
            "priority": "OVERDUE" if due and due < now else "ACTION" if query_received else "DUE",
            "due_at": row.response_due_at.isoformat() if row.response_due_at else None,
            "action_label": "Answer authority query" if query_received else "Track authority response",
            "target_path": f"/maintenance/{tenant_slug}/document-control/library/{row.manual_id}?tab=workflow#document-control-record-actions",
            "_sort_at": due,
        })

    temporary_revisions = (
        db.query(dm.DocumentTemporaryRevision)
        .filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
            dm.DocumentTemporaryRevision.created_by_user_id == current_user.id,
            dm.DocumentTemporaryRevision.status.in_(["DRAFT", "IN_REVIEW", "APPROVED", "IN_FORCE", "EXPIRED"]),
        )
        .order_by(dm.DocumentTemporaryRevision.expiry_date.asc())
        .limit(20)
        .all()
    )
    for row in temporary_revisions:
        manual_ids.add(row.manual_id)
        due = _date_sort(row.expiry_date)
        overdue = row.expiry_date < today and row.status in {"IN_FORCE", "EXPIRED"}
        tasks.append({
            "id": f"temporary-revision:{row.id}",
            "kind": "TEMPORARY_REVISION",
            "manual_id": row.manual_id,
            "entity_id": row.id,
            "title": f"TR {row.tr_number} · {row.title}",
            "status": row.status,
            "priority": "OVERDUE" if overdue else "ACTION" if row.status != "IN_FORCE" else "DUE",
            "due_at": row.expiry_date.isoformat(),
            "action_label": "Incorporate / withdraw" if row.status in {"IN_FORCE", "EXPIRED"} else "Continue TR",
            "target_path": f"/maintenance/{tenant_slug}/document-control/library/{row.manual_id}?tab=changes#document-control-record-actions",
            "_sort_at": due,
        })

    controlled_copies = (
        db.query(dm.DocumentControlledCopy)
        .filter(
            dm.DocumentControlledCopy.tenant_id == tenant.amo_id,
            dm.DocumentControlledCopy.holder_user_id == current_user.id,
            dm.DocumentControlledCopy.status.in_(["ISSUED", "RECALLED"]),
        )
        .order_by(dm.DocumentControlledCopy.due_back_at.asc().nullslast(), dm.DocumentControlledCopy.issued_at.asc())
        .limit(20)
        .all()
    )
    for row in controlled_copies:
        manual_ids.add(row.manual_id)
        due = _naive(row.due_back_at)
        tasks.append({
            "id": f"controlled-copy:{row.id}",
            "kind": "CONTROLLED_COPY",
            "manual_id": row.manual_id,
            "entity_id": row.id,
            "title": f"Controlled copy {row.copy_number}",
            "status": row.status,
            "priority": "OVERDUE" if due and due < now else "ACTION" if row.status == "RECALLED" else "DUE",
            "due_at": row.due_back_at.isoformat() if row.due_back_at else None,
            "action_label": "Return recalled copy" if row.status == "RECALLED" else "Open copy custody",
            "target_path": f"/maintenance/{tenant_slug}/document-control/controlled-copies?copy={row.id}",
            "_sort_at": due,
        })

    responsibilities = _responsibilities_for_user(db, tenant=tenant, current_user=current_user)
    if responsibilities:
        workflows = (
            db.query(dm.DocumentWorkflowInstance)
            .filter(
                dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
                dm.DocumentWorkflowInstance.manual_id.in_(set(responsibilities)),
                dm.DocumentWorkflowInstance.state.in_(OPEN_WORKFLOW_STATES),
            )
            .order_by(dm.DocumentWorkflowInstance.updated_at.asc())
            .limit(50)
            .all()
        )
        for row in workflows:
            required = WORKFLOW_RESPONSIBILITY.get(row.state)
            if not required or not required.intersection(responsibilities.get(row.manual_id, set())):
                continue
            manual_ids.add(row.manual_id)
            tasks.append({
                "id": f"workflow:{row.id}",
                "kind": "WORKFLOW_DECISION",
                "manual_id": row.manual_id,
                "entity_id": row.id,
                "title": f"{row.state.replace('_', ' ').title()} decision",
                "status": row.state,
                "priority": "ACTION",
                "due_at": None,
                "action_label": "Open workflow",
                "target_path": f"/maintenance/{tenant_slug}/document-control/library/{row.manual_id}?tab=workflow#document-control-record-actions",
                "_sort_at": None,
            })

    labels = _readable_document_labels(
        db,
        tenant=tenant,
        current_user=current_user,
        manual_ids=manual_ids,
    )
    visible = [task for task in tasks if task["manual_id"] in labels]
    visible.sort(key=lambda task: (task.get("_sort_at") is None, task.get("_sort_at") or datetime.max, task["kind"], task["id"]))
    return [{**_without_internal_sort(task), "document": labels[task["manual_id"]]} for task in visible[:30]]


@router.get("/t/{tenant_slug}/my-work")
def get_my_document_work(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return {"items": _my_work(db, tenant_slug=tenant_slug, current_user=current_user), "limit": 30}


@router.get("/t/{tenant_slug}/dashboard", include_in_schema=False)
def get_role_appropriate_dashboard(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return operational metrics only to Document Control personnel.

    Reader metrics are calculated directly from documents visible to that user.
    Restricted-document counts and controller activity are never loaded into a
    reader response and cannot be inferred from tenant-wide totals.
    """
    if not is_control_user(current_user):
        return _reader_dashboard(db, tenant_slug=tenant_slug, current_user=current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    dashboard = _get_full_dashboard(tenant_slug=tenant_slug, db=db, current_user=current_user)
    dashboard["capabilities"] = document_control_capabilities(current_user)
    dashboard["metrics"].update(_controller_control_gaps(db, tenant=tenant))
    return dashboard
