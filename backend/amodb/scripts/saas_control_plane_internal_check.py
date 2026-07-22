from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"


REQUIRED_CHECKS = {
    "saas_models": (
        BACKEND_ROOT / "amodb/apps/platform/saas_models.py",
        [
            "class SaaSProviderCredential",
            "class SaaSJob",
            "class SaaSModulePrice",
            "class SaaSBillingAccount",
            "class SaaSInvoiceFiscalization",
            "class SaaSSupportTicketMessage",
            "uq_saas_job_idempotency",
            "ix_saas_jobs_claim",
        ],
    ),
    "encrypted_secrets": (
        BACKEND_ROOT / "amodb/apps/platform/saas_secrets.py",
        [
            "PLATFORM_SECRETS_KEY",
            "Fernet",
            "def encrypt_secret",
            "def decrypt_secret",
            "def redact_mapping",
        ],
    ),
    "durable_queue": (
        BACKEND_ROOT / "amodb/apps/platform/saas_queue.py",
        [
            "with_for_update(skip_locked=True)",
            "def enqueue_job",
            "def claim_jobs",
            "def release_expired_leases",
            "def complete_job",
            "def fail_job",
            "def queue_summary",
        ],
    ),
    "provider_adapters": (
        BACKEND_ROOT / "amodb/apps/platform/saas_providers.py",
        [
            'ProviderDefinition("stripe"',
            'ProviderDefinition("mpesa_daraja"',
            'ProviderDefinition("etims_oscu"',
            'ProviderDefinition("smtp"',
            'ProviderDefinition("openai"',
            "def verify_stripe_signature",
            "def create_stripe_checkout_session",
            "def fiscalize_etims_invoice",
        ],
    ),
    "saas_routes": (
        BACKEND_ROOT / "amodb/apps/platform/saas_router.py",
        [
            '@platform_saas_router.get("/capabilities")',
            '@platform_saas_router.get("/providers")',
            '@platform_saas_router.get("/jobs")',
            '@platform_saas_router.get("/module-prices")',
            '@platform_saas_router.patch("/tenants/{tenant_id}/modules")',
            '@platform_saas_router.post("/billing/tenants/{tenant_id}/checkout"',
            '@platform_saas_router.post("/billing/invoices/{invoice_id}/fiscalize"',
            '@webhook_router.post("/stripe"',
            '@support_router.post("/tickets"',
        ],
    ),
    "saas_workers": (
        BACKEND_ROOT / "amodb/jobs/saas_worker.py",
        [
            "STRIPE_CREATE_CHECKOUT_SESSION",
            "STRIPE_WEBHOOK",
            "ETIMS_FISCALIZE_INVOICE",
            "AI_SUPPORT_REPLY",
            "def run_once",
            "def run_forever",
        ],
    ),
    "legacy_command_queue": (
        BACKEND_ROOT / "amodb/apps/platform/saas_legacy_bridge.py",
        [
            "def install_legacy_command_queue",
            'job.status = "QUEUED"',
            'job_type="PLATFORM_COMMAND_JOB"',
            "execute_legacy_command_in_worker",
        ],
    ),
    "atomic_usage": (
        BACKEND_ROOT / "amodb/apps/platform/saas_usage.py",
        [
            "ON CONFLICT (amo_id, meter_key)",
            "usage_meters.used_units + EXCLUDED.used_units",
            "application._queue_api_usage = enqueue_only",
            'name="api-usage-flush"',
        ],
    ),
    "integration_health": (
        BACKEND_ROOT / "amodb/apps/platform/saas_integration.py",
        [
            'integration_router = APIRouter(prefix="/saas/integration-health"',
            "quality_training",
            "saas_worker_online",
            "capacity_position",
            "verified_by_this_endpoint",
        ],
    ),
    "migration": (
        BACKEND_ROOT / "amodb/alembic/versions/saas_20260722_control_plane_foundation.py",
        [
            'revision = "saas_20260722_control_plane"',
            'down_revision = "quality_20260722_schema_integrity"',
            '"saas_provider_credentials"',
            '"saas_jobs"',
            '"saas_module_prices"',
            '"saas_invoice_fiscalizations"',
            '"saas_support_ticket_messages"',
        ],
    ),
    "frontend_service": (
        FRONTEND_ROOT / "src/services/platformControl.ts",
        [
            "export type SaaSJob",
            "export type SaaSProvider",
            "saasCapabilities:",
            "updateSaasProvider:",
            "updateTenantModules:",
            "createManualInvoice:",
            "createCheckout:",
            "fiscalizeInvoice:",
            "requestAiSupportReply:",
            "globalThis.setTimeout",
        ],
    ),
    "frontend_controls": (
        FRONTEND_ROOT / "src/pages/platform/PlatformIntegrationsPage.tsx",
        [
            "Provider registry",
            "Integration queue",
            "Support desk",
            "Queue AI draft",
            "Secrets are encrypted on the backend",
        ],
    ),
    "frontend_billing": (
        FRONTEND_ROOT / "src/pages/platform/PlatformBillingPage.tsx",
        [
            "Module price catalog",
            "Queue recurring checkout",
            "Fiscalize OSCU",
            "Billing queue",
        ],
    ),
    "frontend_tenants": (
        FRONTEND_ROOT / "src/pages/platform/PlatformTenantsPage.tsx",
        [
            "Module subscription control",
            "Save module subscriptions",
            "Previous",
            "Next",
        ],
    ),
    "load_profile": (
        ROOT / "loadtests/k6_saas_control_plane.js",
        [
            "TENANT_VUS || 1000",
            "http_req_failed",
            '"p(95)<800"',
            "tenant_quality_training_reads",
            "/quality/calendar",
        ],
    ),
}


