"""Govern QMS People authorization cases, reviews, exemptions and permissions.

Revision ID: quality_260922_people_authz
Revises: quality_260920_audit_ref_family
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260922_people_authz"
down_revision = "quality_260920_audit_ref_family"
branch_labels = None
depends_on = None

_TABLES = (
    "quality_appointments",
    "quality_authorization_cases",
    "quality_authorization_case_events",
    "quality_authorization_evidence",
    "quality_authorization_reviews",
    "quality_controlled_exemptions",
)

_CAPABILITIES = {
    "qms.people.view": "Quality people authorization visibility.",
    "qms.authorization.prepare": "Prepare, nominate and submit Quality authorization cases.",
    "qms.authorization.approve": "Record final Quality authorization decisions.",
    "qms.authorization.review": "Record governed periodic Quality authorization reviews.",
    "qms.authorization.exemption.approve": "Approve time-bounded controlled exemptions.",
    "qms.authorization.policy.manage": "Manage Quality authorization policy and rule configuration.",
    "qms.authorization.oversight": "View tenant-wide Quality authorization governance without mutation authority.",
}

_ROLE_CAPABILITIES = {
    "QUALITY_MANAGER": tuple(_CAPABILITIES),
    "AMO_ADMIN": tuple(_CAPABILITIES),
    "QUALITY_OFFICER": ("qms.people.view", "qms.authorization.prepare"),
    "ACCOUNTABLE_EXECUTIVE": ("qms.people.view", "qms.authorization.oversight"),
    "AUDITOR": ("qms.people.view",),
    "QUALITY_INSPECTOR": ("qms.people.view",),
    "QUALITY_SUPPORT_OFFICER": ("qms.people.view",),
    "DOCUMENT_CONTROL_OFFICER": ("qms.people.view",),
    "VIEW_ONLY": ("qms.people.view",),
}


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"

def _decision_type_check_name() -> str | None:
    inspector = sa.inspect(op.get_bind())
    for check in inspector.get_check_constraints("quality_privilege_decisions"):
        sqltext = str(check.get("sqltext") or "").lower()
        if "decision_type" in sqltext:
            name = check.get("name")
            return str(name) if name else None
    return None


def _drop_reflected_constraint(table_name: str, constraint_name: str) -> None:
    """Drop the exact reflected PostgreSQL identifier without reapplying naming conventions."""
    preparer = op.get_bind().dialect.identifier_preparer
    table_sql = preparer.quote_identifier(table_name)
    constraint_sql = preparer.quote_identifier(constraint_name)
    op.execute(sa.text(f"ALTER TABLE {table_sql} DROP CONSTRAINT {constraint_sql}"))



def _enable_rls(table_name: str) -> None:
    if not _postgres():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy}
        ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _postgres():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _append_only(table_name: str) -> None:
    if not _postgres():
        return
    function_name = f"prevent_{table_name}_mutation"
    trigger_name = f"trg_{table_name}_append_only"
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION {function_name}()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '{table_name} is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text(f'DROP TRIGGER IF EXISTS {trigger_name} ON "{table_name}"'))
    op.execute(sa.text(f"""
        CREATE TRIGGER {trigger_name}
        BEFORE UPDATE OR DELETE ON "{table_name}"
        FOR EACH ROW EXECUTE FUNCTION {function_name}();
    """))


def _drop_append_only(table_name: str) -> None:
    if not _postgres():
        return
    op.execute(sa.text(f'DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON "{table_name}"'))
    op.execute(sa.text(f'DROP FUNCTION IF EXISTS prevent_{table_name}_mutation()'))


def _create_capabilities() -> None:
    if not _postgres():
        return
    for index, (code, description) in enumerate(_CAPABILITIES.items(), start=1):
        op.execute(sa.text("""
            INSERT INTO auth_capability_definitions (id, code, module, description)
            VALUES (:id, :code, 'quality', :description)
            ON CONFLICT (code) DO UPDATE
            SET module = 'quality', description = EXCLUDED.description
        """).bindparams(id=f"qms-authz-cap-{index:02d}", code=code, description=description))
    for role, capabilities in _ROLE_CAPABILITIES.items():
        for code in capabilities:
            op.execute(sa.text("""
                INSERT INTO auth_role_capability_bindings
                    (id, role_id, capability_id, constraints_json, created_at)
                SELECT md5(r.id || ':' || c.code), r.id, c.id, '{}', NOW()
                FROM auth_role_definitions r
                JOIN auth_capability_definitions c ON c.code = :code
                WHERE r.base_role_key = :role
                ON CONFLICT (role_id, capability_id) DO NOTHING
            """).bindparams(role=role, code=code))


def upgrade() -> None:
    op.create_table(
        "quality_appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("function_code", sa.String(96), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_until", sa.Date()),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36)),
        sa.Column("updated_by_user_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE','SUPERSEDED')", name="ck_quality_appointment_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_appointments_person", "quality_appointments", ["amo_id", "user_id", "status"])
    op.create_index("ix_quality_appointments_function", "quality_appointments", ["amo_id", "function_code", "status"])

    op.create_table(
        "quality_authorization_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("appointment_id", sa.String(36)),
        sa.Column("current_privilege_id", sa.String(36)),
        sa.Column("requested_rule_id", sa.String(36), nullable=False),
        sa.Column("case_type", sa.String(32), nullable=False, server_default="NEW_AUTHORIZATION"),
        sa.Column("status", sa.String(32), nullable=False, server_default="NOMINATED"),
        sa.Column("requested_scope_key", sa.String(255), nullable=False, server_default="GLOBAL"),
        sa.Column("requested_scope", sa.JSON(), nullable=False),
        sa.Column("nomination_date", sa.Date(), nullable=False),
        sa.Column("nominated_by_user_id", sa.String(36)),
        sa.Column("person_snapshot", sa.JSON(), nullable=False),
        sa.Column("current_authorization_snapshot", sa.JSON(), nullable=False),
        sa.Column("requested_authorization_snapshot", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text()),
        sa.Column("recommendation_by_user_id", sa.String(36)),
        sa.Column("recommendation_at", sa.DateTime(timezone=True)),
        sa.Column("decision", sa.String(32)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("decided_by_user_id", sa.String(36)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("effective_from", sa.Date()),
        sa.Column("expires_on", sa.Date()),
        sa.Column("next_review_due", sa.Date()),
        sa.Column("readiness_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36)),
        sa.Column("updated_by_user_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('NOMINATED','UNDER_REVIEW','DEVELOPMENT','AWAITING_EVIDENCE','READY_FOR_DECISION','RETURNED','APPROVED','REJECTED','CANCELLED')",
            name="ck_quality_authorization_case_status",
        ),
        sa.CheckConstraint(
            "case_type IN ('NEW_AUTHORIZATION','CHANGE_AUTHORIZATION','RENEWAL','REINSTATEMENT')",
            name="ck_quality_authorization_case_type",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["appointment_id"], ["quality_appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_privilege_id"], ["quality_privileges.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_rule_id"], ["quality_privilege_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["nominated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recommendation_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_authorization_cases_queue", "quality_authorization_cases", ["amo_id", "status", "updated_at"])
    op.create_index("ix_quality_authorization_cases_person", "quality_authorization_cases", ["amo_id", "user_id", "created_at"])

    op.create_table(
        "quality_authorization_case_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("previous_status", sa.String(32)),
        sa.Column("new_status", sa.String(32)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_authorization_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_authorization_case_events_history", "quality_authorization_case_events", ["amo_id", "case_id", "occurred_at"])
    op.create_index("ix_quality_authorization_case_events_actor", "quality_authorization_case_events", ["amo_id", "actor_user_id", "occurred_at"])

    op.create_table(
        "quality_authorization_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36)),
        sa.Column("privilege_id", sa.String(36)),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("source_module", sa.String(64)),
        sa.Column("source_reference", sa.JSON(), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("storage_path", sa.Text()),
        sa.Column("content_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("uploaded_by_user_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_type IN ('TRAINING_RECORD','COMPETENCE_ASSESSMENT','PRIOR_AUTHORIZATION','AUDIT_EXPERIENCE','COMPETENCE_PACKAGE','ANNUAL_REVIEW','CONTROLLED_EXEMPTION','APPOINTMENT_LETTER','OTHER')",
            name="ck_quality_authorization_evidence_type",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','SUPERSEDED','VOID')", name="ck_quality_authorization_evidence_status"),
        sa.CheckConstraint("case_id IS NOT NULL OR privilege_id IS NOT NULL", name="ck_quality_authorization_evidence_owner"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_authorization_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["privilege_id"], ["quality_privileges.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_authorization_evidence_case", "quality_authorization_evidence", ["amo_id", "case_id", "created_at"])
    op.create_index("ix_quality_authorization_evidence_privilege", "quality_authorization_evidence", ["amo_id", "privilege_id", "created_at"])

    op.create_table(
        "quality_authorization_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("privilege_id", sa.String(36), nullable=False),
        sa.Column("last_reviewed", sa.Date(), nullable=False),
        sa.Column("next_review_due", sa.Date()),
        sa.Column("review_outcome", sa.String(32), nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(36)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_evidence", sa.JSON(), nullable=False),
        sa.Column("review_notes", sa.Text()),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_outcome IN ('CONTINUE','CONTINUE_WITH_CONDITIONS','SUSPEND','REVOKE','REQUIRES_ACTION')",
            name="ck_quality_authorization_review_outcome",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["privilege_id"], ["quality_privileges.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_authorization_reviews_due", "quality_authorization_reviews", ["amo_id", "next_review_due"])
    op.create_index("ix_quality_authorization_reviews_history", "quality_authorization_reviews", ["amo_id", "privilege_id", "reviewed_at"])

    op.create_table(
        "quality_controlled_exemptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(36)),
        sa.Column("privilege_id", sa.String(36)),
        sa.Column("person_user_id", sa.String(36), nullable=False),
        sa.Column("authorization_type", sa.String(255), nullable=False),
        sa.Column("criterion", sa.String(255), nullable=False),
        sa.Column("reason_normal_compliance_impossible", sa.Text(), nullable=False),
        sa.Column("equivalent_evidence", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("supervision_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("supervisor_user_id", sa.String(36)),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("approved_by_user_id", sa.String(36)),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(36)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED','SUPERSEDED')", name="ck_quality_controlled_exemption_status"),
        sa.CheckConstraint("expires_on >= effective_from", name="ck_quality_controlled_exemption_dates"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_authorization_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["privilege_id"], ["quality_privileges.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["person_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supervisor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_quality_controlled_exemptions_active", "quality_controlled_exemptions", ["amo_id", "status", "expires_on"])
    op.create_index("ix_quality_controlled_exemptions_person", "quality_controlled_exemptions", ["amo_id", "person_user_id", "created_at"])

    for table in _TABLES:
        _enable_rls(table)
    _append_only("quality_authorization_case_events")
    _append_only("quality_authorization_reviews")
    _append_only("quality_privilege_decisions")

    if _postgres():
        decision_type_check = _decision_type_check_name()
        if decision_type_check:
            _drop_reflected_constraint("quality_privilege_decisions", decision_type_check)
        op.create_check_constraint(
            op.f("ck_quality_privilege_decision_type"),
            "quality_privilege_decisions",
            "decision_type IN ('GRANT','RENEW','CHANGE','SUSPEND','REINSTATE','REVOKE','EXPIRE','REJECT')",
        )
        inspector = sa.inspect(op.get_bind())
        for foreign_key in inspector.get_foreign_keys("quality_privilege_decisions"):
            if foreign_key.get("referred_table") == "quality_privileges" and foreign_key.get("constrained_columns") == ["privilege_id"]:
                _drop_reflected_constraint("quality_privilege_decisions", str(foreign_key["name"]))
                break
        op.create_foreign_key(
            op.f("fk_quality_privilege_decisions_privilege_retained"),
            "quality_privilege_decisions",
            "quality_privileges",
            ["privilege_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    _create_capabilities()


def downgrade() -> None:
    if _postgres():
        op.drop_constraint(op.f("fk_quality_privilege_decisions_privilege_retained"), "quality_privilege_decisions", type_="foreignkey")
        op.create_foreign_key(
            op.f("quality_privilege_decisions_privilege_id_fkey"),
            "quality_privilege_decisions",
            "quality_privileges",
            ["privilege_id"],
            ["id"],
            ondelete="CASCADE",
        )
        decision_type_check = _decision_type_check_name()
        if decision_type_check:
            op.drop_constraint(op.f(decision_type_check), "quality_privilege_decisions", type_="check")
        op.create_check_constraint(
            "ck_quality_privilege_decision_type",
            "quality_privilege_decisions",
            "decision_type IN ('GRANT','RENEW','SUSPEND','REINSTATE','REVOKE','EXPIRE','REJECT')",
        )
    _drop_append_only("quality_privilege_decisions")
    _drop_append_only("quality_authorization_reviews")
    _drop_append_only("quality_authorization_case_events")
    for table in reversed(_TABLES):
        _disable_rls(table)

    op.drop_index("ix_quality_controlled_exemptions_person", table_name="quality_controlled_exemptions")
    op.drop_index("ix_quality_controlled_exemptions_active", table_name="quality_controlled_exemptions")
    op.drop_table("quality_controlled_exemptions")
    op.drop_index("ix_quality_authorization_reviews_history", table_name="quality_authorization_reviews")
    op.drop_index("ix_quality_authorization_reviews_due", table_name="quality_authorization_reviews")
    op.drop_table("quality_authorization_reviews")
    op.drop_index("ix_quality_authorization_evidence_privilege", table_name="quality_authorization_evidence")
    op.drop_index("ix_quality_authorization_evidence_case", table_name="quality_authorization_evidence")
    op.drop_table("quality_authorization_evidence")
    op.drop_index("ix_quality_authorization_case_events_actor", table_name="quality_authorization_case_events")
    op.drop_index("ix_quality_authorization_case_events_history", table_name="quality_authorization_case_events")
    op.drop_table("quality_authorization_case_events")
    op.drop_index("ix_quality_authorization_cases_person", table_name="quality_authorization_cases")
    op.drop_index("ix_quality_authorization_cases_queue", table_name="quality_authorization_cases")
    op.drop_table("quality_authorization_cases")
    op.drop_index("ix_quality_appointments_function", table_name="quality_appointments")
    op.drop_index("ix_quality_appointments_person", table_name="quality_appointments")
    op.drop_table("quality_appointments")
