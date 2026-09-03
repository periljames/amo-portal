#!/usr/bin/env python3
"""Seed a realistic SaaS platform-control dataset for the superadmin console.

This populates the tenant fleet, commercial plan catalog, subscriptions,
invoices (paid / pending / overdue), support tickets and security incidents so
every tab of the Platform Control console renders live data instead of empty
states. It drives the same HTTP endpoints the superadmin UI uses, so it also
serves as a smoke test of those write paths.

Usage (with the dev runtime up and .env.development loaded):

    AMO_API_URL=http://127.0.0.1:8080 \
    AMO_OPS_URL=http://127.0.0.1:8090 \
    AMO_SUPERUSER_EMAIL=admin@venspera.dev \
    AMO_SUPERUSER_PASSWORD='DevAdmin123!' \
    python -m amodb.scripts.seed_platform_demo
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib import error, request

API_BASE = os.getenv("AMO_API_URL", "http://127.0.0.1:8080").rstrip("/")
OPS_BASE = os.getenv("AMO_OPS_URL", "http://127.0.0.1:8090").rstrip("/")
SUPERUSER_EMAIL = os.getenv("AMO_SUPERUSER_EMAIL", "admin@venspera.dev")
SUPERUSER_PASSWORD = os.getenv("AMO_SUPERUSER_PASSWORD", "DevAdmin123!")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _request(method: str, base: str, path: str, payload: Optional[dict] = None, token: Optional[str] = None) -> Any:
    url = f"{base}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with request.urlopen(req) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else None
    except error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def _safe(method: str, base: str, path: str, payload: Optional[dict] = None, token: Optional[str] = None) -> Optional[Any]:
    try:
        return _request(method, base, path, payload, token)
    except RuntimeError as exc:
        print(f"  ! {exc}")
        return None


def login() -> str:
    payload = {"amo_slug": "system", "email": SUPERUSER_EMAIL, "password": SUPERUSER_PASSWORD}
    return _request("POST", API_BASE, "/auth/login", payload)["access_token"]


CATALOG = [
    {"code": "STARTER", "name": "Starter", "term": "MONTHLY", "amount_cents": 4900, "currency": "USD", "trial_days": 14, "description": "Single-base AMO, core QMS + fleet."},
    {"code": "PRO", "name": "Professional", "term": "MONTHLY", "amount_cents": 19900, "currency": "USD", "trial_days": 14, "description": "Multi-base, rostering, reliability, document control."},
    {"code": "ENTERPRISE", "name": "Enterprise", "term": "MONTHLY", "amount_cents": 99900, "currency": "USD", "trial_days": 0, "description": "Unlimited bases, SSO, priority support, SLAs."},
]

TENANTS = [
    {"name": "Rift Valley Aerotech", "amo_code": "RVA", "login_slug": "rift-valley", "owner_email": "ops@riftvalleyaero.example", "region": "KE", "plan": "PRO", "status": "ACTIVE"},
    {"name": "Sahara Wings MRO", "amo_code": "SWM", "login_slug": "sahara-wings", "owner_email": "admin@saharawings.example", "region": "MA", "plan": "ENTERPRISE", "status": "ACTIVE"},
    {"name": "Coastal Aviation Technics", "amo_code": "CAT", "login_slug": "coastal-avionics", "owner_email": "quality@coastalavtech.example", "region": "ZA", "plan": "STARTER", "status": "TRIALING"},
    {"name": "Highland Rotor Services", "amo_code": "HRS", "login_slug": "highland-rotor", "owner_email": "maint@highlandrotor.example", "region": "GB", "plan": "PRO", "status": "ACTIVE"},
]


def ensure_catalog(token: str) -> None:
    print("Seeding commercial plan catalog...")
    existing = _safe("GET", API_BASE, "/billing/catalog?include_inactive=true", token=token) or []
    codes = {str(item.get("code")) for item in existing} if isinstance(existing, list) else set()
    for sku in CATALOG:
        if sku["code"] in codes:
            print(f"  = SKU {sku['code']} already present")
            continue
        if _safe("POST", API_BASE, "/billing/catalog", sku, token=token):
            print(f"  + SKU {sku['code']}")


def existing_tenants(token: str) -> dict[str, dict]:
    data = _safe("GET", API_BASE, "/platform/tenants", token=token) or {}
    items = data.get("items") if isinstance(data, dict) else data
    result: dict[str, dict] = {}
    for row in items or []:
        slug = row.get("login_slug") or row.get("slug")
        if slug:
            result[str(slug)] = row
    return result


def ensure_tenant(token: str, spec: dict, known: dict[str, dict]) -> Optional[dict]:
    if spec["login_slug"] in known:
        print(f"  = Tenant {spec['name']} already present")
        return known[spec["login_slug"]]
    created = _safe("POST", API_BASE, "/platform/tenants", {
        "name": spec["name"],
        "amo_code": spec["amo_code"],
        "login_slug": spec["login_slug"],
        "owner_email": spec["owner_email"],
        "region": spec["region"],
        "plan": spec["plan"],
    }, token=token)
    if created:
        print(f"  + Tenant {spec['name']}")
    return created


def _tenant_id(detail: Optional[dict]) -> Optional[str]:
    if not detail:
        return None
    if detail.get("id"):
        return str(detail["id"])
    tenant = detail.get("tenant") or detail.get("amo") or {}
    return str(tenant.get("id")) if tenant.get("id") else None


def assign_subscription(token: str, amo_id: str, spec: dict) -> None:
    status = "TRIALING" if spec["status"] == "TRIALING" else "ACTIVE"
    _safe("POST", API_BASE, f"/accounts/admin/platform/tenants/{amo_id}/subscription", {
        "sku_code": spec["plan"],
        "status": status,
        "notes": "Seeded by seed_platform_demo",
    }, token=token)


def seed_invoices(token: str, amo_id: str, spec: dict) -> None:
    price = next((s["amount_cents"] for s in CATALOG if s["code"] == spec["plan"]), 9900)
    now = datetime.now(timezone.utc)
    # A settled invoice, an open one, and (for active plans) an overdue one.
    _safe("POST", API_BASE, f"/platform/billing/tenants/{amo_id}/manual-invoice", {
        "amount_cents": price, "currency": "USD", "description": f"{spec['plan']} plan - previous period", "mark_paid": True,
    }, token=token)
    _safe("POST", API_BASE, f"/platform/billing/tenants/{amo_id}/manual-invoice", {
        "amount_cents": price, "currency": "USD", "description": f"{spec['plan']} plan - current period", "due_at": _iso(now + timedelta(days=20)),
    }, token=token)
    if spec["status"] == "ACTIVE" and spec["plan"] != "STARTER":
        _safe("POST", API_BASE, f"/platform/billing/tenants/{amo_id}/manual-invoice", {
            "amount_cents": price // 3, "currency": "USD", "description": "Metered usage overage", "due_at": _iso(now - timedelta(days=9)),
        }, token=token)


SUPPORT_TICKETS = [
    {"title": "SSO metadata rejected on login", "description": "Enterprise IdP SAML metadata upload returns a validation error.", "priority": "HIGH", "category": "TECHNICAL"},
    {"title": "Invoice PDF shows wrong tax label", "description": "Latest invoice renders VAT instead of the configured tax label.", "priority": "NORMAL", "category": "BILLING"},
    {"title": "Request additional base station", "description": "We need to add a second maintenance base to our subscription.", "priority": "NORMAL", "category": "GENERAL"},
    {"title": "Rostering export timing out", "description": "Monthly duty roster export times out for large crews.", "priority": "URGENT", "category": "TECHNICAL"},
]


def seed_tickets(token: str, tenants: list[dict]) -> None:
    print("Seeding support tickets...")
    for idx, ticket in enumerate(SUPPORT_TICKETS):
        tenant = tenants[idx % len(tenants)] if tenants else None
        payload = dict(ticket)
        if tenant:
            payload["tenant_id"] = tenant["id"]
        if _safe("POST", API_BASE, "/platform/saas/support/tickets", payload, token=token):
            print(f"  + Ticket: {ticket['title']}")


INCIDENTS = [
    {"title": "Elevated API error rate on /work-orders", "severity": "HIGH", "description": "5xx rate crossed the fast-burn SLO threshold for 6 minutes."},
    {"title": "Database connection pool saturation", "severity": "MEDIUM", "description": "Pool utilisation peaked at 82% during nightly report generation."},
]


def seed_incidents(token: str, tenants: list[dict]) -> None:
    print("Seeding security incidents...")
    for idx, incident in enumerate(INCIDENTS):
        payload = dict(incident)
        if tenants:
            payload["tenant_id"] = tenants[idx % len(tenants)]["id"]
        if _safe("POST", OPS_BASE, "/ops/v1/incidents", payload, token=token):
            print(f"  + Incident: {incident['title']}")


def main() -> int:
    print(f"Authenticating as {SUPERUSER_EMAIL} ...")
    token = login()
    ensure_catalog(token)

    print("Provisioning demo tenants...")
    known = existing_tenants(token)
    tenant_records: list[dict] = []
    for spec in TENANTS:
        detail = ensure_tenant(token, spec, known)
        amo_id = _tenant_id(detail)
        if not amo_id:
            continue
        assign_subscription(token, amo_id, spec)
        seed_invoices(token, amo_id, spec)
        tenant_records.append({"id": amo_id, "name": spec["name"]})

    seed_tickets(token, tenant_records)
    seed_incidents(token, tenant_records)

    # Refresh the platform monitor so infrastructure/health cards have a sample.
    _safe("POST", API_BASE, "/platform/diagnostics/run", {"reason": "Seed data diagnostics"}, token=token)

    print(f"Done. Seeded {len(tenant_records)} tenants with plans, invoices, tickets and incidents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
