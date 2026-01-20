#!/usr/bin/env python3
"""Seed demo data for an empty AMO Portal instance."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

BASE_URL = os.getenv("AMO_API_URL", "http://localhost:8000").rstrip("/")
SUPERUSER_EMAIL = os.getenv("AMO_SUPERUSER_EMAIL", "owner@example.com")
SUPERUSER_PASSWORD = os.getenv("AMO_SUPERUSER_PASSWORD", "ChangeMe123!")
AMO_LOGIN_SLUG = os.getenv("AMO_LOGIN_SLUG", "demo-amo")
AMO_CODE = os.getenv("AMO_CODE", "DEMO")
AMO_NAME = os.getenv("AMO_NAME", "Demo AMO")
AMO_ADMIN_EMAIL = os.getenv("AMO_ADMIN_EMAIL", "admin@demo.example.com")
AMO_ADMIN_PASSWORD = os.getenv("AMO_ADMIN_PASSWORD", "ChangeMe123!")
AIRCRAFT_SERIAL = os.getenv("AMO_AIRCRAFT_SERIAL", "DEMO-001")
AIRCRAFT_REG = os.getenv("AMO_AIRCRAFT_REG", "N-DEMO")


def _request(
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None,
    token: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> Any:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {body}") from exc


def _safe_request(*args: Any, **kwargs: Any) -> Optional[Any]:
    try:
        return _request(*args, **kwargs)
    except RuntimeError as exc:
        print(str(exc))
        return None


def bootstrap_superuser() -> None:
    payload = {
        "email": SUPERUSER_EMAIL,
        "password": SUPERUSER_PASSWORD,
        "first_name": "Platform",
        "last_name": "Owner",
        "full_name": "Platform Owner",
        "position_title": "System Owner",
        "phone": "+10000000000",
        "staff_code": "ROOT-001",
    }
    _safe_request("POST", "/auth/first-superuser", payload)


def login(email: str, password: str, amo_slug: str) -> str:
    payload = {"email": email, "password": password, "amo_slug": amo_slug}
    token_payload = _request("POST", "/auth/login", payload)
    return token_payload["access_token"]


def ensure_amo(token: str) -> dict[str, Any]:
    payload = {
        "amo_code": AMO_CODE,
        "name": AMO_NAME,
        "icao_code": None,
        "country": "US",
        "login_slug": AMO_LOGIN_SLUG,
        "contact_email": AMO_ADMIN_EMAIL,
        "contact_phone": "+10000000000",
        "time_zone": "UTC",
    }
    amo = _safe_request("POST", "/accounts/admin/amos", payload, token=token)
    if amo:
        return amo
    amos = _request("GET", "/accounts/admin/amos", token=token)
    for item in amos:
        if item["login_slug"] == AMO_LOGIN_SLUG:
            return item
    raise RuntimeError("Unable to create or locate AMO.")


def ensure_amo_admin(token: str, amo_id: str) -> None:
    payload = {
        "email": AMO_ADMIN_EMAIL,
        "password": AMO_ADMIN_PASSWORD,
        "first_name": "Demo",
        "last_name": "Admin",
        "full_name": "Demo Admin",
        "role": "AMO_ADMIN",
        "position_title": "Accountable Manager",
        "phone": "+10000000000",
        "amo_id": amo_id,
        "staff_code": "DEMO-ADMIN",
    }
    _safe_request("POST", "/accounts/admin/users", payload, token=token)


def seed_fleet(token: str) -> None:
    aircraft_payload = {
        "serial_number": AIRCRAFT_SERIAL,
        "registration": AIRCRAFT_REG,
        "template": "DHC8",
        "make": "De Havilland",
        "model": "Dash 8",
    }
    _safe_request("POST", "/aircraft/", aircraft_payload, token=token)


def seed_components(token: str) -> dict[str, Any]:
    component_payload = {
        "part_number": "ENG-001",
        "serial_number": "ENG-SN-001",
        "description": "Baseline engine",
        "component_class": "ENGINE",
        "ata": "72",
    }
    component = _safe_request("POST", "/reliability/component-instances", component_payload, token=token)
    return component or {}


def seed_defect(token: str) -> None:
    defect_payload = {
        "reported_by": "Pilot",
        "source": "PILOT",
        "description": "Oil pressure fluctuation",
        "ata_chapter": "79",
        "occurred_at": "2024-01-01T00:00:00Z",
        "create_work_order": True,
        "idempotency_key": "demo-defect-001",
    }
    _safe_request(
        "POST",
        f"/aircraft/{AIRCRAFT_SERIAL}/defects",
        defect_payload,
        token=token,
        headers={"Idempotency-Key": "demo-defect-001"},
    )


def main() -> int:
    print("Bootstrapping superuser (if needed)...")
    bootstrap_superuser()
    print("Logging in as platform superuser...")
    superuser_token = login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD, "system")
    amo = ensure_amo(superuser_token)
    ensure_amo_admin(superuser_token, amo["id"])
    print("Logging in as AMO admin...")
    amo_token = login(AMO_ADMIN_EMAIL, AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG)
    print("Seeding aircraft...")
    seed_fleet(amo_token)
    print("Seeding baseline component instances...")
    seed_components(amo_token)
    print("Seeding defect intake...")
    seed_defect(amo_token)
    print("Seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
