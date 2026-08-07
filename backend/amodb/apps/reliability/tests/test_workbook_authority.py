from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.reliability import models as reliability_models
from amodb.apps.reliability import workbook_parity as wp


class FakeQuery:
    def __init__(self, existing):
        self.existing = existing

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self.existing


class FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    def query(self, model):
        assert model is reliability_models.AircraftUtilizationDaily
        return FakeQuery(self.existing)

    def add(self, value):
        self.added.append(value)


def record(**overrides):
    values = {
        "dataset_code": wp.WorkbookDatasetCode.AU.value,
        "amo_id": "amo-1",
        "aircraft_serial_number": "208B-001",
        "event_date": date(2026, 8, 1),
        "payload": {"flight_hours": "12.375", "flight_cycles": 7, "source_reference": "OPS-2026-08-01"},
        "reference_code": None,
        "record_number": "AU-202608-00001",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_au_approval_refuses_to_overwrite_authoritative_utilisation():
    db = FakeSession(existing=SimpleNamespace(id=91))
    with pytest.raises(HTTPException) as conflict:
        wp._approve_to_canonical(db, record(), "user-1")
    assert conflict.value.status_code == 409
    assert "cannot overwrite" in str(conflict.value.detail).lower()
    assert db.added == []


def test_au_approval_creates_exact_new_utilisation_without_float_conversion():
    db = FakeSession()
    wp._approve_to_canonical(db, record(), "user-1")
    assert len(db.added) == 1
    created = db.added[0]
    assert created.flight_hours == Decimal("12.375")
    assert created.cycles == 7
    assert created.source == "OPS-2026-08-01"
