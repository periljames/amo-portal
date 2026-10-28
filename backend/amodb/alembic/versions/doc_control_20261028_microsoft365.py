"""Optional tenant-owned Microsoft 365 Graph authorization and working file mapping.

Revision ID: doc_m365_261028
Revises: docx_fidelity_261028
"""
from alembic import op
import sqlalchemy as sa

revision = "doc_m365_261028"
down_revision = "docx_fidelity_261028"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_microsoft_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="NOT_CONNECTED"),
        sa.Column("microsoft_tenant_id", sa.String(72)),
        sa.Column("microsoft_user_id", sa.String(128)),
        sa.Column("microsoft_user_name", sa.String(255)),
        sa.Column("connected_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("encrypted_refresh_token", sa.Text()),
        sa.Column("granted_scopes", sa.Text()),
        sa.Column("oauth_state_sha256", sa.String(64), unique=True),
        sa.Column("oauth_state_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("oauth_state_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_connected_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "document_microsoft_file_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manual_id", sa.String(36), sa.ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drive_id", sa.String(512), nullable=False),
        sa.Column("item_id", sa.String(512), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("web_url", sa.Text(), nullable=False),
        sa.Column("observed_etag", sa.String(255), nullable=False),
        sa.Column("observed_modified_at", sa.DateTime(timezone=True)),
        sa.Column("observed_size", sa.Integer()),
        sa.Column("last_imported_etag", sa.String(255)),
        sa.Column("last_imported_source_sha256", sa.String(64)),
        sa.Column("last_imported_revision_id", sa.String(36), sa.ForeignKey("manual_revisions.id", ondelete="SET NULL")),
        sa.Column("linked_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "manual_id", name="uq_doc_microsoft_file_tenant_manual"),
    )
    op.create_index("ix_doc_microsoft_file_tenant_revision", "document_microsoft_file_links", ["tenant_id", "last_imported_revision_id"])


def downgrade():
    # No automatic loss of credentials, document linkage or revision provenance.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM document_microsoft_file_links LIMIT 1")).first():
        raise RuntimeError("Linked Microsoft document provenance must be explicitly retained before downgrade")
    if connection.execute(sa.text("SELECT 1 FROM document_microsoft_connections WHERE encrypted_refresh_token IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Disconnect tenant Microsoft accounts before destructive downgrade")
    op.drop_table("document_microsoft_file_links")
    op.drop_table("document_microsoft_connections")
