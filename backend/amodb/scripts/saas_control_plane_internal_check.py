from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"


REQUIRED: dict[Path, tuple[str, ...]] = {
    BACKEND_ROOT / "amodb/apps/platform/saas_models.py": (
        "class SaaSJob",
        "lease_token = Column",
        "uq_saas_job_idempotency",
        "source_job_id = Column",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_queue.py": (
        "NON_REPEATABLE_JOB_TYPES",
        "with_for_update(skip_locked=True)",
        ".limit(1)",
        "def heartbeat_job",
        "models.SaaSJob.lease_token == expected_token",
        "Job lease was lost before completion",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_lease.py": (
        "class LeaseHeartbeat",
        "heartbeat_job",
        "raise_if_lost",
    ),
    BACKEND_ROOT / "amodb/jobs/saas_worker_safe.py": (
        "LeaseHeartbeat",
        "heartbeat.raise_if_lost()",
        "NonRepeatableJobError",
        "complete_job(db, job, result, worker_id=worker_id)",
    ),
    BACKEND_ROOT / "amodb/jobs/platform_command_worker.py": (
        "LeaseHeartbeat",
        "heartbeat.raise_if_lost()",
        "except saas_queue.LeaseLostError",
    ),
    BACKEND_ROOT / "amodb/alembic/versions/saas_20260722_runtime_fencing.py": (
        'revision = "saas_20260722_runtime_fence"',
        'down_revision = "saas_20260722_messaging"',
        "ix_saas_jobs_lease_fence",
    ),
    BACKEND_ROOT / "amodb/alembic/versions/saas_20260722_side_effect_safety.py": (
        'revision = "saas_20260722_side_effect_safe"',
        'down_revision = "saas_20260722_runtime_fence"',
        '"source_job_id"',
        '"timezone_name"',
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_secrets.py": (
        "PLATFORM_SECRETS_KEY",
        "Fernet",
        "def encrypt_secret",
        "def decrypt_secret",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_side_effects.py": (
        "account_services.format_invoice_number(invoice)",
        '"total_amount_cents": int(invoice.amount_cents)',
        "saas_providers.openai_support_response",
        'fiscalization.status = "RECONCILIATION_REQUIRED"',
        "source_job_id=job.id",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_admin_policy.py": (
        "def prepare_provider_payload",
        "allow_platform_fallback=False",
        "merged_secret = {**existing_secret, **submitted}",
        "Tenant-specific secret values are required",
        "An enabled provider cannot clear its stored secret",
        "Enabled provider configuration is missing required secret field(s)",
        "def install_tenant_provider_override_policy",
        "saas_services.upsert_provider_credential = guarded_upsert_provider_credential",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_webhooks.py": (
        "ACTIVE_CREDENTIAL_STATES",
        "def _credential_candidates",
        "models.SaaSBillingAccount.external_customer_ref",
        "if scoped_rows:",
        "A disabled or incomplete scoped row deliberately blocks platform",
        "saas_providers.verify_stripe_signature",
        '"verified_credential_id": matched.id',
        '"verified_tenant_id"',
    ),
    BACKEND_ROOT / "amodb/apps/platform/tenant_saas_router.py": (
        'APIRouter(prefix="/tenant-saas"',
        "def require_saas_admin",
        "Cannot manage SaaS settings for another AMO",
        '@router.get("/setup")',
        '@router.put("/providers/{provider}")',
        '@router.post("/providers/{provider}/health"',
        '@router.get("/jobs")',
        '@router.post("/checkout"',
        '@router.post("/invoices/{invoice_id}/fiscalize"',
        '"managed_in_frontend": False',
    ),
    BACKEND_ROOT / "amodb/apps/platform/__init__.py": (
        "_saas_services.record_stripe_webhook = _saas_webhooks.record_stripe_webhook",
        "install_tenant_provider_override_policy()",
        "router.include_router(tenant_saas_router)",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_usage.py": (
        "ON CONFLICT (amo_id, meter_key)",
        "usage_meters.used_units + EXCLUDED.used_units",
        "def flush_with_requeue",
        "application._api_usage_pending.get(pending_amo_id, 0) + quantity",
        "application._flush_api_usage_metrics = flush_with_requeue",
    ),
    BACKEND_ROOT / "amodb/apps/realtime/broker_auth.py": (
        'GATEWAY_SHARED_SUBSCRIPTION = "$share/amo-portal-gateway/amo/+/user/+/outbox"',
        "MQTT_BROKER_WS_URL must use wss:// in production",
        "def authenticate_client",
        "def authorize_topic",
    ),
    BACKEND_ROOT / "amodb/apps/realtime/secure_messaging.py": (
        "def _reconcile_thread_memberships",
        "Only current department members may open this channel",
        "mention_user_ids",
        'level == "MENTIONS"',
    ),
    BACKEND_ROOT / "amodb/apps/realtime/production_messaging.py": (
        "notification_preferences.allows_chat_notification",
        "get_preferences = notification_preferences.get_preferences",
        "update_preferences = notification_preferences.update_preferences",
    ),
    BACKEND_ROOT / "amodb/apps/realtime/gateway.py": (
        "realtime_auth.validate_connect_token",
        "production_messaging.process_inbound_envelope",
        "result.wait_for_publish(timeout=timeout)",
        "result.is_published()",
        "with_for_update(skip_locked=True)",
        ".limit(1)",
    ),
    BACKEND_ROOT / "amodb/apps/realtime/router.py": (
        "production_messaging as messaging",
        "notification_counts.unread_notification_count",
    ),
    FRONTEND_ROOT / "src/services/realtime/queue.ts": (
        "export const MAX_OUTBOUND_MESSAGES = 500",
        "export function sanitizeOutbound",
        "delete clean.authToken",
        "existing.slice(0, excess)",
    ),
    FRONTEND_ROOT / "src/services/realtime/mqtt.ts": (
        "publishWithAcknowledgement",
        "MQTT publish acknowledgement timed out",
        "await removeOutbound(item.id)",
        "queued MQTT publish retained for retry",
    ),
    FRONTEND_ROOT / "src/services/saasSettings.ts": (
        "/platform/tenant-saas/setup",
        "function tenantParams",
        "if (!user?.is_superuser) return {}",
        "updateProvider:",
        "testProvider:",
        "checkout:",
        "fiscalize:",
    ),
    FRONTEND_ROOT / "src/pages/AdminSaaSSettingsPage.tsx": (
        "Integrations & automation setup",
        "Enter tenant-specific secret values",
        "Save encrypted configuration",
        "Queue backend health check",
        "Durable backend pipeline",
        "Deployment-managed requirements",
        "Copy webhook URL",
        "Global integrations",
        "Global billing",
    ),
    FRONTEND_ROOT / "src/pages/EmailServerSettingsPage.tsx": (
        'export { default } from "./AdminSaaSSettingsPage"',
    ),
    FRONTEND_ROOT / "src/pages/platform/PlatformTenantsPage.tsx": (
        "Open integrations & pipeline",
        "tenant_id=${encodeURIComponent(selected)}",
    ),
    FRONTEND_ROOT / "src/styles/adminSaaSSettings.css": (
        ".saas-admin__provider-layout",
        ".saas-admin__readiness-grid",
        '[data-theme="dark"] .saas-admin',
    ),
    ROOT / "deploy/saas/docker-compose.yml": (
        "working_dir: /app/backend",
        "CORS_ALLOWED_ORIGINS is required in production",
        "MQTT_BROKER_WS_URL is required",
        "REALTIME_BROKER_WEBHOOK_SECRET is required",
        "amodb.jobs.saas_worker_safe",
        "SAAS_WORKER_BATCH_SIZE:-1",
    ),
    ROOT / "loadtests/k6_saas_control_plane.js": (
        "TENANT_VUS || 1000",
        "http_req_failed",
        '"p(95)<800"',
        "/quality/calendar",
    ),
}


