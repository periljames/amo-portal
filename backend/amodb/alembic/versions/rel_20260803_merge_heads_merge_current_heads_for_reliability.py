"""Merge the current application heads before installing Reliability scope.

Revision ID: rel_20260803_merge_heads_diag
Revises: accounts_20260803_auth_session, document_control_20260729_ai_assisted_search,
foundation_20260731_geofence, p0a7_train_record_dedupe,
procure_20260803_docs, qms_20260607_read_stability,
qms_20260704_car_attach_repair, rostering_20260728_automation_policy,
saas_p5_20260501, train_20260627_final
Create Date: 2026-08-04
"""
from typing import Sequence, Union


revision: str = "rel_20260803_merge_heads_diag"
down_revision: Union[str, Sequence[str], None] = (
    "accounts_20260803_auth_session",
    "document_control_20260729_ai_assisted_search",
    "foundation_20260731_geofence",
    "p0a7_train_record_dedupe",
    "procure_20260803_docs",
    "qms_20260607_read_stability",
    "qms_20260704_car_attach_repair",
    "rostering_20260728_automation_policy",
    "saas_p5_20260501",
    "train_20260627_final",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge the existing migration branches without changing schema."""
    pass


def downgrade() -> None:
    """Split back to the pre-Reliability heads without changing schema."""
    pass
