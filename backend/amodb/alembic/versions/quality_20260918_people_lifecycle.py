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
            SELECT md5(r.id || ':qms.training.manage'), r.id, c.id, '{}', NOW()
            FROM auth_role_definitions r CROSS JOIN auth_capability_definitions c
            WHERE r.base_role_key = 'QUALITY_OFFICER' AND c.code = 'qms.training.manage'
            AND EXISTS (SELECT 1 FROM auth_role_capability_bindings b
                JOIN auth_capability_definitions existing ON existing.id = b.capability_id
                WHERE b.role_id = r.id AND existing.code = 'qms.audit.manage')
            ON CONFLICT (role_id, capability_id) DO NOTHING"""))


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""CREATE OR REPLACE FUNCTION prevent_quality_privilege_decisions_mutation()
            RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'quality_privilege_decisions is append-only'; END; $$ LANGUAGE plpgsql"""))
        op.execute(sa.text("""CREATE TRIGGER trg_quality_privilege_decisions_append_only
            BEFORE UPDATE OR DELETE ON quality_privilege_decisions FOR EACH ROW
            EXECUTE FUNCTION prevent_quality_privilege_decisions_mutation()"""))
