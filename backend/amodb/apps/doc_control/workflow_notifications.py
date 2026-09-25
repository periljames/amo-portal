"""Durable, tenant-scoped workflow notifications committed with the document."""
from __future__ import annotations

from amodb.apps.accounts import models as accounts
from amodb.apps.realtime.models import PortalNotification
from amodb.apps.realtime.messaging import _queue_user_event
from amodb.apps.realtime.schemas import RealtimeKind
from .workspace_responsibility_access import workflow_actions_for_user
from .workspace_service import can_read_manual, get_profile


def notify_workflow_progress(db, *, tenant, manual, workflow) -> None:
    profile = get_profile(db, tenant, manual.id)
    users = db.query(accounts.User).filter(
        accounts.User.amo_id == tenant.amo_id,
        accounts.User.is_active.is_(True),
        accounts.User.is_system_account.is_(False),
    ).all()
    state = str(workflow.state)
    title = "Document uploaded — review required" if state == "DRAFT" else f"Document {state.replace('_', ' ').lower()}"
    target = f"/maintenance/{tenant.slug}/document-control/library/{manual.id}?tab=workflow&workflow={workflow.id}"
    for user in users:
        if not can_read_manual(user, profile):
            continue
        if str(user.id) != str(workflow.created_by_user_id) and not workflow_actions_for_user(db, workflow=workflow, user=user):
            continue
        key = f"document-workflow:{workflow.id}:{workflow.version or 1}:{user.id}"
        if db.query(PortalNotification.id).filter(
            PortalNotification.amo_id == tenant.amo_id,
            PortalNotification.user_id == user.id,
            PortalNotification.dedupe_key == key,
        ).first():
            continue
        notification = PortalNotification(
            amo_id=tenant.amo_id, user_id=user.id,
            kind="DOCUMENT_WORKFLOW", title=title,
            body=f"{manual.code} · {manual.title}. Status: {state.replace('_', ' ').lower()}. Open the document to view progress and available actions."[:1000],
            entity_type="document_workflow", entity_id=workflow.id,
            action_url=target, dedupe_key=key,
            metadata_json={"manual_id": manual.id, "revision_id": workflow.revision_id, "state": state},
        )
        db.add(notification)
        db.flush()
        _queue_user_event(
            db, amo_id=tenant.amo_id, user_id=user.id,
            kind=RealtimeKind.NOTIFICATION_CREATED,
            payload={"notification_id": notification.id, "kind": notification.kind},
        )
    db.flush()