FORBIDDEN_CHECKS = {
    "frontend_browser_secrets": (
        FRONTEND_ROOT / "src/services/platformControl.ts",
        ["localStorage.setItem(\"stripe", "localStorage.setItem(\"openai", "VITE_OPENAI_API_KEY", "VITE_STRIPE_SECRET"],
    ),
    "provider_plaintext_secret_response": (
        BACKEND_ROOT / "amodb/apps/platform/saas_services.py",
        ['"encrypted_secret":', '"secret": provider_secrets', '"api_key": secret'],
    ),
    "legacy_inline_command_execution": (
        BACKEND_ROOT / "amodb/apps/platform/saas_legacy_bridge.py",
        ["original_execute(db, job, actor_id=actor_id)\n        db.commit()"],
    ),
}


COMPILE_TARGETS = [
    path
    for path, _ in REQUIRED_CHECKS.values()
    if path.suffix == ".py"
] + [
    BACKEND_ROOT / "amodb/jobs/platform_command_worker.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_control_plane.py",
    Path(__file__),
]


def missing(text: str, needles: Iterable[str]) -> list[str]:
    return [needle for needle in needles if needle not in text]


def present(text: str, needles: Iterable[str]) -> list[str]:
    return [needle for needle in needles if needle in text]


def display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT.parent))
    except ValueError:
        return str(path)


def main() -> int:
    passed = True
    results: dict[str, object] = {}
    for name, (path, needles) in REQUIRED_CHECKS.items():
        if not path.exists():
            passed = False
            results[name] = {"passed": False, "path": display(path), "missing": list(needles)}
            continue
        absent = missing(path.read_text(encoding="utf-8"), needles)
        ok = not absent
        passed = passed and ok
        results[name] = {"passed": ok, "path": display(path), "missing": absent}

    for name, (path, needles) in FORBIDDEN_CHECKS.items():
        found = present(path.read_text(encoding="utf-8"), needles) if path.exists() else []
        ok = path.exists() and not found
        passed = passed and ok
        results[name] = {"passed": ok, "path": display(path), "present": found}

    compile_results = []
    for target in COMPILE_TARGETS:
        try:
            py_compile.compile(str(target), doraise=True)
            compile_results.append({"path": display(target), "passed": True})
        except Exception as exc:
            passed = False
            compile_results.append({"path": display(target), "passed": False, "error": str(exc)})

    package_json = FRONTEND_ROOT / "package.json"
    package = json.loads(package_json.read_text(encoding="utf-8"))
    script = package.get("scripts", {}).get("test:platform")
    script_ok = script == "vitest run src/services/platformControl.test.ts"
    passed = passed and script_ok
    results["frontend_test_script"] = {"passed": script_ok, "command": script}

    print(json.dumps({"passed": passed, "checks": results, "compile": compile_results}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
