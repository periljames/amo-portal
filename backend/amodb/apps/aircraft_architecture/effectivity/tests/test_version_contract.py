from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.aircraft_architecture.effectivity import services


def test_hash_is_stable_for_reordered_expression_keys():
    base = {
        "rule_set": SimpleNamespace(code="DHC8-ATA-05"),
        "version_code": "R1",
        "effective_date": "2026-08-05",
        "source_reference": "DHC8 MPD",
        "source_revision": "76",
        "source_checksum_sha256": None,
    }
    a = SimpleNamespace(**base, expression_json={"path": "aircraft.model", "op": "eq", "value": "DHC8-315"})
    b = SimpleNamespace(**base, expression_json={"value": "DHC8-315", "op": "eq", "path": "aircraft.model"})
    assert services.compute_content_hash(a) == services.compute_content_hash(b)


def test_non_draft_versions_are_immutable():
    with pytest.raises(HTTPException) as exc:
        services.require_draft(SimpleNamespace(status="PUBLISHED"))
    assert exc.value.status_code == 409
