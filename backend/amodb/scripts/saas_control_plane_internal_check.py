from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"

REQUIRED_CHECKS: dict[str, tuple[Path, list[str]]] = {
    "saas_models": (
        BACKEND_ROOT / "amodb/apps/platform/saas_models.py",
        ["class SaaSProviderCredential", "class SaaSJob", "class SaaSModulePrice", "class SaaSInvoiceFiscalization", "uq_saas_job_idempotency", "ix_saas_jobs_claim"],
    ),
    "encrypted_secrets": (
        BACKEND_ROOT / "amodb/apps/platform/saas_secrets.py",
        ["PLATFORM_SECRETS_KEY", "Fernet", "def encrypt_secret", "def decrypt_secret", "def redact_mapping"],
    ),
    "durable_queue": (
        BACKEND_ROOT / "amodb/apps/platform/saas_queue.py",
        [
            "with_for_update(skip_locked=True)",
            "RETRYABLE_MANUAL_STATUSES",
            "safe claim width is deliberately one",
            ".limit(1)",
            "Only an actively leased job can be completed",
            "Only an actively leased job can be failed",
            "def enqueue_job",
            "def claim_jobs",
            "def release_expired_leases",
            "def heartbeat_job",
            "def complete_job",
            "def fail_job",
        ],
    ),
    "provider_adapters": (
        BACKEND_ROOT / "amodb/apps/platform/saas_providers.py",
        ['ProviderDefinition("stripe"', 'ProviderDefinition("mpesa_daraja"', 'ProviderDefinition("etims_oscu"', 'ProviderDefinition("smtp"', 'ProviderDefinition("openai"', "def verify_stripe_signature", "def create_stripe_checkout_session", "def fiscalize_etims_invoice"],
    ),
    "saas_routes": (
        BACKEND_ROOT / "amodb/apps/platform/saas_router.py",
        ['@platform_saas_router.get("/capabilities")', '@platform_saas_router.get("/providers")', '@platform_saas_router.get("/jobs")', '@platform_saas_router.get("/module-prices")', '@platform_saas_router.patch("/tenants/{tenant_id}/modules")', '@webhook_router.post("/stripe"', '@support_router.post("/tickets"', "def _visible_support_payload"],
    ),
    "saas_workers": (
        BACKEND_ROOT / "amodb/jobs/saas_worker.py",
        ["STRIPE_CREATE_CHECKOUT_SESSION", "STRIPE_WEBHOOK", "ETIMS_FISCALIZE_INVOICE", "AI_SUPPORT_REPLY", "def run_once", "def run_forever"],
    ),
    "legacy_command_queue": (
        BACKEND_ROOT / "amodb/apps/platform/saas_legacy_bridge.py",
        ["def install_legacy_command_queue", 'job.status = "QUEUED"', 'job_type="PLATFORM_COMMAND_JOB"', "execute_legacy_command_in_worker"],
    ),
    "atomic_usage": (
        BACKEND_ROOT / "amodb/apps/platform/saas_usage.py",
        ["ON CONFLICT (amo_id, meter_key)", "usage_meters.used_units + EXCLUDED.used_units", "application._queue_api_usage = enqueue_only"],
    ),
    "integration_health": (
        BACKEND_ROOT / "amodb/apps/platform/saas_integration.py",
        ['integration_router = APIRouter(prefix="/saas/integration-health"', "quality_training", "saas_worker_online", "capacity_position"],
    ),
    "control_plane_migration": (
        BACKEND_ROOT / "amodb/alembic/versions/saas_20260722_control_plane_foundation.py",
        ['revision = "saas_20260722_control_plane"', 'down_revision = "quality_20260722_schema_integrity"', '"saas_provider_credentials"', '"saas_jobs"', '"saas_module_prices"'],
    ),
    "messaging_migration": (
        BACKEND_ROOT / "amodb/alembic/versions/saas_20260722_messaging_hardening.py",
        ['revision = "saas_20260722_messaging"', 'down_revision = "saas_20260722_qms_read_idx"', '"portal_notifications"', '"notification_preferences"', '"uq_chat_threads_amo_scope_key"'],
    ),
    "realtime_auth": (
        BACKEND_ROOT / "amodb/apps/realtime/realtime_auth.py",
        ["def validate_connect_token", "hmac.compare_digest", "RealtimeConnectToken.expires_at > now", "User.is_active.is_(True)", "def prune_user_tokens"],
    ),
    "broker_auth": (
        BACKEND_ROOT / "amodb/apps/realtime/broker_auth.py",
        [
            'GATEWAY_SHARED_SUBSCRIPTION = "$share/amo-portal-gateway/amo/+/user/+/outbox"',
            "def validate_production_config",
            "MQTT_BROKER_WS_URL must use wss:// in production",
            "def authenticate_client",
            "def authorize_topic",
            "topic == GATEWAY_SHARED_SUBSCRIPTION",
            'topic == f"{base}/outbox"',
            'topic in {f"{base}/inbox", f"{base}/ack"}',
        ],
    ),
    "broker_router": (
        BACKEND_ROOT / "amodb/apps/realtime/broker_router.py",
        [
            'router = APIRouter(prefix="/realtime/broker"',
            '@router.post("/authenticate"',
            '@router.post("/authorize"',
            "broker_auth.require_broker_webhook_secret",
        ],
    ),
    "secure_messaging": (
        BACKEND_ROOT / "amodb/apps/realtime/secure_messaging.py",
        ["def _reconcile_thread_memberships", "Only current department members may open this channel", "User is not a current member of this group", "mention_user_ids", 'level == "MENTIONS"', "Mentioned users must be current conversation members", "def process_inbound_envelope"],
    ),
    "messaging_gateway": (
        BACKEND_ROOT / "amodb/apps/realtime/gateway.py",
        [
            "broker_auth.validate_production_config",
            "username_pw_set",
            "broker_auth.GATEWAY_SHARED_SUBSCRIPTION",
            "realtime_auth.validate_connect_token",
            "secure_messaging.process_inbound_envelope",
            'model_copy(update={"authToken": None})',
            "with_for_update(skip_locked=True)",
            "REALTIME_PAYLOAD_MAX_BYTES",
        ],
    ),
    "messaging_routes": (
        BACKEND_ROOT / "amodb/apps/realtime/router.py",
        ["router.include_router(broker_router.router)", "secure_messaging as messaging", "realtime_auth.prune_user_tokens", '@router.get("/chat/directory")', '@router.post("/chat/direct/{peer_user_id}"', '@router.post("/chat/departments/{department_id}"', '@router.post("/chat/groups/{group_id}"', '@router.get("/notifications/me")'],
    ),
    "frontend_platform_service": (
        FRONTEND_ROOT / "src/services/platformControl.ts",
        ["export type SaaSJob", "updateSaasProvider:", "updateTenantModules:", "createCheckout:", "fiscalizeInvoice:", "globalThis.setTimeout"],
    ),
    "frontend_messaging": (
        FRONTEND_ROOT / "src/services/messaging.ts",
        ["export type ChatThreadKind", "openDirect:", "openDepartment:", "openGroup:", "markThreadRead:", "unreadCount:", "updatePreferences:"],
    ),
    "frontend_realtime_auth": (
        FRONTEND_ROOT / "src/services/realtime/mqtt.ts",
        ["private sessionToken", "scheduleTokenRefresh", "authToken: this.sessionToken", "delete queued.authToken", "delete decoded.authToken"],
    ),
    "frontend_messaging_hub": (
        FRONTEND_ROOT / "src/components/messaging/MessagingHub.tsx",
        ["People", "Dept.", "Groups", "All alerts", "Email summaries", "messagingApi.markThreadRead"],
    ),
    "frontend_controls": (
        FRONTEND_ROOT / "src/pages/platform/PlatformIntegrationsPage.tsx",
        ["Provider registry", "Integration queue", "Support desk", "Queue AI draft", "Secrets are encrypted on the backend"],
    ),
    "frontend_billing": (
        FRONTEND_ROOT / "src/pages/platform/PlatformBillingPage.tsx",
        ["Module price catalog", "Queue recurring checkout", "Fiscalize OSCU", "Billing queue"],
    ),
    "production_compose": (
        ROOT / "deploy/saas/docker-compose.yml",
        [
            "CORS_ALLOWED_ORIGINS is required in production",
            "MQTT_BROKER_INTERNAL_URL is required",
            "MQTT_BROKER_WS_URL is required",
            "REALTIME_BROKER_WEBHOOK_SECRET is required",
            "REALTIME_GATEWAY_PASSWORD is required",
            "SAAS_WORKER_BATCH_SIZE:-1",
        ],
    ),
    "load_profile": (
        ROOT / "loadtests/k6_saas_control_plane.js",
        ["TENANT_VUS || 1000", "http_req_failed", '"p(95)<800"', "tenant_quality_training_reads", "/quality/calendar"],
    ),
}

