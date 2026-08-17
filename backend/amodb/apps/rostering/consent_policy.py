from __future__ import annotations

from . import consent_service

_INSTALLED = False


def install_service_policy(service_module) -> None:
    """Attach consent governance to canonical roster mutations and lifecycle.

    This compatibility seam is intentionally installed once in application_router,
    alongside the existing roster-control/version-copy policies. It means REST,
    bulk generation and other callers using the public services facade cannot
    bypass acknowledgement generation or final workflow gating.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    original_create = service_module.create_assignment
    original_update = service_module.update_assignment
    original_delete = service_module.delete_assignment
    original_bulk = service_module.bulk_create_assignments
    original_submit = service_module.submit_version
    original_approve = service_module.approve_version
    original_publish = service_module.publish_version

    def create_assignment(db, *, version, actor_user_id: str, payload):
        row = original_create(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        consent_service.sync_assignment_consent(
            db,
            assignment=row,
            actor_user_id=actor_user_id,
            reason=getattr(payload, "change_reason", None),
        )
        return row

    def update_assignment(db, *, row, actor_user_id: str, payload):
        updated = original_update(
            db,
            row=row,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        consent_service.sync_assignment_consent(
            db,
            assignment=updated,
            actor_user_id=actor_user_id,
            reason=getattr(payload, "change_reason", None),
        )
        return updated

    def delete_assignment(db, *, row, actor_user_id: str, payload):
        result = original_delete(
            db,
            row=row,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        consent_service.sync_assignment_consent(
            db,
            assignment=row,
            actor_user_id=actor_user_id,
            reason=getattr(payload, "reason", None),
        )
        return result

    def bulk_create_assignments(db, *, version, actor_user_id: str, payload):
        result = original_bulk(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        created_ids = [getattr(item, "id", None) for item in getattr(result, "created", [])]
        if created_ids:
            from . import models

            rows = db.query(models.RosterAssignment).filter(
                models.RosterAssignment.amo_id == version.amo_id,
                models.RosterAssignment.version_id == version.id,
                models.RosterAssignment.id.in_([item for item in created_ids if item]),
            ).all()
            for assignment in rows:
                consent_service.sync_assignment_consent(
                    db,
                    assignment=assignment,
                    actor_user_id=actor_user_id,
                )
        return result

    def submit_version(db, *, version, actor_user_id: str, payload):
        consent_service.assert_version_ready(
            db,
            version=version,
            actor_user_id=actor_user_id,
        )
        return original_submit(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    def approve_version(db, *, version, actor_user_id: str, payload):
        consent_service.assert_version_ready(
            db,
            version=version,
            actor_user_id=actor_user_id,
        )
        return original_approve(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    def publish_version(db, *, version, actor_user_id: str, payload):
        consent_service.assert_version_ready(
            db,
            version=version,
            actor_user_id=actor_user_id,
        )
        return original_publish(
            db,
            version=version,
            actor_user_id=actor_user_id,
            payload=payload,
        )

    service_module.create_assignment = create_assignment
    service_module.update_assignment = update_assignment
    service_module.delete_assignment = delete_assignment
    service_module.bulk_create_assignments = bulk_create_assignments
    service_module.submit_version = submit_version
    service_module.approve_version = approve_version
    service_module.publish_version = publish_version
    _INSTALLED = True


__all__ = ["install_service_policy"]