FORBIDDEN: dict[Path, tuple[str, ...]] = {
    FRONTEND_ROOT / "src/services/platformControl.ts": (
        "VITE_OPENAI_API_KEY",
        "VITE_STRIPE_SECRET",
    ),
    FRONTEND_ROOT / "src/services/saasSettings.ts": (
        "PLATFORM_SECRETS_KEY",
        "REALTIME_GATEWAY_PASSWORD",
        "encrypted_secret",
    ),
    BACKEND_ROOT / "amodb/apps/realtime/gateway.py": (
        'client.subscribe("amo/+/user/+/outbox"',
        "secure_messaging.process_inbound_envelope",
    ),
    BACKEND_ROOT / "amodb/apps/realtime/router.py": (
        "secure_messaging as messaging",
    ),
    BACKEND_ROOT / "amodb/apps/platform/saas_side_effects.py": (
        "invoice.invoice_number",
        "invoice.subtotal_cents",
        "invoice.tax_cents",
        "invoice.total_cents",
        "generate_openai_support_response",
    ),
    BACKEND_ROOT / "amodb/apps/platform/tenant_saas_router.py": (
        '"value": os.getenv',
        '"secret": saas_services.provider_secrets',
    ),
}


EXTRA_COMPILE = (
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_control_plane.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_queue_fencing.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_side_effect_safety.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_admin_and_webhooks.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_broker_auth.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_messaging_hardening.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_realtime_security_hardening.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_realtime_services.py",
    Path(__file__),
)


