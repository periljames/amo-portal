"""Align initial Workforce contracts with authoritative personnel hire dates.

Revision ID: workforce_260815_hire_dates
Revises: platform_260815_offline_resilience
"""

from alembic import op


revision = "workforce_260815_hire_dates"
down_revision = "platform_260815_offline_resilience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Imported HireDate values replace the provisional starts used while the
    # Workforce records were seeded. Only the earliest employment period is
    # aligned; later genuine reinstatement/re-employment periods are retained.
    op.execute(
        """
        WITH initial_contracts AS (
            SELECT
                contract.id,
                contract.amo_id,
                contract.user_id,
                ROW_NUMBER() OVER (
                    PARTITION BY contract.amo_id, contract.user_id
                    ORDER BY contract.effective_from ASC, contract.id ASC
                ) AS period_order
            FROM employment_contracts AS contract
        )
        UPDATE employment_contracts AS contract
        SET
            effective_from = profile.hire_date,
            updated_at = CURRENT_TIMESTAMP
        FROM initial_contracts AS initial_period
        JOIN personnel_profiles AS profile
          ON profile.amo_id = initial_period.amo_id
         AND profile.user_id = initial_period.user_id
        WHERE contract.id = initial_period.id
          AND initial_period.period_order = 1
          AND profile.hire_date IS NOT NULL
          AND contract.effective_from IS DISTINCT FROM profile.hire_date
          AND (contract.effective_to IS NULL OR profile.hire_date <= contract.effective_to)
          AND NOT EXISTS (
              SELECT 1
              FROM employment_contracts AS same_start
              WHERE same_start.amo_id = contract.amo_id
                AND same_start.user_id = contract.user_id
                AND same_start.id <> contract.id
                AND same_start.effective_from = profile.hire_date
          )
        """
    )


def downgrade() -> None:
    # The displaced values were provisional placeholders and are intentionally
    # not restored over the authoritative personnel hire dates.
    pass
