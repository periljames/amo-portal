from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .audit_assignment_permissions import audit_allows_fieldwork_execution
from .router import _current_amo_id, _get_audit_for_amo, _get_finding_for_amo, router


# Legacy audit endpoints pre-date the explicit Lead / Assistant / Supporting /
# Observer duty split and use a broad "audit team" helper for both reads and
# writes. Reads remain available to Observer. These mutation routes must not.
_AUDIT_CONTENT_MUTATIONS: set[tuple[str, str]] = {
    ("POST", "/quality/audits/{audit_id}/document-requests"),
    ("PATCH", "/quality/audits/{audit_id}/document-requests/{request_id}"),
    ("POST", "/quality/audits/{audit_id}/checklist-items"),
    ("PATCH", "/quality/audits/{audit_id}/checklist-items/{item_id}"),
    ("POST", "/quality/audits/{audit_id}/findings"),
    ("PATCH", "/quality/audits/{audit_id}/findings/{finding_id}"),
    ("DELETE", "/quality/audits/{audit_id}/findings/{finding_id}"),
    ("POST", "/quality/audits/{audit_id}/findings/{finding_id}/review-flag"),
    ("POST", "/quality/audits/{audit_id}/fieldwork/complete"),
    ("POST", "/quality/audits/{audit_id}/post-brief"),
    ("POST", "/quality/audits/{audit_id}/archive-package"),
    ("POST", "/quality/audits/{audit_id}/checklist"),
    ("POST", "/quality/audits/{audit_id}/report"),
    ("POST", "/quality/audits/{audit_id}/report/share"),
}

_FINDING_CONTENT_MUTATIONS: set[tuple[str, str]] = {
    ("PATCH", "/quality/findings/{finding_id}"),
    ("DELETE", "/quality/findings/{finding_id}"),
    ("POST", "/quality/findings/{finding_id}/review-flag"),
    ("POST", "/quality/findings/{finding_id}/attachments"),
    ("DELETE", "/quality/findings/{finding_id}/attachments/{attachment_id}"),
    ("POST", "/quality/findings/{finding_id}/close"),
    ("POST", "/quality/findings/{finding_id}/verify"),
}


def _is_observer_only(audit: object, user_id: str | None) -> bool:
    if not user_id:
        return False
    user_key = str(user_id)
    observer_key = str(getattr(audit, "observer_auditor_user_id", None) or "")
    if not observer_key or observer_key != user_key:
        return False
    # Fail safe if legacy data accidentally placed the same person in more than
    # one assignment seat: an executing assignment wins only when it is actually
    # present on the authoritative audit record.
    return not audit_allows_fieldwork_execution(audit, user_key)


def _deny_observer_audit_mutation(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> None:
    audit = _get_audit_for_amo(
        db,
        amo_id=_current_amo_id(current_user),
        audit_id=audit_id,
    )
    if _is_observer_only(audit, getattr(current_user, "id", None)):
        raise HTTPException(
            status_code=403,
            detail=(
                "Observer auditors are read-only participants for this audit. "
                "They may inspect governed audit content but cannot create, edit, "
                "delete, verify, close, distribute, or otherwise author it."
            ),
        )


def _deny_observer_finding_mutation(
    finding_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> None:
    amo_id = _current_amo_id(current_user)
    finding = _get_finding_for_amo(db, amo_id=amo_id, finding_id=finding_id)
    audit = _get_audit_for_amo(db, amo_id=amo_id, audit_id=finding.audit_id)
    if _is_observer_only(audit, getattr(current_user, "id", None)):
        raise HTTPException(
            status_code=403,
            detail=(
                "Observer auditors are read-only participants for this audit and "
                "cannot mutate its findings or finding evidence."
            ),
        )


def _install_guard(route: APIRoute, dependency) -> None:
    marker = f"_qms_observer_guard_{dependency.__name__}"
    if getattr(route, marker, False):
        return
    # APIRoute's request handler closes over this Dependant object. Mutating its
    # dependency list is therefore enough to add the fail-closed guard without
    # replacing endpoint signatures, response models or OpenAPI contracts.
    route.dependant.dependencies.insert(
        0,
        get_dependant(path=route.path_format, call=dependency),
    )
    setattr(route, marker, True)


def install_observer_mutation_guards() -> None:
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        path = str(route.path)
        methods = set(route.methods or ())
        if any((method, path) in _AUDIT_CONTENT_MUTATIONS for method in methods):
            _install_guard(route, _deny_observer_audit_mutation)
        if any((method, path) in _FINDING_CONTENT_MUTATIONS for method in methods):
            _install_guard(route, _deny_observer_finding_mutation)


install_observer_mutation_guards()