def _missing(text: str, values: Iterable[str]) -> list[str]:
    return [value for value in values if value not in text]


def _present(text: str, values: Iterable[str]) -> list[str]:
    return [value for value in values if value in text]


def main() -> int:
    passed = True
    checks: dict[str, object] = {}

    for path, tokens in REQUIRED.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = _missing(text, tokens)
        ok = path.exists() and not missing
        passed = passed and ok
        checks[str(path.relative_to(ROOT))] = {"passed": ok, "missing": missing}

    for path, tokens in FORBIDDEN.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        present = _present(text, tokens)
        ok = path.exists() and not present
        passed = passed and ok
        checks[f"forbidden:{path.relative_to(ROOT)}"] = {"passed": ok, "present": present}

    gateway = (BACKEND_ROOT / "amodb/apps/realtime/gateway.py").read_text(encoding="utf-8")
    auth_order = gateway.index("realtime_auth.validate_connect_token") < gateway.index("production_messaging.process_inbound_envelope")
    ack_order = gateway.index("result.wait_for_publish(timeout=timeout)") < gateway.index("row.published_at = datetime.now(timezone.utc)")
    passed = passed and auth_order and ack_order
    checks["gateway-auth-before-dispatch"] = {"passed": auth_order}
    checks["gateway-puback-before-outbox-clear"] = {"passed": ack_order}

    package_init = (BACKEND_ROOT / "amodb/apps/platform/__init__.py").read_text(encoding="utf-8")
    policy_order = package_init.index("install_tenant_provider_override_policy()") < package_init.index("from .saas_router import")
    passed = passed and policy_order
    checks["tenant-provider-policy-before-route-import"] = {"passed": policy_order}

    compile_rows: list[dict[str, object]] = []
    compile_targets = tuple(REQUIRED) + EXTRA_COMPILE
    for path in dict.fromkeys(path for path in compile_targets if path.suffix == ".py"):
        try:
            py_compile.compile(str(path), doraise=True)
            compile_rows.append({"path": str(path.relative_to(ROOT)), "passed": True})
        except Exception as exc:
            passed = False
            compile_rows.append({"path": str(path.relative_to(ROOT)), "passed": False, "error": str(exc)})

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    expected_script = "vitest run src/services/platformControl.test.ts src/services/saasSettings.test.ts src/services/messaging.test.ts src/services/realtime/reliability.test.ts"
    actual_script = package.get("scripts", {}).get("test:platform")
    script_ok = actual_script == expected_script
    passed = passed and script_ok
    checks["frontend-test-script"] = {"passed": script_ok, "command": actual_script}

    print(json.dumps({"passed": passed, "checks": checks, "compile": compile_rows}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
