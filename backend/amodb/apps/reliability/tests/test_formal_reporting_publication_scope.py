from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.reliability import formal_reporting_publication_hardening as hardening


def test_type_only_effectivity_freezes_resolved_aircraft_for_history():
    report = SimpleNamespace(
        effectivity_json={
            "aircraft_serial_numbers": [],
            "aircraft_types": ["De Havilland DHC-8-100"],
            "scope": "TENANT_FLEET",
        }
    )

    hardening._freeze_resolved_aircraft_effectivity(report, {"AC-001", "AC-002"})

    assert report.effectivity_json["requested_aircraft_serial_numbers"] == []
    assert report.effectivity_json["resolved_aircraft_serial_numbers"] == ["AC-001", "AC-002"]
    assert report.effectivity_json["aircraft_serial_numbers"] == ["AC-001", "AC-002"]
    assert report.effectivity_json["aircraft_types"] == ["De Havilland DHC-8-100"]
    assert report.effectivity_json["scope"] == "AIRCRAFT_TYPE_EFFECTIVITY"


def test_serial_only_effectivity_is_not_rewritten_as_type_scope():
    report = SimpleNamespace(
        effectivity_json={
            "aircraft_serial_numbers": ["AC-001"],
            "aircraft_types": [],
            "scope": "SELECTED_AIRCRAFT",
        }
    )

    hardening._freeze_resolved_aircraft_effectivity(report, {"AC-001"})

    assert report.effectivity_json == {
        "aircraft_serial_numbers": ["AC-001"],
        "aircraft_types": [],
        "scope": "SELECTED_AIRCRAFT",
    }
