"""Consolidate preventive content into CAP without changing retained snapshots.

The downgrade restores the old nullable fields but retains all merged text in
CAP; it cannot infer how subsequent edits should be split into two narratives.
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_cap_unified_261121"
down_revision = "quality_car_evidence_261121"
branch_labels = None
depends_on = None

NARRATIVE_TABLES = ("qms_corrective_actions", "quality_cars", "quality_car_responses")


def merge(first, second):
    values = []
    for value in (first, second):
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return "\n\n".join(values) or None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    affected = [name for name in (*NARRATIVE_TABLES, "quality_car_rca_actions", "quality_car_attachments", "quality_car_rca_documents") if name in tables]
    # Migrate every tenant. Restore each table's existing RLS setting before the
    # transaction commits; any failure rolls back both data and policy changes.
    rls = []
    if bind.dialect.name == "postgresql":
        for name in affected:
            enabled = bind.execute(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:name)"), {"name": name}).scalar()
            if enabled:
                rls.append(name)
                op.execute(sa.text(f'ALTER TABLE "{name}" DISABLE ROW LEVEL SECURITY'))
    for name in NARRATIVE_TABLES:
        if name not in tables:
            continue
        table = sa.Table(name, sa.MetaData(), autoload_with=bind)
        if "preventive_action" not in table.c:
            continue
        for row in bind.execute(sa.select(table)).mappings():
            old = row["preventive_action"]
            if not old or not old.strip():
                continue
            changes = {"corrective_action": merge(row["corrective_action"], old)}
            if "capa_text" in table.c and row["capa_text"]:
                changes["capa_text"] = merge(row["capa_text"], old)
            bind.execute(table.update().where(table.c.id == row["id"]).values(**changes))
        with op.batch_alter_table(name) as batch:
            batch.drop_column("preventive_action")
    if "quality_car_rca_actions" in tables:
        op.execute(sa.text("UPDATE quality_car_rca_actions SET kind='CORRECTIVE' WHERE kind='PREVENTIVE'"))
        with op.batch_alter_table("quality_car_rca_actions") as batch:
            batch.drop_constraint("ck_quality_car_rca_action_kind", type_="check")
            batch.create_check_constraint("ck_quality_car_rca_action_kind", "kind IN ('CORRECTIVE','CONTAINMENT')")
    if "quality_car_attachments" in tables:
        op.execute(sa.text("UPDATE quality_car_attachments SET response_section='CORRECTIVE' WHERE response_section='PREVENTIVE'"))
    if "quality_car_rca_documents" in tables:
        table = sa.Table("quality_car_rca_documents", sa.MetaData(), autoload_with=bind)
        for row in bind.execute(sa.select(table.c.id, table.c.draft)).mappings():
            draft = row["draft"]
            if not isinstance(draft, dict) or not isinstance(draft.get("form"), dict) or "preventive_action" not in draft["form"]:
                continue
            form = dict(draft["form"])
            form["corrective_action"] = merge(form.get("corrective_action"), form.pop("preventive_action")) or ""
            bind.execute(table.update().where(table.c.id == row["id"]).values(draft={**draft, "form": form}))
    for name in rls:
        op.execute(sa.text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    for name in NARRATIVE_TABLES:
        op.add_column(name, sa.Column("preventive_action", sa.Text(), nullable=True))
    with op.batch_alter_table("quality_car_rca_actions") as batch:
        batch.drop_constraint("ck_quality_car_rca_action_kind", type_="check")
        batch.create_check_constraint("ck_quality_car_rca_action_kind", "kind IN ('CORRECTIVE','PREVENTIVE','CONTAINMENT')")
