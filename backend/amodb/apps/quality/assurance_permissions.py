from __future__ import annotations

from .tenant_security import _QUALITY_ROLE_PERMISSIONS


# The Control Centre is the Quality dashboard, so inspectors and auditors must
# be able to read the management-review briefing rendered inside that dashboard.
# These additions are read-only and do not grant approval, evidence verification,
# control management or intelligence-decision permissions.
for _role in ("QUALITY_INSPECTOR", "AUDITOR", "QUALITY_OFFICER"):
    _QUALITY_ROLE_PERMISSIONS.setdefault(_role, set()).update(
        {
            "qms.management_review.view",
            "qms.supplier.view",
            "qms.equipment.view",
            "qms.risk.view",
            "qms.change.view",
            "qms.training.view",
        }
    )
