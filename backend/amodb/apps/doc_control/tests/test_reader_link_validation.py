from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control.reader_link_validation import validate_qms_link
from amodb.apps.quality import models as quality_models


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *_criteria):
        return self

    def first(self):
        return self.row


class _Db:
    def __init__(self, row):
        self.row = row

    def query(self, _model):
        return _Query(self.row)


def test_qms_audit_link_is_tenant_validated_and_canonicalized() -> None:
    row = quality_models.QMSAudit()
    row.id = uuid.uuid4()
    row.audit_ref = "QAR-MO-26-001"
    row.status = SimpleNamespace(value="CLOSED")
    result = validate_qms_link(_Db(row), tenant_id="amo-1", entity_type="audit", entity_id=str(row.id))
    assert result == {"entity_type": "QMS_AUDIT", "entity_id": str(row.id), "reference": "QAR-MO-26-001", "status": "CLOSED"}


def test_unsupported_link_type_fails_closed() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_qms_link(_Db(None), tenant_id="amo-1", entity_type="MADE_UP_RECORD", entity_id=str(uuid.uuid4()))
    assert caught.value.status_code == 422


def test_malformed_qms_identifier_is_rejected_before_query() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_qms_link(_Db(None), tenant_id="amo-1", entity_type="QMS_FINDING", entity_id="not-a-uuid")
    assert caught.value.status_code == 422


def test_missing_qms_record_is_not_silently_accepted() -> None:
    with pytest.raises(HTTPException) as caught:
        validate_qms_link(_Db(None), tenant_id="amo-1", entity_type="CAR", entity_id=str(uuid.uuid4()))
    assert caught.value.status_code == 404
