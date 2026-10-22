import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality import canonical_core_router as router


class SettingsDB:
    def __init__(self, row=None, legacy=False):
        self.row = row
        self.columns = {"id", "amo_id", "payload", "deleted_at", "created_at", "updated_at", "created_by", "updated_by"}
        if legacy:
            self.columns.update(router._SETTINGS_GROUPS)
        self.statements = []
        self.committed = False

    def execute(self, statement, values):
        sql = str(statement)
        self.statements.append((sql, values.copy()))
        assert values["amo_id"] == "tenant-a"
        if sql.lstrip().startswith("SELECT"):
            assert "deleted_at IS NULL" in sql
            return self
        assert "RETURNING *" in sql
        row = dict(self.row or {"id": values["id"]})
        for key, value in values.items():
            if key in router._SETTINGS_GROUPS or key == "payload":
                assert key in self.columns, f"SQL references absent column {key}"
                row[key] = json.loads(value)
        self.row = row
        return self

    def mappings(self):
        return self

    def first(self):
        return self.row

    def commit(self):
        self.committed = True


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(router, "set_postgres_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(router, "_table_columns", lambda db, table: db.columns)
    monkeypatch.setattr(router, "_log_qms_activity", lambda *args, **kwargs: None)
    return SimpleNamespace(amo_id="tenant-a", amo_code="A", user_id="user-a")


def test_reads_canonical_payload_without_referencing_legacy_columns(context):
    db = SettingsDB({"id": "existing", "payload": {"numbering_rules": {"audit_prefix": "QAR"}, "internal": "keep"}})
    settings = router.get_qms_settings(context, db)["settings"]
    assert settings["numbering_rules"] == {"audit_prefix": "QAR"}
    assert settings["workflow_rules"] == {}
    assert "internal" not in settings
    assert "SELECT *" in db.statements[0][0]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_partial_updates_preserve_other_groups_and_support_both_layouts(context, legacy, existing):
    previous = {"id": "existing", "payload": {"internal": "keep", "retention_rules": {"years": 7}}} if existing else None
    db = SettingsDB(previous, legacy=legacy)
    result = router.update_qms_settings(None, {"numbering_rules": {"audit_prefix": "QA"}}, context, db)
    assert result["settings"]["numbering_rules"] == {"audit_prefix": "QA"}
    assert db.committed
    if existing:
        assert db.row["payload"]["internal"] == "keep"
        assert result["settings"]["retention_rules"] == {"years": 7}
        assert "FOR UPDATE" in db.statements[0][0]


def test_rejects_non_object_configuration_before_writing(context):
    db = SettingsDB()
    with pytest.raises(HTTPException) as error:
        router.update_qms_settings(None, {"workflow_rules": ["invalid"]}, context, db)
    assert error.value.status_code == 422
    assert not db.committed
