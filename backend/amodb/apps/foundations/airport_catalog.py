# backend/amodb/apps/foundations/airport_catalog.py
from __future__ import annotations

import csv
import io
import math
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from . import schemas

DEFAULT_DATASET_URL = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
_CACHE_LOCK = threading.Lock()
_CACHE_ROWS: list[dict[str, str]] = []
_CACHE_LOADED_AT = 0.0
_CACHE_TIMESTAMP: Optional[datetime] = None


class AirportCatalogUnavailable(RuntimeError):
    pass


def _haversine_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    radius_km = 6371.0088
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def _download_dataset() -> str:
    local_path = (os.getenv("AIRPORT_DATASET_LOCAL_PATH") or "").strip()
    if local_path:
        path = Path(local_path).expanduser().resolve()
        if not path.exists():
            raise AirportCatalogUnavailable("Configured airport dataset file does not exist.")
        return path.read_text(encoding="utf-8-sig")

    url = (os.getenv("AIRPORT_DATASET_URL") or DEFAULT_DATASET_URL).strip()
    timeout = max(1.0, min(float(os.getenv("AIRPORT_DATASET_TIMEOUT_SECONDS", "8") or "8"), 30.0))
    request = urllib.request.Request(url, headers={"User-Agent": "AMO-Portal-Airport-Catalog/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(32 * 1024 * 1024 + 1)
    except Exception as exc:  # pragma: no cover - depends on runtime network
        raise AirportCatalogUnavailable(f"Airport catalog provider is unavailable: {exc}") from exc
    if len(payload) > 32 * 1024 * 1024:
        raise AirportCatalogUnavailable("Airport catalog response exceeded the safety limit.")
    return payload.decode("utf-8-sig")


def _load_rows(force: bool = False) -> tuple[list[dict[str, str]], Optional[datetime]]:
    global _CACHE_ROWS, _CACHE_LOADED_AT, _CACHE_TIMESTAMP
    ttl_seconds = max(300, int(os.getenv("AIRPORT_DATASET_CACHE_TTL_SECONDS", "86400") or "86400"))
    now = time.monotonic()
    if not force and _CACHE_ROWS and now - _CACHE_LOADED_AT < ttl_seconds:
        return _CACHE_ROWS, _CACHE_TIMESTAMP

    with _CACHE_LOCK:
        now = time.monotonic()
        if not force and _CACHE_ROWS and now - _CACHE_LOADED_AT < ttl_seconds:
            return _CACHE_ROWS, _CACHE_TIMESTAMP
        try:
            text = _download_dataset()
            reader = csv.DictReader(io.StringIO(text))
            rows = [row for row in reader if row.get("ident") and row.get("latitude_deg") and row.get("longitude_deg")]
        except AirportCatalogUnavailable:
            if _CACHE_ROWS:
                return _CACHE_ROWS, _CACHE_TIMESTAMP
            raise
        except Exception as exc:
            if _CACHE_ROWS:
                return _CACHE_ROWS, _CACHE_TIMESTAMP
            raise AirportCatalogUnavailable(f"Airport catalog could not be parsed: {exc}") from exc
        _CACHE_ROWS = rows
        _CACHE_LOADED_AT = now
        _CACHE_TIMESTAMP = datetime.now(timezone.utc)
        return _CACHE_ROWS, _CACHE_TIMESTAMP


def _normalise(value: Optional[str]) -> str:
    return " ".join((value or "").strip().casefold().split())


def _score(row: dict[str, str], query: str) -> float:
    query_norm = _normalise(query)
    if not query_norm:
        return 0.0
    ident = _normalise(row.get("ident"))
    gps = _normalise(row.get("gps_code"))
    iata = _normalise(row.get("iata_code"))
    local = _normalise(row.get("local_code"))
    name = _normalise(row.get("name"))
    municipality = _normalise(row.get("municipality"))
    keywords = _normalise(row.get("keywords"))
    codes = [ident, gps, iata, local]
    if query_norm in codes:
        return 1000.0
    if any(code.startswith(query_norm) for code in codes if code):
        return 850.0
    if name.startswith(query_norm):
        return 700.0
    if municipality.startswith(query_norm):
        return 620.0
    if query_norm in name:
        return 540.0
    if query_norm in municipality:
        return 480.0
    if query_norm in keywords:
        return 360.0
    terms = query_norm.split()
    haystack = " ".join([ident, gps, iata, local, name, municipality, keywords])
    if terms and all(term in haystack for term in terms):
        return 260.0
    return 0.0


def search_airports(
    *,
    query: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    limit: int = 10,
    rows: Optional[Iterable[dict[str, str]]] = None,
) -> schemas.AirportCatalogSearchRead:
    cached_at: Optional[datetime] = None
    if rows is None:
        catalog_rows, cached_at = _load_rows()
    else:
        catalog_rows = list(rows)
    query_norm = _normalise(query)
    if len(query_norm) < 2:
        return schemas.AirportCatalogSearchRead(items=[], cached_at=cached_at)

    ranked: list[tuple[float, float, dict[str, str]]] = []
    for row in catalog_rows:
        score = _score(row, query_norm)
        if score <= 0:
            continue
        try:
            row_latitude = float(row["latitude_deg"])
            row_longitude = float(row["longitude_deg"])
        except (KeyError, TypeError, ValueError):
            continue
        distance_km = (
            _haversine_km(latitude, longitude, row_latitude, row_longitude)
            if latitude is not None and longitude is not None
            else math.inf
        )
        # Nearby matches break otherwise equal textual scores without overriding exact codes.
        proximity_bonus = max(0.0, 80.0 - min(distance_km, 80.0)) if math.isfinite(distance_km) else 0.0
        ranked.append((score + proximity_bonus, distance_km, row))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2].get("name") or ""))
    items: list[schemas.AirportCatalogItem] = []
    for _, distance_km, row in ranked[: max(1, min(limit, 25))]:
        latitude_value = float(row["latitude_deg"])
        longitude_value = float(row["longitude_deg"])
        ident = (row.get("ident") or "").strip().upper()
        gps_code = (row.get("gps_code") or "").strip().upper() or None
        icao_code = gps_code or (ident if len(ident) == 4 and ident.isalnum() else None)
        items.append(
            schemas.AirportCatalogItem(
                ident=ident,
                name=(row.get("name") or ident).strip(),
                airport_type=(row.get("type") or "").strip() or None,
                municipality=(row.get("municipality") or "").strip() or None,
                iso_country=(row.get("iso_country") or "").strip() or None,
                iso_region=(row.get("iso_region") or "").strip() or None,
                icao_code=icao_code,
                iata_code=(row.get("iata_code") or "").strip().upper() or None,
                local_code=(row.get("local_code") or "").strip().upper() or None,
                latitude=latitude_value,
                longitude=longitude_value,
                distance_km=round(distance_km, 1) if math.isfinite(distance_km) else None,
            )
        )
    return schemas.AirportCatalogSearchRead(items=items, cached_at=cached_at)
