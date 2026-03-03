#!/usr/bin/env python3
"""End-to-end deterministic demo seed for authenticated Planning/Production screenshots."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

BASE_URL = os.getenv("AMO_API_URL", "http://localhost:8080").rstrip("/")
SUPERUSER_EMAIL = os.getenv("AMO_SUPERUSER_EMAIL", "owner@example.com")
SUPERUSER_PASSWORD = os.getenv("AMO_SUPERUSER_PASSWORD", "ChangeMe123!")
AMO_LOGIN_SLUG = os.getenv("AMO_LOGIN_SLUG", "demo-amo")
AMO_ADMIN_EMAIL = os.getenv("AMO_ADMIN_EMAIL", "admin@demo.example.com")
AMO_ADMIN_PASSWORD = os.getenv("AMO_ADMIN_PASSWORD", "ChangeMe123!")
AIRCRAFT_SERIAL = os.getenv("AMO_AIRCRAFT_SERIAL", "DEMO-001")


def req(method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None) -> Any:
    r = urllib.request.Request(f"{BASE_URL}{path}", data=json.dumps(payload).encode("utf-8") if payload is not None else None, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode('utf-8')}")


def safe(method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None):
    try:
        return req(method, path, payload, token)
    except RuntimeError as e:
        print(e)
        return None


def login(email: str, password: str, amo_slug: str) -> str:
    return req("POST", "/auth/login", {"email": email, "password": password, "amo_slug": amo_slug})["access_token"]


def ensure_users(super_token: str, amo_id: str):
    users = [
        ("planner@demo.example.com", "PLANNING_ENGINEER", "Planner"),
        ("production@demo.example.com", "PRODUCTION_ENGINEER", "Production"),
        ("quality@demo.example.com", "QUALITY_MANAGER", "Quality"),
        ("records@demo.example.com", "CERTIFYING_ENGINEER", "Records"),
    ]
    for email, role, label in users:
        safe("POST", "/accounts/admin/users", {
            "email": email,
            "password": AMO_ADMIN_PASSWORD,
            "first_name": label,
            "last_name": "Demo",
            "full_name": f"{label} Demo",
            "role": role,
            "position_title": label,
            "phone": "+10000000000",
            "amo_id": amo_id,
            "staff_code": f"DEMO-{role}",
        }, super_token)


def main() -> int:
    # base seed flows
    os.system("python backend/scripts/seed_demo.py")
    os.system("python backend/scripts/seed_maintenance_module_demo.py")
    os.system("python backend/scripts/seed_technical_records_demo.py")

    super_token = login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD, "system")
    amos = req("GET", "/accounts/admin/amos", token=super_token)
    amo = next((a for a in amos if a.get("login_slug") == AMO_LOGIN_SLUG), amos[0])
    ensure_users(super_token, amo["id"])

    planner_token = login("planner@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG)

    wl = safe("POST", "/records/watchlists", {"name": "Demo AD/SB", "criteria_json": {"keywords": ["fuel", "wing"]}}, planner_token)
    if wl:
        safe("POST", f"/records/watchlists/{wl['id']}/run", {}, planner_token)

    queue = safe("GET", "/records/publications/review", None, planner_token) or []
    for row in queue[:2]:
        safe("POST", f"/records/publications/review/{row['match_id']}/decision", {"review_status": "Under Review", "classification": "Applicable"}, planner_token)
        safe("POST", "/records/compliance-actions", {"publication_match_id": row["match_id"], "decision": "ADD_TO_EXISTING_WORK_PACKAGE", "status": "Planned"}, planner_token)

    prod_token = login("production@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG)
    wos = safe("GET", "/work-orders/?limit=20", None, prod_token) or []
    if wos:
        wo = wos[0]
        tasks = safe("GET", f"/work-orders/{wo['id']}/tasks", None, prod_token) or []
        if tasks:
            t = tasks[0]
            safe("PUT", f"/work-orders/tasks/{t['id']}", {"status": "IN_PROGRESS", "last_known_updated_at": t["updated_at"]}, prod_token)
            t2 = safe("GET", f"/work-orders/tasks/{t['id']}", None, prod_token)
            if t2:
                safe("PUT", f"/work-orders/tasks/{t['id']}", {"status": "COMPLETED", "last_known_updated_at": t2["updated_at"]}, prod_token)
        safe("POST", "/records/production/release-gates", {"work_order_id": wo["id"], "status": "Ready", "readiness_notes": "Seeded release prep", "blockers_json": []}, prod_token)

    print("Demo seed complete")
    print(f"Tenant: {AMO_LOGIN_SLUG}")
    print(f"Planner login: planner@demo.example.com / {AMO_ADMIN_PASSWORD}")
    print(f"Production login: production@demo.example.com / {AMO_ADMIN_PASSWORD}")
    print(f"Quality login: quality@demo.example.com / {AMO_ADMIN_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
