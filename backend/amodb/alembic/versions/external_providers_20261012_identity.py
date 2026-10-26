"""Persistent cross-tenant provider identities and tenant-scoped access.

Revision ID: extprov_261012_identity
Revises: extprov_261009_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261012_identity"
down_revision = "extprov_261009_foundation"
branch_labels = None
depends_on = None

def upgrade():
    # Person and authentication factor are global. They are NEVER rows in users,
    # and are not subject to tenant-specific staff role inheritance.
    op.create_table("external_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="INVITED"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('INVITED','ACTIVE','LOCKED','REVOKED')", name="ck_external_identity_status"))
    op.create_table("external_credentials",
        sa.Column("identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("password_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("totp_secret_encrypted", sa.Text()),
        sa.Column("totp_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("failed_attempts >= 0", name="ck_external_credentials_attempts"))
    op.create_table("external_organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("registered_country", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("external_organization_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("external_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role_code", sa.String(48), nullable=False, server_default="READ_ONLY"),
        sa.Column("status", sa.String(24), nullable=False, server_default="INVITED"),
        sa.Column("joined_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "identity_id", name="uq_ext_org_member"),
        sa.CheckConstraint("status IN ('INVITED','ACTIVE','REVOKED')", name="ck_ext_org_member_status"))
    op.create_table("external_tenant_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("external_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("portal_state", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("restrict_new_work", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","supplier_id"],["procurement_suppliers.amo_id","procurement_suppliers.id"],name="fk_ext_tenant_provider_supplier"),
        sa.UniqueConstraint("amo_id","supplier_id",name="uq_ext_tenant_provider_supplier"),
        sa.UniqueConstraint("amo_id","organization_id","supplier_id",name="uq_ext_tenant_org_supplier"),
        sa.UniqueConstraint("amo_id","id",name="uq_ext_tenant_provider_id"),
        sa.CheckConstraint("portal_state IN ('PENDING','ACTIVE','SUSPENDED','REVOKED')",name="ck_ext_tenant_provider_state"))
    op.create_table("external_tenant_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("tenant_provider_id", sa.String(36), nullable=False),
        sa.Column("membership_id", sa.String(36), sa.ForeignKey("external_organization_memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role_code", sa.String(48), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("object_scope_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["amo_id","tenant_provider_id"],["external_tenant_providers.amo_id","external_tenant_providers.id"],name="fk_ext_grant_provider"),
        sa.UniqueConstraint("amo_id","tenant_provider_id","identity_id",name="uq_ext_grant_identity"),
        sa.UniqueConstraint("amo_id","id",name="uq_ext_tenant_grant_id"),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED','REVOKED')",name="ck_ext_grant_status"))
    op.create_table("external_identity_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id",ondelete="CASCADE"),nullable=False),
        sa.Column("identity_id", sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("grant_id", sa.String(36),nullable=False),
        sa.Column("kind", sa.String(24),nullable=False),
        sa.Column("token_hash",sa.String(64),nullable=False,unique=True),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("used_at",sa.DateTime(timezone=True)),
        sa.Column("revoked_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","grant_id"],["external_tenant_grants.amo_id","external_tenant_grants.id"],name="fk_ext_token_grant"),
        sa.CheckConstraint("kind IN ('INVITE','RESET','VERIFY')",name="ck_ext_token_kind"))
    op.create_table("external_sessions",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),sa.ForeignKey("amos.id",ondelete="CASCADE"),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("grant_id",sa.String(36),nullable=False),
        sa.Column("session_hash",sa.String(64),nullable=False,unique=True),
        sa.Column("csrf_hash",sa.String(64),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("revoked_at",sa.DateTime(timezone=True)),
        sa.Column("last_seen_at",sa.DateTime(timezone=True)),
        sa.Column("mfa_verified_at",sa.DateTime(timezone=True)),
        sa.Column("ip_hash",sa.String(64)),
        sa.Column("user_agent_hash",sa.String(64)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","grant_id"],["external_tenant_grants.amo_id","external_tenant_grants.id"],name="fk_ext_session_grant"))
    # Reuse the platform's WebAuthn library, not audit-guest invitation tokens.
    op.create_table("external_passkey_credentials",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="CASCADE"),nullable=False),
        sa.Column("credential_id",sa.LargeBinary(),nullable=False,unique=True),
        sa.Column("public_key",sa.LargeBinary(),nullable=False),
        sa.Column("sign_count",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("nickname",sa.String(80)),
        sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.text("true")),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column("last_used_at",sa.DateTime(timezone=True)))
    op.create_table("external_passkey_challenges",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),sa.ForeignKey("amos.id",ondelete="CASCADE"),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="CASCADE"),nullable=False),
        sa.Column("challenge_type",sa.String(20),nullable=False),
        sa.Column("challenge_b64",sa.String(128),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("consumed_at",sa.DateTime(timezone=True)),
        sa.CheckConstraint("challenge_type IN ('REGISTER','ASSERT')",name="ck_ext_passkey_challenge_type"))
    op.create_table("external_security_events",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),sa.ForeignKey("amos.id",ondelete="CASCADE"),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT")),
        sa.Column("grant_id",sa.String(36)),
        sa.Column("actor_identity_id",sa.String(36)),
        sa.Column("actor_user_id",sa.String(36)),
        sa.Column("event_type",sa.String(80),nullable=False),
        sa.Column("details_json",sa.JSON(),nullable=False),
        sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_ext_events_actor_tenant","external_security_events",["amo_id","occurred_at"])
    for name in ("external_tenant_providers","external_tenant_grants","external_identity_tokens","external_sessions","external_passkey_challenges","external_security_events"):
        op.create_index(f"ix_{name}_tenant",name,["amo_id"])
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f"""CREATE POLICY "{name}_tenant" ON "{name}"
                USING (amo_id = NULLIF(current_setting('app.tenant_id',true),''))
                WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id',true),''))"""))

    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""CREATE FUNCTION external_security_events_no_change()
            RETURNS trigger LANGUAGE plpgsql AS $provider$
            BEGIN RAISE EXCEPTION 'External security event history is immutable'; END;
            $provider$"""))
        op.execute(sa.text("""CREATE TRIGGER trg_ext_security_events_immutable
            BEFORE UPDATE OR DELETE ON external_security_events
            FOR EACH ROW EXECUTE FUNCTION external_security_events_no_change()"""))

def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_ext_security_events_immutable ON external_security_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS external_security_events_no_change()"))
    for name in ("external_security_events","external_passkey_challenges","external_passkey_credentials","external_sessions","external_identity_tokens","external_tenant_grants","external_tenant_providers"):
        op.drop_table(name)
    for name in ("external_organization_memberships","external_organizations","external_credentials","external_identities"):
        op.drop_table(name)
