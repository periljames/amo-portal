import importlib.util
from pathlib import Path
from copy import deepcopy
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from amodb.apps.quality.cap_content import unified_cap
from amodb.apps.quality.schemas import CARInviteUpdate


def test_old_submission_combines_both_fields_without_truncation():
    first, second = "c" * 8000, "p" * 8000
    payload = CARInviteUpdate(corrective_action=first, preventive_action=second)
    assert payload.corrective_action == first + "\n\n" + second
    assert "preventive_action" not in payload.model_dump()


def test_snapshot_projection_preserves_original_and_avoids_duplicate_text():
    original = {"form": {"corrective_action": "Same text", "preventive_action": "Same text"}, "actions": [{"kind": "PREVENTIVE"}]}
    before = deepcopy(original)
    assert unified_cap(original) == {"form": {"corrective_action": "Same text"}, "actions": [{"kind": "CORRECTIVE"}]}
    assert original == before


def test_empty_legacy_patch_does_not_clear_the_existing_cap():
    assert unified_cap({"preventive_action": None}) == {}
    assert unified_cap({"preventive_action": ""}) == {}
    assert unified_cap({"corrective_action": None, "preventive_action": None}) == {"corrective_action": None}


def test_migration_merges_content_reassigns_evidence_and_keeps_history_intact():
    path = Path(__file__).parents[3] / "alembic/versions/quality_20261121_unify_cap.py"
    spec = importlib.util.spec_from_file_location("cap_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as bind:
        meta = sa.MetaData()
        for name in migration.NARRATIVE_TABLES:
            table = sa.Table(name, meta, sa.Column("id", sa.String, primary_key=True), sa.Column("corrective_action", sa.Text), sa.Column("preventive_action", sa.Text), sa.Column("capa_text", sa.Text))
            table.create(bind)
            bind.execute(table.insert(), [{"id": "both", "corrective_action": "Existing CAP", "preventive_action": "Prevent recurrence", "capa_text": "Reviewed CAP"}, {"id": "only", "corrective_action": None, "preventive_action": "Only legacy content", "capa_text": None}])
        actions = sa.Table("quality_car_rca_actions", meta, sa.Column("id", sa.String, primary_key=True), sa.Column("kind", sa.String), sa.CheckConstraint("kind IN ('CORRECTIVE','PREVENTIVE','CONTAINMENT')", name="ck_quality_car_rca_action_kind"))
        attachments = sa.Table("quality_car_attachments", meta, sa.Column("id", sa.String, primary_key=True), sa.Column("response_section", sa.String))
        docs = sa.Table("quality_car_rca_documents", meta, sa.Column("id", sa.String, primary_key=True), sa.Column("draft", sa.JSON), sa.Column("submitted_snapshot", sa.JSON))
        meta.create_all(bind)
        bind.execute(actions.insert(), {"id": "action", "kind": "PREVENTIVE"})
        bind.execute(attachments.insert(), {"id": "evidence", "response_section": "PREVENTIVE"})
        original = {"form": {"corrective_action": "Draft CAP", "preventive_action": "Systemic control"}}
        bind.execute(docs.insert(), {"id": "document", "draft": original, "submitted_snapshot": original})
        migration.op = Operations(MigrationContext.configure(bind))
        migration.upgrade()
        for name in migration.NARRATIVE_TABLES:
            table = sa.Table(name, sa.MetaData(), autoload_with=bind)
            assert "preventive_action" not in table.c
            rows = {row["id"]: row for row in bind.execute(sa.select(table)).mappings()}
            assert rows["both"]["corrective_action"] == "Existing CAP\n\nPrevent recurrence"
            assert rows["both"]["capa_text"] == "Reviewed CAP\n\nPrevent recurrence"
            assert rows["only"]["corrective_action"] == "Only legacy content"
        assert bind.execute(sa.select(actions.c.kind)).scalar() == "CORRECTIVE"
        assert bind.execute(sa.select(attachments.c.response_section)).scalar() == "CORRECTIVE"
        doc = bind.execute(sa.select(docs)).mappings().one()
        assert doc["draft"]["form"] == {"corrective_action": "Draft CAP\n\nSystemic control"}
        assert doc["submitted_snapshot"] == original
