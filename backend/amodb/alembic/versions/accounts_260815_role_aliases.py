"""Add canonical KCAR 2025 account roles and migrate exact legacy titles.

Revision ID: accounts_260815_role_aliases
Revises: workforce_260815_hierarchy
Create Date: 2026-08-15
"""
from __future__ import annotations

from alembic import op


revision = "accounts_260815_role_aliases"
down_revision = "workforce_260815_hierarchy"
branch_labels = None
depends_on = None


NEW_ROLE_VALUES = (
    "USER",
    "ACCOUNTABLE_EXECUTIVE",
    "BASE_MAINTENANCE_MANAGER",
    "LINE_MAINTENANCE_MANAGER",
    "WORKSHOP_MANAGER",
)


def _normalised_title_sql() -> str:
    return "UPPER(REGEXP_REPLACE(COALESCE(position_title, ''), '[^A-Za-z0-9]+', '', 'g'))"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for value in NEW_ROLE_VALUES:
                op.execute(f"ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS '{value}'")

        title = _normalised_title_sql()
        mappings = {
            "ACCOUNTABLE_EXECUTIVE": (
                "ACCOUNTABLE", "ACCOUNTABLEEXECUTIVE", "ACCOUNTABLEMANAGER",
                "ACCOUNTABLEPERSON", "AE", "CEO", "CHIEFEXECUTIVEOFFICER",
            ),
            "BASE_MAINTENANCE_MANAGER": (
                "BASEMAINTENANCEMANAGER", "HEADOFBASEMAINTENANCE", "HEADBASEMAINTENANCE",
                "BASEMAINTENANCEHEAD", "HEADOFBASEMAITENANCE", "HEADOFBASEMAINTAINANCE",
                "BMM", "HOBM", "HBM",
            ),
            "LINE_MAINTENANCE_MANAGER": (
                "LINEMAINTENANCEMANAGER", "HEADOFLINEMAINTENANCE", "HEADLINEMAINTENANCE",
                "LINEMAINTENANCEHEAD", "HEADOFLINEMAITENANCE", "HEADOFLINEMAINTAINANCE",
                "LMM", "HOLM", "HLM",
            ),
            "WORKSHOP_MANAGER": (
                "WORKSHOPMANAGER", "HEADOFWORKSHOP", "WORKSHOPHEAD",
                "COMPONENTWORKSHOPMANAGER", "HEADOFCOMPONENTMAINTENANCE", "WM", "HOW",
            ),
            "QUALITY_MANAGER": (
                "QUALITYMANAGER", "HEADOFQUALITY", "QUALITYHEAD",
                "COMPLIANCEMONITORINGMANAGER", "QM", "HOQ",
            ),
            "SAFETY_MANAGER": (
                "SAFETYMANAGER", "HEADOFSAFETY", "SAFETYHEAD", "SM", "HOS",
            ),
        }
        labels = {
            "ACCOUNTABLE_EXECUTIVE": "Accountable Executive",
            "BASE_MAINTENANCE_MANAGER": "Base Maintenance Manager",
            "LINE_MAINTENANCE_MANAGER": "Line Maintenance Manager",
            "WORKSHOP_MANAGER": "Workshop Manager",
            "QUALITY_MANAGER": "Quality Manager",
            "SAFETY_MANAGER": "Safety Manager",
        }
        for role, aliases in mappings.items():
            values = ", ".join(f"'{value}'" for value in aliases)
            op.execute(
                f"""
                UPDATE users
                SET role = '{role}'::account_role_enum,
                    position_title = '{labels[role]}',
                    is_amo_admin = FALSE,
                    is_auditor = FALSE
                WHERE is_superuser = FALSE
                  AND {title} IN ({values})
                """
            )

        # A governed Workforce placement is the authoritative employment
        # position. Keep the account access persona aligned where the hierarchy
        # initializer has already assigned a canonical regulatory role key.
        op.execute(
            """
            UPDATE users AS u
            SET role = wp.role_key::account_role_enum,
                position_title = wp.canonical_title,
                is_amo_admin = FALSE,
                is_auditor = FALSE
            FROM workforce_person_placements AS wpp
            JOIN workforce_positions AS wp ON wp.id = wpp.position_id
            WHERE wpp.user_id = u.id
              AND wpp.amo_id = u.amo_id
              AND wpp.placement_type = 'PRIMARY'
              AND wpp.effective_from <= CURRENT_DATE
              AND (wpp.effective_to IS NULL OR wpp.effective_to >= CURRENT_DATE)
              AND wp.role_key IN (
                  'ACCOUNTABLE_EXECUTIVE', 'BASE_MAINTENANCE_MANAGER',
                  'LINE_MAINTENANCE_MANAGER', 'WORKSHOP_MANAGER',
                  'QUALITY_MANAGER', 'SAFETY_MANAGER'
              )
            """
        )

        # Authorization consumers resolve regulatory responsibility from this
        # table. Backfill it from the newly canonicalized account roles so
        # migrated tenants do not require a second manual appointment step.
        op.execute(
            """
            INSERT INTO auth_postholder_assignments (
                id, amo_id, user_id, postholder_code, status, valid_from, created_at
            )
            SELECT
                md5(u.amo_id || '|' || u.id || '|' || u.role::text),
                u.amo_id,
                u.id,
                u.role::text,
                'ACTIVE',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM users AS u
            WHERE u.amo_id IS NOT NULL
              AND u.is_active = TRUE
              AND u.role::text IN (
                  'ACCOUNTABLE_EXECUTIVE', 'BASE_MAINTENANCE_MANAGER',
                  'LINE_MAINTENANCE_MANAGER', 'WORKSHOP_MANAGER',
                  'QUALITY_MANAGER', 'SAFETY_MANAGER'
              )
            ON CONFLICT (amo_id, postholder_code, user_id) DO UPDATE SET
                status = 'ACTIVE', valid_from = CURRENT_TIMESTAMP, valid_to = NULL
            """
        )

        # Training authorization committees previously used KCAR 2018-style
        # seat codes. Preserve existing cases and decisions under the same
        # canonical postholder keys used by authorization and account access.
        for table_name, column_name in (
            ("training_operating_settings", "default_committee_positions"),
            ("training_authorization_cases", "required_committee_positions"),
        ):
            op.execute(
                f"""
                UPDATE {table_name}
                SET {column_name} = REPLACE(
                    REPLACE(
                        REPLACE({column_name}::text,
                            'HEAD_OF_QUALITY', 'QUALITY_MANAGER'),
                        'HEAD_OF_BASE_MAINTENANCE', 'BASE_MAINTENANCE_MANAGER'),
                    'HEAD_OF_LINE_MAINTENANCE', 'LINE_MAINTENANCE_MANAGER')::json
                WHERE {column_name}::text LIKE '%HEAD_OF_%'
                """
            )
        op.execute(
            """
            UPDATE training_committee_decisions
            SET position_code = CASE position_code
                WHEN 'HEAD_OF_QUALITY' THEN 'QUALITY_MANAGER'
                WHEN 'HEAD_OF_BASE_MAINTENANCE' THEN 'BASE_MAINTENANCE_MANAGER'
                WHEN 'HEAD_OF_LINE_MAINTENANCE' THEN 'LINE_MAINTENANCE_MANAGER'
                ELSE position_code
            END
            WHERE position_code IN (
                'HEAD_OF_QUALITY', 'HEAD_OF_BASE_MAINTENANCE',
                'HEAD_OF_LINE_MAINTENANCE'
            )
            """
        )
        op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'USER'::account_role_enum")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE auth_postholder_assignments
            SET status = 'INACTIVE', valid_to = CURRENT_TIMESTAMP
            WHERE postholder_code IN (
                'ACCOUNTABLE_EXECUTIVE', 'BASE_MAINTENANCE_MANAGER',
                'LINE_MAINTENANCE_MANAGER', 'WORKSHOP_MANAGER'
            )
            """
        )
        op.execute(
            """
            UPDATE users
            SET role = 'USER'::account_role_enum
            WHERE role::text IN (
                'ACCOUNTABLE_EXECUTIVE', 'BASE_MAINTENANCE_MANAGER',
                'LINE_MAINTENANCE_MANAGER', 'WORKSHOP_MANAGER'
            )
            """
        )
        op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'TECHNICIAN'::account_role_enum")
        # PostgreSQL enum labels are intentionally retained: removing labels can
        # invalidate historical audit payloads and requires rebuilding the type.
