# backend/amodb/apps/foundations/services.py
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Iterable, List, Optional, TypeVar

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..accounts import models as account_models
from . import models, schemas

LOCATION_OBSERVATION_RETENTION_DAYS = 7
CONSENSUS_MIN_CONTRIBUTORS = 2
CONSENSUS_MAX_ACCEPTED_ACCURACY_M = 500.0
CONSENSUS_MAX_SPREAD_M = 350.0

ObservationT = TypeVar("ObservationT")


def _clean_code(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip().upper()
    return cleaned or None


def _clean_text(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _normalise_aliases(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _has_location(latitude: Optional[float], longitude: Optional[float]) -> bool:
    return latitude is not None and longitude is not None


def _latest_observation_per_contributor(observations: Iterable[ObservationT]) -> List[ObservationT]:
    """Keep one newest observation per contributor so one person cannot weight consensus."""
    latest: dict[str, ObservationT] = {}
    for row in observations:
        contributor = str(getattr(row, "submitted_by_user_id"))
        existing = latest.get(contributor)
        if existing is None or getattr(row, "created_at") > getattr(existing, "created_at"):
            latest[contributor] = row
    return list(latest.values())


def _apply_location_fields(item: models.BaseStation, data: dict, *, actor_user_id: str) -> None:
    location_keys = {
        "latitude",
        "longitude",
        "coordinate_accuracy_m",
        "location_source",
        "airport_reference_ident",
    }
    if not location_keys.intersection(data):
        return

    latitude = data.get("latitude", item.latitude)
    longitude = data.get("longitude", item.longitude)
    if (latitude is None) != (longitude is None):
        raise ValueError("Latitude and longitude must be provided together.")

    item.latitude = latitude
    item.longitude = longitude
    item.coordinate_accuracy_m = data.get("coordinate_accuracy_m", item.coordinate_accuracy_m)
    item.location_source = data.get("location_source", item.location_source)
    item.airport_reference_ident = _clean_code(data.get("airport_reference_ident", item.airport_reference_ident))

    if _has_location(latitude, longitude):
        item.location_source = item.location_source or "MANUAL"
        item.location_verified_at = datetime.now(timezone.utc)
        item.location_verified_by_user_id = actor_user_id
    else:
        item.coordinate_accuracy_m = None
        item.location_source = None
        item.airport_reference_ident = None
        item.location_verified_at = None
        item.location_verified_by_user_id = None
        item.checkin_prompt_enabled = False
        item.checkout_reminder_enabled = False
        item.suspicious_location_review_enabled = False


def list_base_stations(db: Session, *, amo_id: str, include_inactive: bool = False) -> List[models.BaseStation]:
    query = db.query(models.BaseStation).filter(models.BaseStation.amo_id == amo_id)
    if not include_inactive:
        query = query.filter(models.BaseStation.is_active.is_(True))
    return query.order_by(models.BaseStation.name.asc()).all()


def get_base_station(db: Session, *, amo_id: str, base_station_id: str) -> Optional[models.BaseStation]:
    return (
        db.query(models.BaseStation)
        .filter(models.BaseStation.amo_id == amo_id, models.BaseStation.id == base_station_id)
        .first()
    )


def create_base_station(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.BaseStationCreate,
) -> models.BaseStation:
    data = payload.model_dump(exclude={"aliases"})
    aliases = _normalise_aliases(payload.aliases)
    item = models.BaseStation(
        amo_id=amo_id,
        code=_clean_code(data.pop("code")),
        name=(data.pop("name") or "").strip(),
        icao_code=_clean_code(data.pop("icao_code", None)),
        iata_code=_clean_code(data.pop("iata_code", None)),
        time_zone=_clean_text(data.pop("time_zone", None)),
        description=_clean_text(data.pop("description", None)),
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
        **{key: value for key, value in data.items() if key not in {
            "latitude", "longitude", "coordinate_accuracy_m", "location_source", "airport_reference_ident"
        }},
    )
    _apply_location_fields(item, data, actor_user_id=actor_user_id)
    db.add(item)
    db.flush()
    for alias in aliases:
        db.add(models.BaseStationAlias(amo_id=amo_id, base_station_id=item.id, alias=alias, source_module="FOUNDATIONS"))
    db.flush()
    return item


def update_base_station(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    actor_user_id: str,
    payload: schemas.BaseStationUpdate,
) -> models.BaseStation:
    data = payload.model_dump(exclude_unset=True)
    aliases = data.pop("aliases", None)

    if "code" in data:
        data["code"] = _clean_code(data["code"])
    if "icao_code" in data:
        data["icao_code"] = _clean_code(data["icao_code"])
    if "iata_code" in data:
        data["iata_code"] = _clean_code(data["iata_code"])
    if "time_zone" in data:
        data["time_zone"] = _clean_text(data["time_zone"])
    if "description" in data:
        data["description"] = _clean_text(data["description"])
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()

    _apply_location_fields(base_station, data, actor_user_id=actor_user_id)
    location_keys = {"latitude", "longitude", "coordinate_accuracy_m", "location_source", "airport_reference_ident"}
    for field, value in data.items():
        if field in location_keys:
            continue
        setattr(base_station, field, value)

    if not _has_location(base_station.latitude, base_station.longitude) and (
        base_station.checkin_prompt_enabled
        or base_station.checkout_reminder_enabled
        or base_station.suspicious_location_review_enabled
    ):
        raise ValueError("Location prompts require approved base coordinates.")

    base_station.updated_by_user_id = actor_user_id
    if aliases is not None:
        base_station.aliases.clear()
        db.flush()
        for alias in _normalise_aliases(aliases):
            base_station.aliases.append(
                models.BaseStationAlias(amo_id=amo_id, alias=alias, source_module="FOUNDATIONS")
            )
    db.add(base_station)
    db.flush()
    return base_station


def _haversine_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    radius_m = 6_371_008.8
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def prune_location_observations(db: Session, *, now: Optional[datetime] = None) -> int:
    current = now or datetime.now(timezone.utc)
    return (
        db.query(models.BaseLocationObservation)
        .filter(models.BaseLocationObservation.expires_at <= current)
        .delete(synchronize_session=False)
    )


def create_location_observation(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    actor_user_id: str,
    payload: schemas.BaseLocationObservationCreate,
) -> models.BaseLocationObservation:
    now = datetime.now(timezone.utc)
    captured_at = payload.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    if captured_at > now + timedelta(minutes=5):
        raise ValueError("Captured time cannot be in the future.")
    if captured_at < now - timedelta(hours=24):
        raise ValueError("Location samples must be captured within the last 24 hours.")
    if payload.accuracy_m > 2500:
        raise ValueError("Location accuracy is too low to use as base evidence.")

    prune_location_observations(db, now=now)
    # A contributor may refresh their evidence, but cannot increase their weight
    # by submitting repeatedly from the same identity.
    db.query(models.BaseLocationObservation).filter(
        models.BaseLocationObservation.amo_id == amo_id,
        models.BaseLocationObservation.base_station_id == base_station.id,
        models.BaseLocationObservation.submitted_by_user_id == actor_user_id,
    ).delete(synchronize_session=False)

    observation = models.BaseLocationObservation(
        amo_id=amo_id,
        base_station_id=base_station.id,
        submitted_by_user_id=actor_user_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
        captured_at=captured_at,
        expires_at=now + timedelta(days=LOCATION_OBSERVATION_RETENTION_DAYS),
    )
    db.add(observation)
    db.flush()
    return observation


def build_location_consensus(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    now: Optional[datetime] = None,
) -> schemas.BaseLocationConsensusRead:
    current = now or datetime.now(timezone.utc)
    prune_location_observations(db, now=current)
    rows = (
        db.query(models.BaseLocationObservation)
        .filter(
            models.BaseLocationObservation.amo_id == amo_id,
            models.BaseLocationObservation.base_station_id == base_station.id,
            models.BaseLocationObservation.expires_at > current,
            models.BaseLocationObservation.accuracy_m <= CONSENSUS_MAX_ACCEPTED_ACCURACY_M,
        )
        .order_by(models.BaseLocationObservation.created_at.desc())
        .all()
    )
    observations = _latest_observation_per_contributor(rows)
    if not observations:
        return schemas.BaseLocationConsensusRead(
            base_station_id=base_station.id,
            sample_count=0,
            distinct_contributor_count=0,
            ready_for_approval=False,
            reason="No current high-quality location observations.",
        )

    candidate_latitude = float(median([row.latitude for row in observations]))
    candidate_longitude = float(median([row.longitude for row in observations]))
    median_accuracy = float(median([row.accuracy_m for row in observations]))
    max_spread = max(
        _haversine_m(candidate_latitude, candidate_longitude, row.latitude, row.longitude)
        for row in observations
    )
    contributors = len(observations)
    allowed_spread = max(CONSENSUS_MAX_SPREAD_M, float(base_station.geofence_radius_m or 250))
    ready = contributors >= CONSENSUS_MIN_CONTRIBUTORS and max_spread <= allowed_spread
    if contributors < CONSENSUS_MIN_CONTRIBUTORS:
        reason = f"At least {CONSENSUS_MIN_CONTRIBUTORS} distinct authorised contributors are required."
    elif max_spread > allowed_spread:
        reason = "Current observations are too widely dispersed and require review or recapture."
    else:
        reason = "Independent observations agree closely enough for administrator approval."

    return schemas.BaseLocationConsensusRead(
        base_station_id=base_station.id,
        sample_count=len(observations),
        distinct_contributor_count=contributors,
        candidate_latitude=round(candidate_latitude, 7),
        candidate_longitude=round(candidate_longitude, 7),
        median_accuracy_m=round(median_accuracy, 1),
        max_spread_m=round(max_spread, 1),
        ready_for_approval=ready,
        reason=reason,
        expires_at=min(row.expires_at for row in observations),
    )


def approve_location_consensus(
    db: Session,
    *,
    amo_id: str,
    base_station: models.BaseStation,
    actor_user_id: str,
    payload: schemas.BaseLocationConsensusApproval,
) -> schemas.BaseLocationConsensusRead:
    consensus = build_location_consensus(db, amo_id=amo_id, base_station=base_station)
    if consensus.sample_count != payload.expected_sample_count:
        raise ValueError("Location evidence changed. Refresh the consensus before approving it.")
    if not consensus.ready_for_approval or consensus.candidate_latitude is None or consensus.candidate_longitude is None:
        raise ValueError(consensus.reason)

    base_station.latitude = consensus.candidate_latitude
    base_station.longitude = consensus.candidate_longitude
    base_station.coordinate_accuracy_m = consensus.median_accuracy_m
    base_station.location_source = "DEVICE_CONSENSUS"
    base_station.location_verified_at = datetime.now(timezone.utc)
    base_station.location_verified_by_user_id = actor_user_id
    base_station.updated_by_user_id = actor_user_id
    db.add(base_station)

    # Minimise exposure: once the aggregate is approved, discard the raw points.
    db.query(models.BaseLocationObservation).filter(
        models.BaseLocationObservation.amo_id == amo_id,
        models.BaseLocationObservation.base_station_id == base_station.id,
    ).delete(synchronize_session=False)
    db.flush()
    return consensus


def clear_location_observations(db: Session, *, amo_id: str, base_station_id: str) -> int:
    return (
        db.query(models.BaseLocationObservation)
        .filter(
            models.BaseLocationObservation.amo_id == amo_id,
            models.BaseLocationObservation.base_station_id == base_station_id,
        )
        .delete(synchronize_session=False)
    )


def evaluate_location(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.LocationEvaluationRequest,
) -> schemas.LocationEvaluationRead:
    query = db.query(models.BaseStation).filter(
        models.BaseStation.amo_id == amo_id,
        models.BaseStation.is_active.is_(True),
        models.BaseStation.latitude.isnot(None),
        models.BaseStation.longitude.isnot(None),
    )
    if payload.base_station_id:
        query = query.filter(models.BaseStation.id == payload.base_station_id)
    candidates = query.all()
    if not candidates:
        return schemas.LocationEvaluationRead(
            location_confidence="UNAVAILABLE",
            note="No approved base location is configured in this tenant scope.",
        )

    distances = [
        (
            station,
            _haversine_m(payload.latitude, payload.longitude, float(station.latitude), float(station.longitude)),
        )
        for station in candidates
    ]
    station, distance_m = min(distances, key=lambda item: item[1])
    radius = int(station.geofence_radius_m or 250)
    inside = distance_m <= radius + payload.accuracy_m
    confidence = "HIGH" if payload.accuracy_m <= 50 else "MEDIUM" if payload.accuracy_m <= 150 else "LOW"
    review_signal = bool(
        station.suspicious_location_review_enabled
        and payload.accuracy_m <= 150
        and distance_m > max(radius * 4, 1500)
    )
    return schemas.LocationEvaluationRead(
        base_station_id=station.id,
        base_code=station.code,
        base_name=station.name,
        distance_m=round(distance_m, 1),
        geofence_radius_m=radius,
        inside_geofence=inside,
        location_confidence=confidence,
        checkin_prompt_enabled=bool(station.checkin_prompt_enabled and inside),
        checkout_reminder_enabled=bool(station.checkout_reminder_enabled),
        review_signal=review_signal,
        review_reason=(
            "Submitted high-confidence position is materially outside the approved base geofence; human review is required."
            if review_signal else None
        ),
        note="This evaluation is computed transiently and does not store the submitted device position.",
    )


def create_user_base_assignment(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.UserBaseAssignmentCreate,
) -> models.UserBaseAssignment:
    base = db.query(models.BaseStation).filter(models.BaseStation.id == payload.base_station_id, models.BaseStation.amo_id == amo_id).first()
    user = db.query(account_models.User).filter(account_models.User.id == payload.user_id, account_models.User.amo_id == amo_id).first()
    if not base or not user:
        raise ValueError("User or base station not found in the active AMO")
    item = models.UserBaseAssignment(
        amo_id=amo_id,
        created_by_user_id=actor_user_id,
        **payload.model_dump(),
    )
    if payload.is_primary:
        db.query(models.UserBaseAssignment).filter(
            models.UserBaseAssignment.amo_id == amo_id,
            models.UserBaseAssignment.user_id == payload.user_id,
            models.UserBaseAssignment.is_primary.is_(True),
            or_(models.UserBaseAssignment.effective_to.is_(None), models.UserBaseAssignment.effective_to >= payload.effective_from),
        ).update({models.UserBaseAssignment.is_primary: False}, synchronize_session=False)
    db.add(item)
    db.flush()
    return item


def list_availability(
    db: Session,
    *,
    amo_id: str,
    user_id: Optional[str] = None,
    active_at: Optional[datetime] = None,
) -> List[models.CanonicalAvailability]:
    query = db.query(models.CanonicalAvailability).filter(models.CanonicalAvailability.amo_id == amo_id)
    if user_id:
        query = query.filter(models.CanonicalAvailability.user_id == user_id)
    if active_at:
        query = query.filter(
            models.CanonicalAvailability.effective_from <= active_at,
            or_(models.CanonicalAvailability.effective_to.is_(None), models.CanonicalAvailability.effective_to >= active_at),
        )
    return query.order_by(models.CanonicalAvailability.effective_from.desc()).all()


def create_availability(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    payload: schemas.AvailabilityCreate,
) -> models.CanonicalAvailability:
    user = db.query(account_models.User).filter(account_models.User.id == payload.user_id, account_models.User.amo_id == amo_id).first()
    if not user:
        raise ValueError("User not found in the active AMO")
    item = models.CanonicalAvailability(
        amo_id=amo_id,
        user_id=payload.user_id,
        status=payload.status,
        effective_from=payload.effective_from or datetime.now(timezone.utc),
        effective_to=payload.effective_to,
        note=payload.note,
        updated_by_user_id=actor_user_id,
    )
    db.add(item)
    db.flush()
    return item


def personnel_identity_health(db: Session, *, amo_id: str) -> schemas.PersonnelIdentityHealth:
    users = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True)).all()
    profiles = db.query(account_models.PersonnelProfile).filter(
        account_models.PersonnelProfile.amo_id == amo_id,
        func.lower(account_models.PersonnelProfile.status).notin_(["inactive", "archived", "deleted"]),
    ).all()
    users_by_id = {str(user.id): user for user in users}
    linked_profiles = [profile for profile in profiles if profile.user_id and str(profile.user_id) in users_by_id]
    linked_user_ids = {str(profile.user_id) for profile in linked_profiles}
    issues: List[schemas.PersonnelIdentityIssue] = []

    for user in users:
        if str(user.id) not in linked_user_ids:
            issues.append(schemas.PersonnelIdentityIssue(
                issue_type="ACTIVE_USER_WITHOUT_PROFILE",
                user_id=str(user.id),
                staff_code=user.staff_code,
                full_name=user.full_name,
                email=user.email,
                detail="Active account is not linked to a canonical personnel profile.",
            ))
    for profile in profiles:
        if not profile.user_id or str(profile.user_id) not in users_by_id:
            issues.append(schemas.PersonnelIdentityIssue(
                issue_type="ACTIVE_PROFILE_WITHOUT_USER",
                personnel_profile_id=str(profile.id),
                person_id=profile.person_id,
                full_name=profile.full_name,
                email=profile.email,
                detail="Active personnel profile is not linked to an active user account.",
            ))

    return schemas.PersonnelIdentityHealth(
        amo_id=amo_id,
        active_users=len(users),
        active_personnel_profiles=len(profiles),
        linked_active_profiles=len(linked_profiles),
        active_users_without_profile=sum(1 for issue in issues if issue.issue_type == "ACTIVE_USER_WITHOUT_PROFILE"),
        active_profiles_without_user=sum(1 for issue in issues if issue.issue_type == "ACTIVE_PROFILE_WITHOUT_USER"),
        issues=issues,
    )


def foundation_contracts() -> schemas.FoundationContracts:
    return schemas.FoundationContracts(
        ownership={
            "personnel_identity": "Accounts users.id is the canonical person key; PersonnelProfile is one-to-one support data.",
            "base_station": "Foundations base_stations owns operational location identity, approved coordinates and geofence policy.",
            "department": "Accounts departments are tenant-managed records exposed through the Setup Centre without automatic seed-on-read.",
            "availability": "Foundations canonical_user_availability owns ON_DUTY/AWAY/ON_LEAVE state.",
            "workforce_terms": "Workforce owns employment contracts, work patterns and leave balances.",
            "rostering_plan": "Rostering owns roster plans, assignments, compliance checks and publication.",
        },
        service_contracts={
            "location_capture": {
                "raw_observations": "Short-lived, tenant-scoped and never returned to peers.",
                "consensus": "Uses one current observation per independent authorised contributor and explicit administrator approval.",
                "proximity_evaluation": "Transient calculation only; submitted device coordinates are not persisted.",
            },
            "attendance": {
                "consumer": "Rostering/HR may consume approved base geofence policy and transient proximity evaluations.",
                "guardrail": "Location alone never closes duty, checks a user in/out, or determines misconduct.",
            },
            "airport_catalog": {
                "provider": "OurAirports public-domain dataset with local server cache and mandatory operator confirmation.",
            },
        },
        canonical_frontend_routes={
            "amo_setup": "/maintenance/{amoCode}/admin/amo-assets",
            "workforce": "/maintenance/{amoCode}/rostering/settings?section=workforce",
            "rostering": "/maintenance/{amoCode}/rostering",
        },
    )
