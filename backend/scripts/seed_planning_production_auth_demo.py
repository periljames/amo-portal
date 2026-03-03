#!/usr/bin/env python3
"""Authoritative end-to-end demo seed for Planning/Production/Quality/Records verification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE_URL = os.getenv("AMO_API_URL", "http://localhost:8080").rstrip("/")
SUPERUSER_EMAIL = os.getenv("AMO_SUPERUSER_EMAIL", "owner@example.com")
SUPERUSER_PASSWORD = os.getenv("AMO_SUPERUSER_PASSWORD", "ChangeMe123!")
AMO_LOGIN_SLUG = os.getenv("AMO_LOGIN_SLUG", "demo-amo")
AMO_ADMIN_PASSWORD = os.getenv("AMO_ADMIN_PASSWORD", "ChangeMe123!")
ALT_DEMO_PASSWORD = os.getenv("AMO_ALT_DEMO_PASSWORD", "ChangeMe1234A")
AIRCRAFT_SERIAL = os.getenv("AMO_AIRCRAFT_SERIAL", "DEMO-001")
AIRCRAFT_REG = os.getenv("AMO_AIRCRAFT_REG", "N-DEMO")


@dataclass(frozen=True)
class DemoUser:
    email: str
    role: str
    label: str


DEMO_USERS: tuple[DemoUser, ...] = (
    DemoUser("planner@demo.example.com", "PLANNING_ENGINEER", "Planner"),
    DemoUser("production@demo.example.com", "PRODUCTION_ENGINEER", "Production"),
    DemoUser("quality@demo.example.com", "QUALITY_MANAGER", "Quality"),
    DemoUser("records@demo.example.com", "CERTIFYING_ENGINEER", "Records"),
)

ROLE_DEPARTMENT_CODE: dict[str, str] = {
    "PLANNING_ENGINEER": "planning",
    "PRODUCTION_ENGINEER": "production",
    "QUALITY_MANAGER": "quality",
    "CERTIFYING_ENGINEER": "production",
}

REQUIRED_MODULES: tuple[str, ...] = (
    "fleet",
    "reliability",
    "maintenance_program",
    "work",
    "quality",
    "training",
)

BASE_SEED_SCRIPT = "backend/scripts/seed_demo.py"
FOLLOW_ON_SEED_SCRIPTS: tuple[str, ...] = (
    "backend/scripts/seed_maintenance_module_demo.py",
    "backend/scripts/seed_technical_records_demo.py",
)


def req(method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None) -> Any:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
    )
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {path} -> {exc.code} {exc.read().decode('utf-8')}") from exc


def safe(method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None):
    try:
        return req(method, path, payload, token)
    except RuntimeError as exc:
        print(exc)
        return None


def login(email: str, password: str, amo_slug: str, *, fallback_password: str | None = None) -> str:
    try:
        response = req("POST", "/auth/login", {"email": email, "password": password, "amo_slug": amo_slug})
        return response["access_token"]
    except RuntimeError:
        if not fallback_password or fallback_password == password:
            raise
        response = req("POST", "/auth/login", {"email": email, "password": fallback_password, "amo_slug": amo_slug})
        return response["access_token"]


def run_seed_script(script: str, *, allow_failure: bool = False) -> None:
    env = os.environ.copy()
    result = subprocess.run([sys.executable, script], check=False, env=env)
    if result.returncode != 0 and not allow_failure:
        raise subprocess.CalledProcessError(result.returncode, [sys.executable, script])


def ensure_modules(super_token: str, amo_id: str) -> None:
    for module in REQUIRED_MODULES:
        safe("POST", f"/admin/tenants/{amo_id}/modules/{module}/enable", {"module_code": module, "status": "ENABLED"}, super_token)


def get_department_ids(super_token: str, amo_id: str) -> dict[str, str]:
    departments = req("GET", f"/accounts/admin/departments?amo_id={amo_id}", token=super_token) or []
    return {
        (dept.get("code") or "").strip().lower(): dept.get("id")
        for dept in departments
        if dept.get("id") and dept.get("code")
    }


def find_user_by_email(super_token: str, amo_id: str, email: str) -> dict[str, Any] | None:
    users = req("GET", f"/accounts/admin/users?amo_id={amo_id}&limit=500", token=super_token) or []
    email_lower = email.strip().lower()
    for user in users:
        if (user.get("email") or "").strip().lower() == email_lower:
            return user
    return None


def ensure_user_department(super_token: str, amo_id: str, user: DemoUser, department_id: str | None) -> None:
    existing = find_user_by_email(super_token, amo_id, user.email)
    if not existing:
        return
    if department_id and existing.get("department_id") == department_id:
        return
    safe(
        "PUT",
        f"/accounts/admin/users/{existing['id']}",
        {
            "department_id": department_id,
            "position_title": user.label,
            "phone": "+10000000000",
        },
        super_token,
    )


def ensure_users(super_token: str, amo_id: str) -> None:
    department_ids = get_department_ids(super_token, amo_id)
    for user in DEMO_USERS:
        dept_code = ROLE_DEPARTMENT_CODE.get(user.role, "")
        department_id = department_ids.get(dept_code)
        safe(
            "POST",
            "/accounts/admin/users",
            {
                "email": user.email,
                "password": AMO_ADMIN_PASSWORD,
                "first_name": user.label,
                "last_name": "Demo",
                "full_name": f"{user.label} Demo",
                "role": user.role,
                "position_title": user.label,
                "phone": "+10000000000",
                "amo_id": amo_id,
                "staff_code": f"DEMO-{user.role}",
                "department_id": department_id,
            },
            super_token,
        )
        ensure_user_department(super_token, amo_id, user, department_id)


def ensure_seed_aircraft(amo_admin_token: str) -> None:
    safe(
        "POST",
        "/aircraft/",
        {
            "serial_number": AIRCRAFT_SERIAL,
            "registration": AIRCRAFT_REG,
            "template": "DHC8",
            "make": "De Havilland",
            "model": "Dash 8",
        },
        amo_admin_token,
    )


def seed_watchlists_and_compliance(planner_token: str) -> None:
    wl = safe(
        "POST",
        "/records/watchlists",
        {"name": "Demo AD/SB", "criteria_json": {"keywords": ["fuel", "wing"]}},
        planner_token,
    )
    if wl:
        safe("POST", f"/records/watchlists/{wl['id']}/run", {}, planner_token)

    queue = safe("GET", "/records/publications/review", None, planner_token) or []
    for row in queue[:2]:
        safe(
            "POST",
            f"/records/publications/review/{row['match_id']}/decision",
            {"review_status": "Under Review", "classification": "Applicable"},
            planner_token,
        )
        safe(
            "POST",
            "/records/compliance-actions",
            {
                "publication_match_id": row["match_id"],
                "decision": "ADD_TO_EXISTING_WORK_PACKAGE",
                "status": "Planned",
            },
            planner_token,
        )


def seed_production_handoff(prod_token: str) -> None:
    work_orders = safe("GET", "/work-orders/?limit=20", None, prod_token) or []
    if not work_orders:
        return

    work_order = work_orders[0]
    tasks = safe("GET", f"/work-orders/{work_order['id']}/tasks", None, prod_token) or []
    if tasks:
        task = tasks[0]
        safe(
            "PUT",
            f"/work-orders/tasks/{task['id']}",
            {"status": "IN_PROGRESS", "last_known_updated_at": task["updated_at"]},
            prod_token,
        )
        updated_task = safe("GET", f"/work-orders/tasks/{task['id']}", None, prod_token)
        if updated_task:
            safe(
                "PUT",
                f"/work-orders/tasks/{task['id']}",
                {"status": "COMPLETED", "last_known_updated_at": updated_task["updated_at"]},
                prod_token,
            )

    safe(
        "POST",
        "/records/production/release-gates",
        {
            "work_order_id": work_order["id"],
            "status": "Ready",
            "readiness_notes": "Seeded release prep",
            "blockers_json": [],
        },
        prod_token,
    )


def main() -> int:
    run_seed_script(BASE_SEED_SCRIPT)

    super_token = login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD, "system")
    amos = req("GET", "/accounts/admin/amos", token=super_token)
    amo = next((item for item in amos if item.get("login_slug") == AMO_LOGIN_SLUG), amos[0])
    ensure_modules(super_token, amo["id"])
    ensure_users(super_token, amo["id"])

    amo_admin_token = login("admin@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG, fallback_password=ALT_DEMO_PASSWORD)
    ensure_seed_aircraft(amo_admin_token)

    for script in FOLLOW_ON_SEED_SCRIPTS:
        run_seed_script(script, allow_failure=True)

    planner_token = login("planner@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG, fallback_password=ALT_DEMO_PASSWORD)
    seed_watchlists_and_compliance(planner_token)

    production_token = login("production@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG, fallback_password=ALT_DEMO_PASSWORD)
    seed_production_handoff(production_token)

    print("Demo seed complete")
    print(f"Tenant: {AMO_LOGIN_SLUG}")
    for user in DEMO_USERS:
        print(f"{user.label} login: {user.email} / {AMO_ADMIN_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
