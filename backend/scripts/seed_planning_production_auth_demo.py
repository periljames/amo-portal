#!/usr/bin/env python3
"""Authoritative end-to-end demo seed for Planning/Production/Quality/Records verification."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE_URL = os.getenv("AMO_API_URL", "http://localhost:8080").rstrip("/")
SUPERUSER_EMAIL = os.getenv("AMO_SUPERUSER_EMAIL", "owner@example.com")
SUPERUSER_PASSWORD = os.getenv("AMO_SUPERUSER_PASSWORD", "ChangeMe123!")
AMO_LOGIN_SLUG = os.getenv("AMO_LOGIN_SLUG", "demo-amo")
AMO_CODE = os.getenv("AMO_CODE", "DEMO")
AMO_NAME = os.getenv("AMO_NAME", "Demo AMO")
AMO_ADMIN_EMAIL = os.getenv("AMO_ADMIN_EMAIL", "admin@demo.example.com")
AMO_ADMIN_PASSWORD = os.getenv("AMO_ADMIN_PASSWORD", "ChangeMe123!")
ALT_DEMO_PASSWORD = os.getenv("AMO_ALT_DEMO_PASSWORD", "ChangeMe1234A")
AIRCRAFT_SERIAL = os.getenv("AMO_AIRCRAFT_SERIAL", "DEMO-001")
AIRCRAFT_REG = os.getenv("AMO_AIRCRAFT_REG", "N-DEMO")
DEFAULT_TRIAL_SKU = os.getenv("AMODB_DEFAULT_TRIAL_SKU", "DEMO-MONTHLY")
SEED_AIRCRAFT = os.getenv("AMO_SEED_AIRCRAFT", "0") == "1"


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

RESOLVED_PASSWORDS: dict[str, str] = {}


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


def bootstrap_superuser() -> None:
    safe(
        "POST",
        "/auth/first-superuser",
        {
            "email": SUPERUSER_EMAIL,
            "password": SUPERUSER_PASSWORD,
            "first_name": "Platform",
            "last_name": "Owner",
            "full_name": "Platform Owner",
            "position_title": "System Owner",
            "phone": "+10000000000",
            "staff_code": "ROOT-001",
        },
    )


def login(email: str, password: str, amo_slug: str, *, fallback_password: str | None = None) -> str:
    ordered_passwords = []
    cached = RESOLVED_PASSWORDS.get(email)
    if cached:
        ordered_passwords.append(cached)
    ordered_passwords.append(password)
    if fallback_password and fallback_password != password:
        ordered_passwords.append(fallback_password)

    seen = set()
    last_exc: RuntimeError | None = None
    for candidate in ordered_passwords:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            response = req("POST", "/auth/login", {"email": email, "password": candidate, "amo_slug": amo_slug})
            RESOLVED_PASSWORDS[email] = candidate
            return response["access_token"]
        except RuntimeError as exc:
            last_exc = exc
            if " 401 " in str(exc) or " 429 " in str(exc):
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Unable to authenticate {email}")


def try_login(email: str, password: str, amo_slug: str, *, fallback_password: str | None = None) -> str | None:
    try:
        return login(email, password, amo_slug, fallback_password=fallback_password)
    except RuntimeError as exc:
        if " 429 " in str(exc):
            print(f"Skipping {email} login due to auth throttling; rerun after cooldown.")
            return None
        raise


def ensure_catalog_sku(super_token: str) -> str:
    skus = req("GET", "/billing/catalog", token=super_token) or []
    for sku in skus:
        if sku.get("is_active"):
            return sku["code"]

    created = req(
        "POST",
        "/billing/catalog",
        {
            "code": DEFAULT_TRIAL_SKU,
            "name": "Demo Monthly",
            "description": "Default demo trial SKU",
            "term": "MONTHLY",
            "trial_days": 14,
            "amount_cents": 0,
            "currency": "USD",
            "is_active": True,
        },
        super_token,
    )
    return created["code"]


def ensure_amo(super_token: str) -> dict[str, Any]:
    amos = req("GET", "/accounts/admin/amos", token=super_token) or []
    for item in amos:
        if item.get("login_slug") == AMO_LOGIN_SLUG:
            return item

    created = req(
        "POST",
        "/accounts/admin/amos",
        {
            "amo_code": AMO_CODE,
            "name": AMO_NAME,
            "icao_code": None,
            "country": "US",
            "login_slug": AMO_LOGIN_SLUG,
            "contact_email": AMO_ADMIN_EMAIL,
            "contact_phone": "+10000000000",
            "time_zone": "UTC",
            "is_demo": True,
        },
        super_token,
    )
    return created


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


def ensure_user_department(super_token: str, user_id: str, user: DemoUser, department_id: str | None) -> None:
    safe(
        "PUT",
        f"/accounts/admin/users/{user_id}",
        {
            "department_id": department_id,
            "position_title": user.label,
            "phone": "+10000000000",
        },
        super_token,
    )


def ensure_admin_user(super_token: str, amo_id: str) -> None:
    existing = find_user_by_email(super_token, amo_id, AMO_ADMIN_EMAIL)
    if existing:
        return
    safe(
        "POST",
        "/accounts/admin/users",
        {
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
        },
        super_token,
    )


def ensure_demo_users(super_token: str, amo_id: str) -> None:
    department_ids = get_department_ids(super_token, amo_id)
    for user in DEMO_USERS:
        dept_code = ROLE_DEPARTMENT_CODE.get(user.role, "")
        department_id = department_ids.get(dept_code)
        existing = find_user_by_email(super_token, amo_id, user.email)
        if not existing:
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
            existing = find_user_by_email(super_token, amo_id, user.email)

        if existing and existing.get("department_id") != department_id:
            ensure_user_department(super_token, existing["id"], user, department_id)


def ensure_modules(super_token: str, amo_id: str) -> None:
    current = req("GET", f"/admin/tenants/{amo_id}/modules", token=super_token) or []
    enabled = {
        item.get("module_code")
        for item in current
        if (item.get("status") or "").upper() == "ENABLED"
    }
    for module in REQUIRED_MODULES:
        if module in enabled:
            continue
        safe(
            "POST",
            f"/admin/tenants/{amo_id}/modules/{module}/enable",
            {"module_code": module, "status": "ENABLED"},
            super_token,
        )


def ensure_seed_aircraft(amo_admin_token: str) -> None:
    if not SEED_AIRCRAFT:
        return
    aircraft = safe("GET", "/aircraft/?limit=200", None, amo_admin_token)
    if aircraft is None:
        print("Skipping aircraft seed because aircraft listing endpoint is unavailable in this runtime.")
        return
    if any(a.get("serial_number") == AIRCRAFT_SERIAL for a in aircraft):
        return
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
    watchlists = safe("GET", "/records/watchlists", None, planner_token) or []
    wl = next((w for w in watchlists if w.get("name") == "Demo AD/SB"), None)
    if not wl:
        wl = safe(
            "POST",
            "/records/watchlists",
            {"name": "Demo AD/SB", "criteria_json": {"keywords": ["fuel", "wing"]}},
            planner_token,
        )
    if wl:
        safe("POST", f"/records/watchlists/{wl['id']}/run", {}, planner_token)

    queue = safe("GET", "/records/publications/review", None, planner_token) or []
    existing_actions = safe("GET", "/records/compliance-actions", None, planner_token) or []
    existing_match_ids = {a.get("publication_match_id") for a in existing_actions if a.get("publication_match_id")}

    for row in queue[:2]:
        safe(
            "POST",
            f"/records/publications/review/{row['match_id']}/decision",
            {"review_status": "Under Review", "classification": "Applicable"},
            planner_token,
        )
        if row.get("match_id") in existing_match_ids:
            continue
        created = safe(
            "POST",
            "/records/compliance-actions",
            {
                "publication_match_id": row["match_id"],
                "decision": "ADD_TO_EXISTING_WORK_PACKAGE",
                "status": "Planned",
            },
            planner_token,
        )
        if created:
            existing_match_ids.add(row.get("match_id"))


def seed_production_handoff(prod_token: str) -> None:
    work_orders = safe("GET", "/work-orders/?limit=20", None, prod_token) or []
    if not work_orders:
        return

    work_order = work_orders[0]
    tasks = safe("GET", f"/work-orders/{work_order['id']}/tasks", None, prod_token) or []
    if tasks:
        task = tasks[0]
        if task.get("status") != "COMPLETED":
            safe(
                "PUT",
                f"/work-orders/tasks/{task['id']}",
                {"status": "IN_PROGRESS", "last_known_updated_at": task["updated_at"]},
                prod_token,
            )
            updated_task = safe("GET", f"/work-orders/tasks/{task['id']}", None, prod_token)
            if updated_task and updated_task.get("status") != "COMPLETED":
                safe(
                    "PUT",
                    f"/work-orders/tasks/{task['id']}",
                    {"status": "COMPLETED", "last_known_updated_at": updated_task["updated_at"]},
                    prod_token,
                )

    gates = safe("GET", "/records/production/release-gates", None, prod_token) or []
    existing_gate = next((g for g in gates if g.get("work_order_id") == work_order["id"]), None)
    desired_status = "Ready"
    if existing_gate and existing_gate.get("status") == desired_status:
        return

    safe(
        "POST",
        "/records/production/release-gates",
        {
            "work_order_id": work_order["id"],
            "status": desired_status,
            "readiness_notes": "Seeded release prep",
            "blockers_json": [],
        },
        prod_token,
    )


def main() -> int:
    print("Logging in as platform superuser...")
    try:
        super_token = login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD, "system")
    except RuntimeError:
        print("Bootstrapping superuser (if needed)...")
        bootstrap_superuser()
        super_token = login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD, "system")

    ensure_catalog_sku(super_token)
    amo = ensure_amo(super_token)

    ensure_modules(super_token, amo["id"])
    ensure_admin_user(super_token, amo["id"])
    ensure_demo_users(super_token, amo["id"])

    print("Logging in as AMO admin...")
    amo_admin_token = try_login(AMO_ADMIN_EMAIL, AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG, fallback_password=ALT_DEMO_PASSWORD)
    if not amo_admin_token:
        print("Demo seed paused due to auth throttling before AMO admin login.")
        return 0
    ensure_seed_aircraft(amo_admin_token)

    planner_token = try_login("planner@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG, fallback_password=ALT_DEMO_PASSWORD)
    if planner_token:
        seed_watchlists_and_compliance(planner_token)

    production_token = try_login("production@demo.example.com", AMO_ADMIN_PASSWORD, AMO_LOGIN_SLUG, fallback_password=ALT_DEMO_PASSWORD)
    if production_token:
        seed_production_handoff(production_token)

    print("Demo seed complete")
    print(f"Tenant: {AMO_LOGIN_SLUG}")
    for user in DEMO_USERS:
        resolved = RESOLVED_PASSWORDS.get(user.email, AMO_ADMIN_PASSWORD)
        print(f"{user.label} login: {user.email} / {resolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
