"""Shared QMS contractual projection: same source, tenant boundary and readiness."""
from __future__ import annotations

from datetime import date, timedelta

from amodb.apps.quality import provider_governance_router as gov
from amodb.apps.quality.tenant_security import TenantContext


class _Many:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def mappings(self):
        return _Many(self.value)


class _DB:
    def __init__(self, records):
        self.records = records
        self.queries = []

    def execute(self, statement, args):
        statement = str(statement)
        self.queries.append((statement, args))
        if "COUNT(*)" in statement:
            return _Result(len(self.records))
        return _Result(self.records)


def _contract(status, **updates):
    row = {
        "id": "contract-1",
        "supplier_id": 51,
        "contract_number": "C-001",
        "title": "Engine overhaul",
        "status": status,
        "effective_on": None,
        "expires_on": None,
        "termination_notice_days": 30,
        "controlled_document_id": None,
        "controlled_document_revision": None,
        "signed_evidence_submission_id": None,
        "supplier_code": "S-51",
        "legal_name": "Example supplier",
        "provider_status": "APPROVED",
        "provider_kind": "CONTRACTOR",
        "version": 1,
    }
    row.update(updates)
    return row


def _ctx():
    return TenantContext(
        amo_code="example",
        amo_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        user_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        is_superuser=False,
    )


def _read(db, monkeypatch, **options):
    monkeypatch.setattr(gov, "_require_tables", lambda _: None)
    return gov.provider_agreement_register(
        ctx=_ctx(), db=db, search="", status_filter="ALL",
        attention_only=False, due_within_days=30, limit=40, offset=0,
        **options,
    )


def test_register_uses_one_tenant_source_with_bounded_queries(monkeypatch):
    db = _DB([_contract("DRAFT")])
    result = _read(db, monkeypatch)
    assert result["total"] == 1
    assert result["items"][0]["attention"] == "EXECUTED_EVIDENCE_REQUIRED"
    assert len(db.queries) == 2
    for sql, params in db.queries:
        assert "c.amo_id = :amo" in sql
        assert "s.amo_id = c.amo_id" in sql
        assert params["amo"] == _ctx().amo_id
        assert "JOIN procurement_suppliers" in sql
        assert "quality_external_provider_contracts" in sql


def test_renewal_notice_window_does_not_claim_a_signature(monkeypatch):
    expires = date.today() + timedelta(days=61)
    db = _DB([_contract("ACTIVE", expires_on=expires, termination_notice_days=90,
                        controlled_document_id="m1", controlled_document_revision="r1",
                        signed_evidence_submission_id="s1")])
    result = _read(db, monkeypatch)
    item = result["items"][0]
    assert item["renewal_notice_on"] == expires - timedelta(days=90)
    assert item["attention"] == "RENEWAL_DUE"
    # Evidence metadata is linked but neither this endpoint nor this test
    # signs an agreement or grants provider Quality approval.
    assert item["controlled_original_linked"] is True
    assert "signature_verified" not in item


def test_expired_active_contract_is_ineligible_and_readable_as_history(monkeypatch):
    db = _DB([_contract("ACTIVE", expires_on=date.today() - timedelta(days=2))])
    item = _read(db, monkeypatch)["items"][0]
    assert item["effective_status"] == "EXPIRED"
    assert item["attention"] == "EXPIRED"
    assert item["days_until_expiry"] == -2

def test_active_filter_does_not_expose_expired_active_rows(monkeypatch):
    db = _DB([])
    monkeypatch.setattr(gov, "_require_tables", lambda _: None)
    gov.provider_agreement_register(
        ctx=_ctx(), db=db, search="", status_filter="ACTIVE",
        attention_only=False, due_within_days=30, limit=40, offset=0,
    )
    condition = db.queries[0][0]
    assert "c.expires_on IS NULL OR c.expires_on >= :today" in condition
    assert db.queries[0][1]["status"] == "ACTIVE"


def test_expired_filter_includes_stored_and_effectively_expired_rows(monkeypatch):
    db = _DB([])
    monkeypatch.setattr(gov, "_require_tables", lambda _: None)
    gov.provider_agreement_register(
        ctx=_ctx(), db=db, search="", status_filter="EXPIRED",
        attention_only=False, due_within_days=30, limit=40, offset=0,
    )
    condition = db.queries[0][0]
    assert "c.status = 'EXPIRED'" in condition
    assert "c.expires_on < :today" in condition
