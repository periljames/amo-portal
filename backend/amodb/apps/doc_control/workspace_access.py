from __future__ import annotations

import re

from fastapi import Depends, Request

from amodb.apps.accounts import models as account_models
from amodb.security import get_current_active_user

from .workspace_service import require_control_user


_PUBLIC_WORKSPACE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
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
        "POST",
        re.compile(r"^/doc-control/workspace/t/[^/]+/change-requests/?$"),
    ),
    (
        "POST",
        re.compile(
            r"^/doc-control/workspace/t/[^/]+/distribution-campaigns/[^/]+/acknowledge/?$"
        ),
    ),
)


def enforce_workspace_access(
    request: Request,
    current_user: account_models.User = Depends(get_current_active_user),
) -> None:
    """Protect controller worklists independently of frontend visibility.

    The Library, permitted document detail/read target, reader-originated change
    request, and a recipient's acknowledgement action remain available to normal
    active tenant users. Every other workspace route is a governance/control
    surface and therefore fails closed unless the actor has Document Control
    privileges. Endpoint-specific tenant, document, workflow, and recipient checks
    still run after this coarse route gate.
    """
    method = request.method.upper()
    path = request.url.path
    for allowed_method, pattern in _PUBLIC_WORKSPACE_RULES:
        if method == allowed_method and pattern.fullmatch(path):
            return
    require_control_user(current_user)
