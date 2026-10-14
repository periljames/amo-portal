"""Phase 4: governed provider qualification, bounded restriction and surveillance links.

Revision ID: extprov_261014_quality
Revises: extprov_261012_partner
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261014_quality"
down_revision = "extprov_261012_partner"
branch_labels = None
depends_on = None


def _identity_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["amo_id", "supplier_id"],
            ["procurement_suppliers.amo_id", "procurement_suppliers.id"],
            ondelete="RESTRICT",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    ]


def upgrade():
    op.create_table(
        "quality_provider_qualification_policies",
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("category", sa.String(64), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("evaluation_template_id", sa.String(36)),
        sa.Column("initial_audit_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authority_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("safety_assessment_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("questionnaire_json", sa.JSON(), nullable=False),
        sa.Column("required_checks_json", sa.JSON(), nullable=False),
        sa.Column("surveillance_days", sa.Integer(), nullable=True),
        sa.Column("manual_references_json", sa.JSON(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="ck_qp_policy_revision"),
        sa.CheckConstraint("surveillance_days IS NULL OR surveillance_days >= 30",
                           name="ck_qp_surveillance_days"),
    )
    op.create_table(
        "quality_provider_qualification_cases",
        *_identity_columns(),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("case_kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(28), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("amo_id", "supplier_id", "id",name="uq_qp_case_tenant_supplier"),
        sa.UniqueConstraint("amo_id","id",name="uq_qp_case_tenant_id"),
        sa.Column("policy_revision", sa.Integer(), nullable=False),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("evaluation_template_id", sa.String(36)),
        sa.Column("answers_json", sa.JSON(), nullable=False),
        sa.Column("evaluation_id", sa.String(64), nullable=True),
        sa.Column("audit_id", sa.String(36), nullable=True),
        sa.Column("technical_state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("safety_state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("authority_state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("technical_actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("safety_actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("authority_reference", sa.String(180)),
        sa.Column("authority_expires_on", sa.Date()),
        sa.Column("technical_scope_json", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("conclusion", sa.Text()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("next_review_due_on", sa.Date()),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("case_kind IN ('INITIAL','RENEWAL','REQUALIFICATION','REINSTATEMENT')",
                           name="ck_qp_case_kind"),
        sa.CheckConstraint("status IN ('DRAFT','SUBMITTED','IN_REVIEW','READY','APPROVED','CONDITIONALLY_APPROVED','REJECTED','RETURNED')",
                           name="ck_qp_case_status"),
        sa.CheckConstraint("technical_state IN ('PENDING','ACCEPTED','REJECTED')",
                           name="ck_qp_technical_state"),
        sa.CheckConstraint("safety_state IN ('PENDING','NOT_REQUIRED','ACCEPTED','REJECTED')",
                           name="ck_qp_safety_state"),
        sa.CheckConstraint("authority_state IN ('PENDING','NOT_REQUIRED','VERIFIED','REJECTED')",
                           name="ck_qp_authority_state"),
        sa.CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')",
                           name="ck_qp_case_risk"),
        sa.CheckConstraint("version >= 1", name="ck_qp_case_version"),
    )
    op.create_index("ix_qp_case_tenant_supplier", "quality_provider_qualification_cases",
                    ["amo_id", "supplier_id", "created_at"])
    op.create_table(
        "quality_provider_qualification_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("requirement_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("evidence_reference", sa.String(255)),
        sa.Column("approval_reference", sa.String(180)),
        sa.Column("expires_on", sa.Date()),
        sa.Column("conclusion", sa.Text()),
        sa.Column("verified_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["amo_id", "case_id"],
            ["quality_provider_qualification_cases.amo_id",
             "quality_provider_qualification_cases.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("case_id", "requirement_key", name="uq_qp_case_check"),
        sa.CheckConstraint("status IN ('PENDING','VERIFIED','REJECTED','NOT_REQUIRED')",
                           name="ck_qp_check_status"),
    )
    op.create_index("ix_qp_check_tenant", "quality_provider_qualification_checks",
                    ["amo_id", "case_id"])
    op.create_table(
        "quality_provider_restrictions",
        *_identity_columns(),
        sa.Column("dimension", sa.String(30), nullable=False),
        sa.Column("target_key", sa.String(180), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date()),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_records_json", sa.JSON(), nullable=False),
        sa.Column("required_cars_json", sa.JSON(), nullable=False),
        sa.Column("reinstatement_case_id", sa.String(36)),
        sa.ForeignKeyConstraint(["amo_id","supplier_id","reinstatement_case_id"],
            ["quality_provider_qualification_cases.amo_id",
             "quality_provider_qualification_cases.supplier_id",
             "quality_provider_qualification_cases.id"]),
        sa.Column("imposed_by_user_id", sa.String(36), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("lifted_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("lifted_at", sa.DateTime(timezone=True)),
        sa.Column("lift_reason", sa.Text()),
        sa.CheckConstraint("dimension IN ('ORGANIZATION','SITE','CATEGORY','CAPABILITY','PRODUCT_FAMILY','FUNCTION','CONTRACT')",
                           name="ck_qp_restriction_dimension"),
        sa.CheckConstraint("status IN ('ACTIVE','LIFTED')", name="ck_qp_restriction_status"),
        sa.CheckConstraint("ends_on IS NULL OR ends_on >= effective_on",
                           name="ck_qp_restriction_dates"),
    )
    op.create_index("ix_qp_restriction_guard", "quality_provider_restrictions",
                    ["amo_id", "supplier_id", "status", "dimension", "target_key"])
    op.create_table(
        "quality_provider_surveillance",
        *_identity_columns(),
        sa.Column("case_id", sa.String(36)),
        sa.ForeignKeyConstraint(["amo_id","supplier_id","case_id"],
            ["quality_provider_qualification_cases.amo_id",
             "quality_provider_qualification_cases.supplier_id",
             "quality_provider_qualification_cases.id"]),
        sa.Column("audit_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("due_on", sa.Date()),
        sa.Column("outcome", sa.String(24), nullable=False, server_default="SCHEDULED"),
        sa.Column("conclusion", sa.Text()),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("amo_id", "supplier_id", "audit_id",
                            name="uq_qp_surveillance_audit"),
        sa.CheckConstraint("kind IN ('INITIAL','RECURRENT','FOLLOW_UP','REQUALIFICATION')",
                           name="ck_qp_surveillance_kind"),
        sa.CheckConstraint("outcome IN ('SCHEDULED','IN_PROGRESS','SATISFACTORY','UNSATISFACTORY','CANCELLED')",
                           name="ck_qp_surveillance_outcome"),
    )
    op.create_table(
        "quality_provider_qualification_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(36)),
        sa.Column("action", sa.String(90), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id", "supplier_id"],
                                ["procurement_suppliers.amo_id", "procurement_suppliers.id"]),
    )
    op.create_index("ix_qp_event_history", "quality_provider_qualification_events",
                    ["amo_id", "supplier_id", "occurred_at"])
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "quality_provider_qualification_policies",
            "quality_provider_qualification_cases",
            "quality_provider_qualification_checks",
            "quality_provider_restrictions",
            "quality_provider_surveillance",
            "quality_provider_qualification_events",
        ):
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f"""CREATE POLICY "{table}_tenant" ON "{table}"
                USING (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))
                WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))"""))
        op.execute(sa.text("""
            CREATE FUNCTION qp_events_append_only() RETURNS trigger
            LANGUAGE plpgsql AS $qpevent$
            BEGIN
                RAISE EXCEPTION 'Qualification events are immutable';
            END;
            $qpevent$;
        """))
        op.execute(sa.text("""CREATE TRIGGER qp_events_immutable
            BEFORE UPDATE OR DELETE ON quality_provider_qualification_events
            FOR EACH ROW EXECUTE FUNCTION qp_events_append_only()"""))


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS qp_events_immutable ON quality_provider_qualification_events")
        op.execute("DROP FUNCTION IF EXISTS qp_events_append_only()")
    for table in (
        "quality_provider_qualification_events",
        "quality_provider_surveillance",
        "quality_provider_restrictions",
        "quality_provider_qualification_checks",
        "quality_provider_qualification_cases",
        "quality_provider_qualification_policies",
    ):
        op.drop_table(table)
