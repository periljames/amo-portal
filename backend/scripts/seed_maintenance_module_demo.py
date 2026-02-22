#!/usr/bin/env python3
"""Seed focused maintenance module demo data using existing APIs (non-duplicative)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

BASE_URL = os.getenv("AMO_API_URL", "http://localhost:8000").rstrip("/")
AMO_LOGIN_SLUG = os.getenv("AMO_LOGIN_SLUG", "demo-amo")
AMO_ADMIN_EMAIL = os.getenv("AMO_ADMIN_EMAIL", "admin@demo.example.com")
AMO_ADMIN_PASSWORD = os.getenv("AMO_ADMIN_PASSWORD", "ChangeMe123!")
AIRCRAFT_SERIAL = os.getenv("AMO_AIRCRAFT_SERIAL", "DEMO-001")


def _request(method: str, path: str, payload: Optional[dict[str, Any]] = None, token: Optional[str] = None) -> Any:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {body}") from exc


def login() -> str:
    data = _request("POST", "/auth/login", {"email": AMO_ADMIN_EMAIL, "password": AMO_ADMIN_PASSWORD, "amo_slug": AMO_LOGIN_SLUG})
    return data["access_token"]


def create_work_order(token: str, wo_number: str, status: str, description: str) -> dict[str, Any]:
    return _request(
        "POST",
        "/work-orders",
        {
            "wo_number": wo_number,
            "aircraft_serial_number": AIRCRAFT_SERIAL,
            "description": description,
            "wo_type": "PERIODIC",
            "status": status,
            "is_scheduled": True,
            "open_date": "2026-01-10",
            "due_date": "2026-01-20",
        },
        token,
    )


def add_task(token: str, wo_id: int, title: str, status: str) -> dict[str, Any]:
    return _request(
        "POST",
        f"/work-orders/{wo_id}/tasks",
        {
            "title": title,
            "category": "SCHEDULED",
            "origin_type": "SCHEDULED",
            "priority": "MEDIUM",
            "status": status,
        },
        token,
    )


def create_defect(token: str) -> None:
    _request(
        "POST",
        f"/aircraft/{AIRCRAFT_SERIAL}/defects",
        {
            "reported_by": "Line",
            "source": "MAINTENANCE",
            "description": "Hydraulic seep observed at bay.",
            "ata_chapter": "29",
            "occurred_at": "2026-01-10T08:00:00Z",
            "create_work_order": False,
            "idempotency_key": "maintenance-seed-defect-001",
        },
        token,
    )


def issue_crs_for_wo(token: str, wo_number: str) -> None:
    prefill = _request("GET", f"/crs/prefill/{wo_number}", token=token)
    payload = {
        **prefill,
        "issuer_full_name": "Demo Certifier",
        "issuer_auth_ref": "AUTH-001",
        "issuer_license": "LIC-001",
        "crs_issue_date": "2026-01-20",
        "signoffs": [
            {
                "category": "AEROPLANES",
                "sign_date": "2026-01-20",
                "full_name_and_signature": "Demo Certifier",
                "internal_auth_ref": "AUTH-001",
                "stamp": "AMO-STAMP",
            }
        ],
    }
    _request("POST", "/crs/", payload, token)


def main() -> int:
    token = login()
    wo1 = create_work_order(token, "WO-DEMO-001", "IN_PROGRESS", "In-progress scheduled check")
    wo2 = create_work_order(token, "WO-DEMO-002", "RELEASED", "Waiting parts")
    wo3 = create_work_order(token, "WO-DEMO-003", "INSPECTED", "CRS pending closeout")
    wo4 = create_work_order(token, "WO-DEMO-004", "INSPECTED", "Closeout-ready WO")

    add_task(token, wo1["id"], "General visual inspection", "IN_PROGRESS")
    add_task(token, wo2["id"], "Replace hydraulic seal", "PAUSED")
    add_task(token, wo3["id"], "Functional test", "COMPLETED")
    add_task(token, wo4["id"], "Final duplicate inspection", "COMPLETED")

    create_defect(token)
    issue_crs_for_wo(token, "WO-DEMO-004")

    print("Seeded: aircraft baseline usage + 4 WOs (incl. CRS pending and closeout-ready), 1 defect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
