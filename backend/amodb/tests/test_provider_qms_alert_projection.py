"""Provider QMS notifications require the individual member's audit scope."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from amodb.apps.procurement.provider_alerts import _qms_grant_allows, _still_current


def test_qms_grant_does_not_leak_audit_or_inherit_unrelated_capability():
    grant = {"object_scope_json": {"assignments": ["audit-one"]},
             "capabilities_json": ["task.read"]}
    assert _qms_grant_allows(grant, "audit-one", "task.read")
    assert not _qms_grant_allows(grant, "audit-two", "task.read")
    assert not _qms_grant_allows(grant, "audit-one", "capa.respond")
    assert not _qms_grant_allows({"object_scope_json": {}, "capabilities_json": []},
                                 "audit-one", "task.read")


class _Found:
    def __init__(self, item):
        self.item = item

    def mappings(self):
        return self

    def first(self):
        return self.item


class _DB:
    def __init__(self, item):
        self.item = item
        self.sql = ""
        self.args = None

    def execute(self, statement, args):
        self.sql = str(statement)
        self.args = args
        return _Found(self.item)


def test_dispatch_rechecks_canonical_notice_revision():
    row = {"source_kind": "qms_notice", "source_id": "audit-one:notice-one",
           "source_stamp": "DELIVERED:2", "event_key": "quality.audit_notice"}
    db = _DB({"status": "DELIVERED", "revision_no": 2})
    assert _still_current(db, "tenant-one", row, None, {})
    assert db.args["amo"] == "tenant-one"
    assert db.args["audit"] == "audit-one"
    assert db.args["id"] == "notice-one"
    row["source_stamp"] = "DELIVERED:1"
    assert not _still_current(db, "tenant-one", row, None, {})


def test_closed_car_cancels_queued_due_alert():
    row = {"source_kind": "qms_car", "source_id": "audit-one:car-one",
           "source_stamp": "OPEN:2026-10-19", "event_key": "quality.car_due"}
    db = _DB({"status": "CLOSED", "due_date": date(2026, 10, 19)})
    assert not _still_current(db, "tenant-one", row, None, {})