FORBIDDEN_CHECKS: dict[str, tuple[Path, list[str]]] = {
    "frontend_browser_secrets": (
        FRONTEND_ROOT / "src/services/platformControl.ts",
        ["localStorage.setItem(\"stripe", "localStorage.setItem(\"openai", "VITE_OPENAI_API_KEY", "VITE_STRIPE_SECRET"],
    ),
    "provider_plaintext_secret_response": (
        BACKEND_ROOT / "amodb/apps/platform/saas_services.py",
        ['"encrypted_secret":', '"secret": provider_secrets', '"api_key": secret'],
    ),
    "gateway_unsigned_dispatch": (
        BACKEND_ROOT / "amodb/apps/realtime/gateway.py",
        ["messaging.process_inbound_envelope(db, envelope)"],
    ),
    "gateway_non_shared_subscription": (
        BACKEND_ROOT / "amodb/apps/realtime/gateway.py",
        ['client.subscribe("amo/+/user/+/outbox"'],
    ),
    "persisted_realtime_token": (
        FRONTEND_ROOT / "src/services/realtime/queue.ts",
        ["authToken"],
    ),
}

EXTRA_COMPILE_TARGETS = [
    BACKEND_ROOT / "amodb/jobs/platform_command_worker.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_control_plane.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_queue_fencing.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_broker_auth.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_messaging_hardening.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_realtime_security_hardening.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_realtime_services.py",
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

    gateway_text = (BACKEND_ROOT / "amodb/apps/realtime/gateway.py").read_text(encoding="utf-8")
    ordering_ok = gateway_text.index("realtime_auth.validate_connect_token") < gateway_text.index("secure_messaging.process_inbound_envelope")
    passed = passed and ordering_ok
    results["gateway_auth_order"] = {"passed": ordering_ok}

    compile_targets = [path for path, _ in REQUIRED_CHECKS.values() if path.suffix == ".py"] + EXTRA_COMPILE_TARGETS
    compile_results = []
    for target in dict.fromkeys(compile_targets):
        try:
            py_compile.compile(str(target), doraise=True)
            compile_results.append({"path": display(target), "passed": True})
        except Exception as exc:
            passed = False
            compile_results.append({"path": display(target), "passed": False, "error": str(exc)})

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    command = package.get("scripts", {}).get("test:platform")
    expected = "vitest run src/services/platformControl.test.ts src/services/messaging.test.ts"
    script_ok = command == expected
    passed = passed and script_ok
    results["frontend_test_script"] = {"passed": script_ok, "command": command}

    print(json.dumps({"passed": passed, "checks": results, "compile": compile_results}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
