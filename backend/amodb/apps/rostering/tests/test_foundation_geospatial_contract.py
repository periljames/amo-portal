from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from amodb.apps.foundations import airport_catalog, schemas, services
from amodb.apps.foundations.models import BaseStationType
from amodb.apps.foundations.router import _base_read_for_user, router as foundations_router


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


def test_low_accuracy_single_device_capture_cannot_enable_attendance_policy() -> None:
    with pytest.raises(ValidationError):
        schemas.BaseStationCreate(
            code="NBO-HQ",
            name="Nairobi Main Base",
            latitude=-1.319167,
            longitude=36.927778,
            coordinate_accuracy_m=900,
            location_source="DEVICE_SINGLE",
            geofence_radius_m=250,
            checkin_prompt_enabled=True,
        )


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


def test_ordinary_user_base_list_redacts_precise_location() -> None:
    now = datetime.now(timezone.utc)
    base = SimpleNamespace(
        id="base-1",
        amo_id="amo-1",
        code="NBO-HQ",
        name="Nairobi Main Base",
        icao_code="HKJK",
        iata_code="NBO",
        base_type=BaseStationType.MAIN_BASE,
        time_zone="Africa/Nairobi",
        description=None,
        latitude=-1.319167,
        longitude=36.927778,
        coordinate_accuracy_m=20.0,
        location_source="DEVICE_CONSENSUS",
        airport_reference_ident="HKJK",
        location_configured=True,
        geofence_radius_m=250,
        checkin_prompt_enabled=True,
        checkout_reminder_enabled=True,
        suspicious_location_review_enabled=True,
        is_active=True,
        location_verified_at=now,
        location_verified_by_user_id="admin-1",
        created_by_user_id="admin-1",
        updated_by_user_id="admin-1",
        created_at=now,
        updated_at=now,
        aliases=[],
    )
    ordinary_user = SimpleNamespace(
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=False,
        role="TECHNICIAN",
    )

    value = _base_read_for_user(base, ordinary_user)

    assert value.location_configured is True
    assert value.latitude is None
    assert value.longitude is None
    assert value.coordinate_accuracy_m is None
    assert value.location_verified_at is None
    assert value.location_verified_by_user_id is None
    assert value.checkin_prompt_enabled is True
    assert value.geofence_radius_m == 250


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