"""Phase 5: provider evidence requirements, immutable history and governed document links.

Revision ID: extprov_261015_docs
Revises: extprov_261014_quality

Provider submissions remain staging; DMS and QMS retain their own decisions.
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261015_docs"
down_revision = "extprov_261014_quality"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_provider_document_requirements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider_kind", sa.String(32), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledgement_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expiry_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("form_manual_id", sa.String(36), sa.ForeignKey("manuals.id", ondelete="RESTRICT")),
        sa.Column("form_revision_id", sa.String(36), sa.ForeignKey("manual_revisions.id", ondelete="RESTRICT")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retention_policy_ref", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "provider_kind", "code", name="uq_ext_doc_req_tenant_kind_code"),
        sa.UniqueConstraint("amo_id", "id", name="uq_ext_doc_req_tenant_id"),
        sa.CheckConstraint("version >= 1", name="ck_ext_doc_req_version"),
        sa.CheckConstraint("reminder_days BETWEEN 0 AND 365", name="ck_ext_doc_req_reminder_days"),
        sa.CheckConstraint("provider_kind IN ('ALL','SUPPLIER','CONTRACTOR','SUBCONTRACTOR','SERVICE_PROVIDER','CONSULTANT','LABORATORY','CALIBRATION_PROVIDER','OTHER')", name="ck_ext_doc_req_kind"),
        sa.CheckConstraint("(form_manual_id IS NULL) = (form_revision_id IS NULL)", name="ck_ext_doc_req_form_pair"),
    )
    op.create_index("ix_ext_doc_req_tenant_kind", "external_provider_document_requirements", ["amo_id", "provider_kind", "enabled"])
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.add_column(sa.Column("requirement_id", sa.String(36)))
        batch.add_column(sa.Column("supersedes_submission_id", sa.String(36)))
        batch.add_column(sa.Column("form_revision_id", sa.String(36)))
        batch.add_column(sa.Column("valid_until", sa.Date()))
        batch.add_column(sa.Column("dms_manual_id", sa.String(36)))
        batch.add_column(sa.Column("dms_revision_id", sa.String(36)))
        batch.add_column(sa.Column("qms_evidence_id", sa.String(36)))
        batch.add_column(sa.Column("idempotency_key", sa.String(64)))
        batch.add_column(sa.Column("dms_evidence_asset_id", sa.String(36)))
        batch.add_column(sa.Column("dms_retention_id", sa.String(36)))
        batch.create_foreign_key("fk_ext_doc_submission_req", "external_provider_document_requirements", ["amo_id", "requirement_id"], ["amo_id", "id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_ext_doc_submission_tenant_provider", ["amo_id","tenant_provider_id","id"])
        batch.create_foreign_key("fk_ext_doc_supersedes", "external_partner_evidence_submissions",
            ["amo_id","tenant_provider_id","supersedes_submission_id"],
            ["amo_id","tenant_provider_id","id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_ext_doc_form_revision", "manual_revisions", ["form_revision_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_ext_doc_manual", "manuals", ["dms_manual_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_ext_doc_revision", "manual_revisions", ["dms_revision_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_ext_doc_qms_evidence", "quality_external_provider_evidence", ["qms_evidence_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_ext_doc_dms_asset", "document_evidence_assets", ["dms_evidence_asset_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_ext_doc_dms_retention", "document_retention_dispositions", ["dms_retention_id"], ["id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_ext_doc_idempotency", ["amo_id", "tenant_provider_id", "idempotency_key"])
    op.create_index("ix_ext_doc_requirement_history", "external_partner_evidence_submissions", ["amo_id", "tenant_provider_id", "requirement_id", "created_at"])
    # Replace only the original staging-state constraint. File rows and decisions
    # are never deleted/superseded in place; each resubmission is new.
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("ck_ext_partner_upload_state", type_="check")
        batch.drop_constraint("ck_ext_partner_upload_limit", type_="check")
        batch.create_check_constraint("ck_ext_partner_upload_limit", "size_bytes BETWEEN 1 AND 536870912")
        batch.create_check_constraint("ck_ext_partner_upload_state", "status IN ('PENDING_REVIEW','RETURNED','ACCEPTED','REJECTED','WITHDRAWN','SUPERSEDED')")
    op.create_table(
        "external_provider_document_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("external_partner_evidence_submissions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT")),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ext_doc_events_tenant_submission", "external_provider_document_events", ["amo_id", "submission_id", "occurred_at"])
    op.create_table(
        "external_provider_form_acknowledgements",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),sa.ForeignKey("amos.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("tenant_provider_id",sa.String(36),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("requirement_id",sa.String(36),nullable=False),
        sa.Column("form_revision_id",sa.String(36),sa.ForeignKey("manual_revisions.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("attestation",sa.Text(),nullable=False),
        sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","tenant_provider_id"],
            ["external_tenant_providers.amo_id","external_tenant_providers.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["amo_id","requirement_id"],
            ["external_provider_document_requirements.amo_id","external_provider_document_requirements.id"],ondelete="RESTRICT"),
        sa.UniqueConstraint("amo_id","tenant_provider_id","identity_id","requirement_id","form_revision_id",
            name="uq_ext_provider_form_ack_exact_actor_revision"),
    )
    op.create_index("ix_ext_form_ack_tenant_req",
                    "external_provider_form_acknowledgements",["amo_id","requirement_id","occurred_at"])
    op.create_table("external_provider_upload_sessions",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),sa.ForeignKey("amos.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("tenant_provider_id",sa.String(36),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("requirement_id",sa.String(36),nullable=False),
        sa.Column("related_kind",sa.String(32),nullable=False),
        sa.Column("related_id",sa.String(64)),
        sa.Column("supersedes_submission_id",sa.String(36)),
        sa.Column("filename",sa.String(255),nullable=False),
        sa.Column("content_type",sa.String(128),nullable=False),
        sa.Column("size_bytes",sa.BigInteger(),nullable=False),
        sa.Column("sha256",sa.String(64),nullable=False),
        sa.Column("valid_until",sa.Date()),
        sa.Column("retry_key",sa.String(64),nullable=False),
        sa.Column("state",sa.String(16),nullable=False,server_default="OPEN"),
        sa.Column("completed_submission_id",sa.String(36),sa.ForeignKey("external_partner_evidence_submissions.id",ondelete="RESTRICT")),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","tenant_provider_id"],
            ["external_tenant_providers.amo_id","external_tenant_providers.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["amo_id","requirement_id"],
            ["external_provider_document_requirements.amo_id","external_provider_document_requirements.id"],ondelete="RESTRICT"),
        sa.UniqueConstraint("amo_id","tenant_provider_id","identity_id","retry_key",
            name="uq_ext_upload_retry_per_member"),
        sa.UniqueConstraint("amo_id","tenant_provider_id","id",
            name="uq_ext_upload_session_provider"),
        sa.CheckConstraint("state IN ('OPEN','COMPLETED','EXPIRED')",name="ck_ext_upload_state"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 536870912",name="ck_ext_upload_max_size"),
    )
    op.create_table("external_provider_upload_parts",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),nullable=False),
        sa.Column("tenant_provider_id",sa.String(36),nullable=False),
        sa.Column("session_id",sa.String(36),nullable=False),
        sa.Column("part_number",sa.Integer(),nullable=False),
        sa.Column("object_uri",sa.Text(),nullable=False),
        sa.Column("size_bytes",sa.Integer(),nullable=False),
        sa.Column("sha256",sa.String(64),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","tenant_provider_id","session_id"],
            ["external_provider_upload_sessions.amo_id","external_provider_upload_sessions.tenant_provider_id",
             "external_provider_upload_sessions.id"],ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id","part_number",name="uq_ext_upload_part_index"),
        sa.CheckConstraint("part_number BETWEEN 0 AND 63",name="ck_ext_upload_part_index"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 8388608",name="ck_ext_upload_chunk_size"),
    )
    op.create_index("ix_ext_upload_sessions_expiry","external_provider_upload_sessions",
                    ["amo_id","state","created_at"])
    op.create_index("ix_ext_upload_parts_session","external_provider_upload_parts",
                    ["amo_id","session_id","part_number"])
    # Commercial lifecycle remains in existing QMS contract table.
    with op.batch_alter_table("quality_external_provider_contracts") as batch:
        batch.add_column(sa.Column("counterparties_json", sa.JSON()))
        batch.add_column(sa.Column("approved_sites_json", sa.JSON()))
        batch.add_column(sa.Column("authority_acceptance_reference", sa.String(255)))
        batch.add_column(sa.Column("signed_evidence_submission_id", sa.String(36)))
        batch.add_column(sa.Column("terminated_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("supersedes_contract_id", sa.String(36)))
        batch.add_column(sa.Column("change_reason", sa.Text()))
        # The predecessor FK references all three columns: PostgreSQL requires
        # this exact combination to be uniquely constrained, not just id PK.
        batch.create_unique_constraint("uq_ext_agreement_tenant_supplier_id",
                                       ["amo_id","supplier_id","id"])
        batch.create_foreign_key("fk_ext_agreement_prior", "quality_external_provider_contracts",
                                 ["amo_id","supplier_id","supersedes_contract_id"],
                                 ["amo_id","supplier_id","id"], ondelete="RESTRICT")
    if op.get_bind().dialect.name == "postgresql":
        for table in ("external_provider_document_requirements", "external_provider_document_events",
                      "external_provider_form_acknowledgements",
                      "external_provider_upload_sessions","external_provider_upload_parts"):
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
            provider_clause = (""" AND (
                tenant_provider_id = NULLIF(current_setting('app.external_provider_id',true),'')
                OR current_setting('app.external_provider_id',true) = '__INTERNAL_QUALITY_REVIEW__'
            )""" if table in {"external_provider_form_acknowledgements",
                                "external_provider_upload_sessions","external_provider_upload_parts"} else "")
            op.execute(sa.text(f"""CREATE POLICY "{table}_tenant" ON "{table}"
              USING (amo_id = NULLIF(current_setting('app.tenant_id',true), ''){provider_clause})
              WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id',true), ''){provider_clause})"""))
        op.execute(sa.text("""
          CREATE FUNCTION external_document_events_append_only() RETURNS trigger
          LANGUAGE plpgsql AS $extdocev$
          BEGIN
            RAISE EXCEPTION 'Provider document history is immutable';
          END;
          $extdocev$;
        """))
        op.execute(sa.text("""CREATE TRIGGER ext_form_ack_immutable
            BEFORE UPDATE OR DELETE ON external_provider_form_acknowledgements
            FOR EACH ROW EXECUTE FUNCTION external_document_events_append_only()"""))
        op.execute(sa.text("""CREATE TRIGGER ext_document_events_immutable
            BEFORE UPDATE OR DELETE ON external_provider_document_events
            FOR EACH ROW EXECUTE FUNCTION external_document_events_append_only()"""))


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS ext_form_ack_immutable ON external_provider_form_acknowledgements")
        op.execute("DROP TRIGGER IF EXISTS ext_document_events_immutable ON external_provider_document_events")
        op.execute("DROP FUNCTION IF EXISTS external_document_events_append_only()")
    op.drop_index("ix_ext_upload_parts_session",table_name="external_provider_upload_parts")
    op.drop_table("external_provider_upload_parts")
    op.drop_index("ix_ext_upload_sessions_expiry",table_name="external_provider_upload_sessions")
    op.drop_table("external_provider_upload_sessions")
    op.drop_index("ix_ext_form_ack_tenant_req",table_name="external_provider_form_acknowledgements")
    op.drop_table("external_provider_form_acknowledgements")
    with op.batch_alter_table("quality_external_provider_contracts") as batch:
        batch.drop_constraint("fk_ext_agreement_prior", type_="foreignkey")
        batch.drop_constraint("uq_ext_agreement_tenant_supplier_id", type_="unique")
        for name in ("change_reason", "supersedes_contract_id", "terminated_at", "signed_evidence_submission_id", "authority_acceptance_reference", "approved_sites_json", "counterparties_json"):
            batch.drop_column(name)
    op.drop_index("ix_ext_doc_events_tenant_submission", table_name="external_provider_document_events")
    op.drop_table("external_provider_document_events")
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("ck_ext_partner_upload_state", type_="check")
        batch.drop_constraint("ck_ext_partner_upload_limit", type_="check")
        batch.create_check_constraint("ck_ext_partner_upload_limit", "size_bytes BETWEEN 1 AND 20971520")
        batch.create_check_constraint("ck_ext_partner_upload_state", "status IN ('PENDING_REVIEW','ACCEPTED','REJECTED','WITHDRAWN')")
    op.drop_index("ix_ext_doc_requirement_history", table_name="external_partner_evidence_submissions")
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("uq_ext_doc_idempotency", type_="unique")
        for fk in ("fk_ext_doc_dms_retention", "fk_ext_doc_dms_asset", "fk_ext_doc_qms_evidence", "fk_ext_doc_revision", "fk_ext_doc_manual", "fk_ext_doc_form_revision", "fk_ext_doc_supersedes", "fk_ext_doc_submission_req"):
            batch.drop_constraint(fk, type_="foreignkey")
        batch.drop_constraint("uq_ext_doc_submission_tenant_provider", type_="unique")
        for col in ("dms_retention_id", "dms_evidence_asset_id", "idempotency_key", "qms_evidence_id", "dms_revision_id", "dms_manual_id", "valid_until", "form_revision_id", "supersedes_submission_id", "requirement_id"):
            batch.drop_column(col)
    op.drop_index("ix_ext_doc_req_tenant_kind", table_name="external_provider_document_requirements")
    op.drop_table("external_provider_document_requirements")
