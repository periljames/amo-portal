"""Allow tenant-authorised cleanup and rank consolidation of personnel records."""
from alembic import op
import sqlalchemy as sa

revision = "quality_260918_people_lifecycle"
down_revision = "quality_260913_control_trace"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP TRIGGER IF EXISTS trg_quality_privilege_decisions_append_only ON quality_privilege_decisions'))
        op.execute(sa.text('DROP FUNCTION IF EXISTS prevent_quality_privilege_decisions_mutation()'))
        op.execute(sa.text("""INSERT INTO auth_role_capability_bindings
            (id, role_id, capability_id, constraints_json, created_at)
            SELECT md5(r.id || ':' || 'qms.training.manage'), r.id, c.id, '{}', NOW()
            FROM auth_role_definitions r CROSS JOIN auth_capability_definitions c
            WHERE r.base_role_key = 'QUALITY_OFFICER' AND c.code = 'qms.training.manage'
            AND EXISTS (SELECT 1 FROM auth_role_capability_bindings b
                JOIN auth_capability_definitions existing ON existing.id = b.capability_id
                WHERE b.role_id = r.id AND existing.code = 'qms.audit.manage')
            ON CONFLICT (role_id, capability_id) DO NOTHING"""))
        # Development cleanup: keep one live auditor rank per person/scope; revoke extras.
        op.execute(sa.text("""
            WITH ranked AS (
              SELECT p.id, p.amo_id, p.user_id, p.scope_key,
                     ROW_NUMBER() OVER (
                       PARTITION BY p.amo_id, p.user_id, p.scope_key
                       ORDER BY
                         CASE WHEN r.privilege_type = 'LEAD_AUDITOR' THEN 0
                              WHEN COALESCE((r.scope_schema->>'supervised_development')::boolean, false) THEN 2
                              ELSE 1 END,
                         p.updated_at DESC NULLS LAST
                     ) AS keep_rank
              FROM quality_privileges p
              JOIN quality_privilege_rules r ON r.id = p.rule_id AND r.amo_id = p.amo_id
              WHERE p.status IN ('ACTIVE', 'SUSPENDED')
                AND r.privilege_type IN ('AUDITOR', 'LEAD_AUDITOR')
            )
            UPDATE quality_privileges p
            SET status = 'REVOKED', updated_at = NOW()
            FROM ranked
            WHERE p.id = ranked.id AND ranked.keep_rank > 1
        """))


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""CREATE OR REPLACE FUNCTION prevent_quality_privilege_decisions_mutation()
            RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'quality_privilege_decisions is append-only'; END; $$ LANGUAGE plpgsql"""))
        op.execute(sa.text("""CREATE TRIGGER trg_quality_privilege_decisions_append_only
            BEFORE UPDATE OR DELETE ON quality_privilege_decisions FOR EACH ROW
            EXECUTE FUNCTION prevent_quality_privilege_decisions_mutation()"""))
