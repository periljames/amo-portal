from datetime import datetime
from types import SimpleNamespace

import pytest

from amodb.apps.doc_control import workspace_dashboard_router as dashboard


@pytest.mark.parametrize("role,expected", [("AMO_ADMIN", 1), ("QUALITY_OFFICER", 1), ("AUDITOR", 0)])
def test_unassigned_drafts_follow_workflow_authority(monkeypatch, role, expected):
    workflow = SimpleNamespace(id="wf", manual_id="doc", tenant_id="amo", revision_id="rev", state="DRAFT", updated_at=datetime.now())
    class Query:
        def __init__(self, rows): self.rows = rows
        def filter(self, *args): return self
        def join(self, *args): return self
        def order_by(self, *args): return self
        def limit(self, *args): return self
        def all(self): return self.rows
    class DB:
        def query(self, *entities):
            return Query([workflow] if entities == (dashboard.dm.DocumentWorkflowInstance,) else [])
    user = SimpleNamespace(id="user", amo_id="amo", role=role, is_active=True, is_system_account=False, is_superuser=False)
    monkeypatch.setattr(dashboard, "resolve_tenant", lambda *a: SimpleNamespace(amo_id="amo"))
    monkeypatch.setattr(dashboard, "_responsibilities_for_user", lambda *a, **kw: {})
    monkeypatch.setattr(dashboard, "_readable_document_labels", lambda *a, **kw: {"doc": {"id": "doc", "code": "CHK", "title": "Checklist"}})
    result = dashboard._my_work(DB(), tenant_slug="tenant", current_user=user)
    assert len(result) == expected
    if expected:
        assert result[0]["status"] == "DRAFT"
        assert result[0]["action_label"] == "Review document"
        assert "workflow=wf" in result[0]["target_path"]
