"""Regression coverage for individually scoped external partner transactions.

Supplier membership and frontend route visibility never grant record-level
RFQ, PO, quotation, shipment, or manager-assigned repair-order permissions.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.procurement import external_auth_router as access
from amodb.apps.procurement import external_procurement_router as commerce


def _ctx(*, rfqs=("12",), purchase_orders=("31",)):
    return {
        "amo": "tenant-a", "supplier": 7, "provider": "provider-a", "person": "person-a",
        "rfqs": set(rfqs), "purchase_orders": set(purchase_orders),
    }


@pytest.mark.parametrize("scope,id", [("rfqs", 13), ("purchase_orders", 32)])
def test_direct_record_ids_deny_member_other_transaction_before_database(monkeypatch, scope, id):
    db = SimpleNamespace()
    def unexpected(*args, **kwargs):
        raise AssertionError("Unscoped canonical record query was executed")
    monkeypatch.setattr(commerce, "_row", unexpected)
    with pytest.raises(HTTPException) as denied:
        if scope == "rfqs":
            commerce._rfq(db, _ctx(), id, for_write=True)
        else:
            commerce._po(db, _ctx(), id, for_write=True)
    assert denied.value.status_code == 404


@pytest.mark.parametrize("kind,expected", [("rfqs", "rfqs"), ("purchase_orders", "purchase_orders")])
def test_member_lists_filter_before_limit_and_offset(monkeypatch, kind, expected):
    calls = []
    monkeypatch.setattr(commerce, "_session", lambda *a, **k: ({"id": "member"}, _ctx()))
    def rows(db, statement, **params):
        calls.append((statement, params))
        return []
    monkeypatch.setattr(commerce, "_rows", rows)
    if kind == "rfqs":
        out = commerce.rfqs("tenant-a", object(), object(), limit=20, offset=0)
    else:
        out = commerce.purchase_orders("tenant-a", object(), object(), limit=20, offset=0)
    assert out["items"] == []
    assert len(calls) == 1
    sql, params = calls[0]
    assert " IN :scoped" in sql and "LIMIT :limit OFFSET :offset" in sql
    assert params["amo"] == "tenant-a" and params["supplier"] == 7
    assert params["scoped"] == (["12"] if expected == "rfqs" else ["31"])


@pytest.mark.parametrize("kind", ["rfqs", "purchase_orders"])
def test_empty_member_scope_skips_queries(monkeypatch, kind):
    monkeypatch.setattr(commerce, "_session", lambda *a, **k: ({"id": "member"}, _ctx(rfqs=(), purchase_orders=())))
    monkeypatch.setattr(commerce, "_rows", lambda *a, **k: (_ for _ in ()).throw(AssertionError("leak")))
    response = (commerce.rfqs if kind == "rfqs" else commerce.purchase_orders)(
        "tenant-a", object(), object(), limit=20, offset=0
    )
    assert response["items"] == []


def test_quote_withdrawal_checks_parent_rfq_member_scope(monkeypatch):
    monkeypatch.setattr(commerce, "_session", lambda *a, **k: ({"id": "member"}, _ctx()))
    monkeypatch.setattr(commerce, "_row", lambda *a, **k: {
        "id": "quote", "status": "SUBMITTED", "quote_state": "RECEIVED", "rfq_id": 999
    })
    db = SimpleNamespace(execute=lambda *a, **k: (_ for _ in ()).throw(AssertionError("write before scope")))
    with pytest.raises(HTTPException) as denied:
        commerce.withdraw_quote("tenant-a", "quote", SimpleNamespace(note="withdraw quote", idempotency_key="retry"), object(), db)
    assert denied.value.status_code == 404


@pytest.mark.parametrize("kind,parent_key,parent_id", [
    ("QUOTE", "rfq_id", 999), ("SHIPMENT", "po_id", 999),
])
def test_history_checks_quote_shipment_parent_grant(monkeypatch, kind, parent_key, parent_id):
    monkeypatch.setattr(commerce, "_session", lambda *a, **k: ({"id": "member"}, _ctx()))
    monkeypatch.setattr(commerce, "_row", lambda *a, **k: {parent_key: parent_id})
    with pytest.raises(HTTPException) as denied:
        commerce.history("tenant-a", kind, "record-id", object(), object())
    assert denied.value.status_code == 404


def test_delegation_rejects_all_five_out_of_parent_scope_categories():
    parent = {kind: ["assigned"] for kind in access.DELEGABLE_OBJECT_SCOPES}
    for kind in access.DELEGABLE_OBJECT_SCOPES:
        with pytest.raises(HTTPException) as rejected:
            access._check_provider_delegation({kind: ["other"]}, parent)
        assert rejected.value.status_code == 403
    access._check_provider_delegation(
        {kind: ["assigned"] for kind in access.DELEGABLE_OBJECT_SCOPES}, parent
    )


def test_external_admin_cannot_assign_contracted_work():
    with pytest.raises(HTTPException) as rejected:
        access._check_provider_delegation({"contracted_work": ["work-999"]}, {})
    assert rejected.value.status_code == 403


def test_quality_edit_preserves_maintenance_assignment_and_rejects_tampering():
    old = {"rfqs": ["12"], "contracted_work": ["repair-123"]}
    saved = access._merge_manager_scopes({"rfqs": ["13"]}, old)
    assert saved["rfqs"] == ["13"]
    assert saved["contracted_work"] == ["repair-123"]
    assert old["contracted_work"] == ["repair-123"]
    assert access._merge_manager_scopes(
        {"contracted_work": ["repair-123"]}, old
    )["contracted_work"] == ["repair-123"]
    for altered in ([], ["repair-another"]):
        with pytest.raises(HTTPException) as rejected:
            access._merge_manager_scopes({"contracted_work": altered}, old)
        assert rejected.value.status_code == 403


@pytest.mark.parametrize("scope", [{"contracted_work": [123]}, {"rfqs": None}, {"rfqs": [""]}])
def test_malformed_scopes_return_validation_error(scope):
    with pytest.raises(HTTPException) as bad:
        access._scope(scope)
    assert bad.value.status_code == 422
