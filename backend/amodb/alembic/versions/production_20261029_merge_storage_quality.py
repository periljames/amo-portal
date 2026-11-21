"""Reconcile Venspera storage governance with mainline CAR/RCA feedback history.

Two independently deployed branches converge here:
* plat_261026_merge_heads includes external-provider oversight and tenant storage.
* quality_car_feedback_261027 includes RCA, retained actions and feedback.

This revision is intentionally schema-neutral; it establishes a single
ordered Alembic head without reapplying either migration.
"""

revision = "venspera_quality_261029_merge"
down_revision = ("plat_261026_merge_heads", "quality_car_feedback_261027")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
