"""merge heads for Reliability diagnostic

Revision ID: rel_20260803_merge_heads_diag
Revises: accounts_20260803_admin_profile, document_control_20260729_ai_assisted_search, foundation_20260731_geofence, p0a7_train_record_dedupe, qms_20260607_read_stability, qms_20260704_car_attach_repair, rostering_20260728_automation_policy, saas_p5_20260501, train_20260627_final
Create Date: 2026-08-03 14:35:37.836608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'rel_20260803_merge_heads_diag'
down_revision: Union[str, Sequence[str], None] = ('accounts_20260803_admin_profile', 'document_control_20260729_ai_assisted_search', 'foundation_20260731_geofence', 'p0a7_train_record_dedupe', 'qms_20260607_read_stability', 'qms_20260704_car_attach_repair', 'rostering_20260728_automation_policy', 'saas_p5_20260501', 'train_20260627_final')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
