from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from .analytics_common import _resolve_aircraft_selection, _tenant_id
from .analytics_drilldown_context import DrilldownContext
from .analytics_drilldown_deferrals import drilldown_deferrals
from .analytics_drilldown_events import drilldown_events
from .analytics_drilldown_fracas import drilldown_fracas
from .analytics_drilldown_sources import drilldown_sources
from .analytics_types import DrilldownResponse


def _drilldown_endpoint(
    dimension: str = Query(pattern="^(period|event_type|ata|aircraft|station|route|component|component_age|shop_visit_period|oil_consumption|deferral_status|deferral_expiry|deferral_category|deferral_extension|deferral_repeat|deferral_closure|fracas_stage|fracas_age|root_cause|effectiveness|fracas_action_status|fracas_action_period|fracas_reopened|engine_reading|engine_status|source|data_quality)$"),
    key: str = Query(min_length=1, max_length=255),
    period_start: date = Query(),
    period_end: date = Query(),
    bucket: str = Query(default="AUTO", pattern="^(AUTO|DAY|WEEK|MONTH)$"),
    aircraft: Optional[list[str]] = Query(default=None),
    aircraft_types: Optional[list[str]] = Query(default=None),
    ata_chapters: Optional[list[str]] = Query(default=None),
    stations: Optional[list[str]] = Query(default=None),
    event_types: Optional[list[str]] = Query(default=None),
    severities: Optional[list[str]] = Query(default=None),
    source_systems: Optional[list[str]] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> DrilldownResponse:
    amo_id = _tenant_id(current_user)
    selected_aircraft, _ = _resolve_aircraft_selection(
        db,
        amo_id=amo_id,
        aircraft=aircraft or [],
        aircraft_types=aircraft_types or [],
    )
    ctx = DrilldownContext(
        dimension=dimension,
        key=key,
        period_start=period_start,
        period_end=period_end,
        bucket=bucket,
        limit=limit,
        offset=offset,
        db=db,
        amo_id=amo_id,
        selected_aircraft=selected_aircraft,
        selected_ata=set(ata_chapters or []),
        selected_stations=set(stations or []),
        selected_types=set(event_types or []),
        selected_severities=set(severities or []),
        selected_sources=set(source_systems or []),
    )
    for resolver in (drilldown_events, drilldown_deferrals, drilldown_fracas, drilldown_sources):
        result = resolver(ctx)
        if result is not None:
            return result
    return DrilldownResponse(
        dimension=dimension,
        key=key,
        total=0,
        limit=limit,
        offset=offset,
        records=[],
    )
