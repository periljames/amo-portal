from __future__ import annotations

import re

from fastapi import Depends, Request

from amodb.apps.accounts import models as account_models
from amodb.security import get_current_active_user

from .workspace_service import require_control_user


_ENDPOINT_AUTHORIZED_WORKSPACE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "GET",
        re.compile(r"^/doc-control/workspace/t/[^/]+/dashboard/?$"),
    ),
    (
        "GET",
        re.compile(r"^/doc-control/workspace/t/[^/]+/documents/?$"),
    ),
    (
        "GET",
        re.compile(r"^/doc-control/workspace/t/[^/]+/documents/[^/]+/?$"),
    ),
    (
        "GET",
        re.compile(
            r"^/doc-control/workspace/t/[^/]+/documents/[^/]+/read-target/?$"
        ),
    ),
    (
        "GET",
        re.compile(r"^/doc-control/workspace/t/[^/]+/knowledge/tree/?$"),
    ),
    (
        "POST",
        re.compile(r"^/doc-control/workspace/t/[^/]+/knowledge/assist/?$"),
    ),
    (
        "POST",
        re.compile(r"^/doc-control/workspace/t/[^/]+/change-requests/?$"),
    ),
    (
        "POST",
        re.compile(
            r"^/doc-control/workspace/t/[^/]+/distribution-campaigns/[^/]+/acknowledge/?$"
        ),
    ),
    (
        "POST",
        re.compile(
            r"^/doc-control/workspace/t/[^/]+/workflows/[^/]+/transition/?$"
        ),
    ),
)


def enforce_workspace_access(
    request: Request,
    current_user: account_models.User = Depends(get_current_active_user),
) -> None:
    """Apply the coarse controller gate without overriding endpoint authority.

    Reader/library routes and workflow transitions have their own authoritative
    access checks. Workflow transition endpoints use ``require_workflow_action``
    so confirmed technical, Quality and management reviewers can perform only
    their assigned decision while unassigned users still receive 403. Every other
    workspace route remains a governance/control surface and fails closed unless
    the actor has Document Control privileges.
    """
    method = request.method.upper()
    path = request.url.path
    for allowed_method, pattern in _ENDPOINT_AUTHORIZED_WORKSPACE_RULES:
        if method == allowed_method and pattern.fullmatch(path):
            return
    require_control_user(current_user)
