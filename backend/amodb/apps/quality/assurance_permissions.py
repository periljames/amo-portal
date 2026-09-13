from __future__ import annotations

from amodb.apps.accounts import access_control as _access_control
from amodb.apps.accounts import models as _account_models

from . import tenant_security as _tenant_security
from .tenant_security import _QUALITY_ROLE_PERMISSIONS


# The Control Centre is the Quality dashboard, so inspectors and auditors must
# be able to read the management-review briefing and the governed supporting
# workspaces rendered inside that dashboard. These additions are read-only and
# do not grant approval, evidence verification, control management or
# intelligence-decision permissions.
_CONTROL_CENTRE_READ_PERMISSIONS = frozenset(
    {
        "qms.management_review.view",
        "qms.supplier.view",
        "qms.equipment.view",
        "qms.risk.view",
        "qms.change.view",
        "qms.training.view",
    }
)

for _role in ("QUALITY_INSPECTOR", "AUDITOR", "QUALITY_OFFICER"):
    _QUALITY_ROLE_PERMISSIONS.setdefault(_role, set()).update(
        _CONTROL_CENTRE_READ_PERMISSIONS
    )

# Keep newly created/reconciled tenant access profiles aligned with the same
# role policy. The access framework consumes this constant when it repairs the
# system Auditor and Quality Inspector profiles.
_access_control.QUALITY_AUDITOR_CAPABILITIES = frozenset(
    set(_access_control.QUALITY_AUDITOR_CAPABILITIES)
    | set(_CONTROL_CENTRE_READ_PERMISSIONS)
)


# Existing tenants can carry a primary Auditor/Inspector profile created before
# the six read bindings above were introduced. A primary profile is normally
# authoritative and fail-closed. For this deliberately mandatory read-only
# supplement only, allow the role policy to bridge an unreconciled historical
# profile until ensure_tenant_access_profiles repairs its bindings. Mutating
# permissions never use this bridge.
if not getattr(_tenant_security, "_assurance_read_alignment_installed", False):
    _original_has_capability_permission = _tenant_security._has_capability_permission

    def _aligned_has_capability_permission(
        db,
        *,
        amo_id: str,
        user_id: str,
        permission: str,
    ):
        result = _original_has_capability_permission(
            db,
            amo_id=amo_id,
            user_id=user_id,
            permission=permission,
        )
        if result is not False or permission not in _CONTROL_CENTRE_READ_PERMISSIONS:
            return result

        user = db.query(_account_models.User).filter(
            _account_models.User.id == user_id,
            _account_models.User.amo_id == amo_id,
            _account_models.User.is_active.is_(True),
        ).first()
        role_value = getattr(getattr(user, "role", None), "value", getattr(user, "role", None))
        if role_value in {"QUALITY_INSPECTOR", "AUDITOR"}:
            # None intentionally asks tenant_security to use the aligned role
            # fallback. It is not an unconditional capability grant.
            return None
        return result

    _tenant_security._has_capability_permission = _aligned_has_capability_permission
    _tenant_security._assurance_read_alignment_installed = True
