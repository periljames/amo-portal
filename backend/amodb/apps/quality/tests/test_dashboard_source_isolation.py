"""A failed optional source must not poison subsequent PostgreSQL reads."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from amodb.apps.quality import canonical_core_router as core


class ReadSession:
    """Model PostgreSQL's aborted-transaction behavior, including savepoints."""

    def __init__(self):
        self.aborted = False
        self.tenant = "tenant-retained"

    @contextmanager
    def begin_nested(self):
        previous = self.aborted
        try:
            yield
        except Exception:
            self.aborted = previous
            raise

    def fail(self):
        self.aborted = True
        raise OperationalError("optional source", {}, RuntimeError("query cancelled"))

    def execute(self, sql, params=None):
        if self.aborted:
            raise AssertionError("A previous source poisoned the next read")
        if "information_schema.tables" in str(sql):
            self.fail()
        return SimpleNamespace(scalar=lambda: 7)

    def query(self, *args):
        self.fail()

    def rollback(self):
        raise AssertionError("Optional probes must preserve the tenant transaction")


@pytest.mark.parametrize("probe", ["column", "table", "subscription", "entitlement"])
def test_optional_failure_preserves_next_counter_and_tenant(monkeypatch, probe):
    db = ReadSession()
    monkeypatch.setattr(core, "_is_postgres", lambda session: True)
    if probe == "column":
        monkeypatch.setattr(core, "_table_columns", lambda *args: db.fail())
        assert core._has_column_safe(db, "optional_table", "deleted_at") is False
    elif probe == "table":
        assert core._table_exists_safe(db, "optional_table") is False
    elif probe == "subscription":
        monkeypatch.setattr(core.account_services, "resolve_entitlements", lambda *args, **kwargs: {
            "training": SimpleNamespace(is_unlimited=True),
        })
        assert core._tenant_has_module(db, amo_id="tenant-retained", module_key="training") is True
    else:
        monkeypatch.setattr(core.account_services, "resolve_entitlements", lambda *args, **kwargs: db.fail())
        assert core._tenant_has_module(db, amo_id="tenant-retained", module_key="training") is False
    errors = []
    assert core._lite_scalar(db, sql="SELECT COUNT(*) FROM healthy_source", params={},
        source_errors=errors, label="healthy", ctx=SimpleNamespace(amo_code="test")) == 7
    assert errors == []
    assert db.tenant == "tenant-retained"
