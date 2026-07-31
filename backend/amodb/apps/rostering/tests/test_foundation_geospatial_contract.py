from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.foundations import airport_catalog, schemas, services
from amodb.apps.foundations.router import router as foundations_router


def test_base_location_prompts_require_coordinates() -> None:
    with pytest.raises(ValidationError):
        schemas.BaseStationCreate(
            code="NBO-HQ",
            name="Nairobi Main Base",
            checkin_prompt_enabled=True,
        )


def test_base_location_accepts_explicit_consent_capture_fields() -> None:
    item = schemas.BaseStationCreate(
        code="NBO-HQ",
        name="Nairobi Main Base",
        latitude=-1.319167,
        longitude=36.927778,
        coordinate_accuracy_m=18,
        location_source="DEVICE_SINGLE",
        geofence_radius_m=250,
        checkin_prompt_enabled=True,
    )
    assert item.location_source == "DEVICE_SINGLE"
    assert item.checkin_prompt_enabled is True


def test_airport_catalog_prefers_exact_codes_and_returns_coordinates() -> None:
    rows = [
        {
            "ident": "HKJK",
            "gps_code": "HKJK",
            "iata_code": "NBO",
            "local_code": "",
            "name": "Jomo Kenyatta International Airport",
            "type": "large_airport",
            "municipality": "Nairobi",
            "iso_country": "KE",
            "iso_region": "KE-30",
            "latitude_deg": "-1.319167",
            "longitude_deg": "36.927778",
            "keywords": "Embakasi",
        },
        {
            "ident": "HKNW",
            "gps_code": "HKNW",
            "iata_code": "WIL",
            "local_code": "",
            "name": "Nairobi Wilson Airport",
            "type": "medium_airport",
            "municipality": "Nairobi",
            "iso_country": "KE",
            "iso_region": "KE-30",
            "latitude_deg": "-1.32172",
            "longitude_deg": "36.8148",
            "keywords": "Wilson",
        },
    ]
    result = airport_catalog.search_airports(query="NBO", rows=rows)
    assert result.items[0].ident == "HKJK"
    assert result.items[0].icao_code == "HKJK"
    assert result.items[0].iata_code == "NBO"
    assert result.items[0].latitude == pytest.approx(-1.319167)


def test_location_observation_payload_rejects_poor_accuracy() -> None:
    with pytest.raises(ValidationError):
        schemas.BaseLocationObservationCreate(
            latitude=-1.3,
            longitude=36.9,
            accuracy_m=3000,
            captured_at=datetime.now(timezone.utc),
        )


def test_consensus_keeps_only_latest_observation_per_contributor() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(submitted_by_user_id="u-1", created_at=now - timedelta(minutes=5), latitude=1.0),
        SimpleNamespace(submitted_by_user_id="u-1", created_at=now, latitude=2.0),
        SimpleNamespace(submitted_by_user_id="u-2", created_at=now - timedelta(minutes=1), latitude=3.0),
    ]
    selected = services._latest_observation_per_contributor(rows)
    assert len(selected) == 2
    assert {row.latitude for row in selected} == {2.0, 3.0}


def test_foundation_routes_expose_private_consensus_and_department_crud() -> None:
    routes = {(route.path, next(iter(route.methods or set()), "")) for route in foundations_router.routes}
    paths = {path for path, _ in routes}
    for path in {
        "/foundations/departments",
        "/foundations/departments/{department_id}",
        "/foundations/airport-catalog/search",
        "/foundations/base-stations/{base_station_id}/location-observations",
        "/foundations/base-stations/{base_station_id}/location-consensus",
        "/foundations/base-stations/{base_station_id}/location-consensus/approve",
        "/foundations/location/evaluate",
    }:
        assert path in paths

    # Raw peer observations have no list/read endpoint.
    assert not any(
        route.path.endswith("/location-observations") and "GET" in (route.methods or set())
        for route in foundations_router.routes
    )
