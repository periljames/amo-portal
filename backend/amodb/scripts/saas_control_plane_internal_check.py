from __future__ import annotations

import json
import py_compile
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = ROOT / "frontend"

REQUIRED: dict[Path, list[str]] = {
    BACKEND_ROOT / "amodb/apps/platform/saas_models.py": [
        "class SaaSJob",
        "lease_token = Column",
        "ix_saas_jobs_lease_fence",
        "uq_saas_job_idempotency",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_queue.py": [
        "class LeaseLostError",
        "with_for_update(skip_locked=True)",
        ".limit(1)",
        "job.lease_token = secrets.token_urlsafe",
        "models.SaaSJob.lease_token == expected_token",
        "def heartbeat_job",
        "Job lease was lost before completion",
        "Job lease was lost before failure handling",
        "RETRYABLE_MANUAL_STATUSES",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_lease.py": [
        "class LeaseHeartbeat",
        "SimpleNamespace",
        "heartbeat_job",
        "raise_if_lost",
    ],
    BACKEND_ROOT / "amodb/jobs/saas_worker_safe.py": [
        "LeaseHeartbeat",
        "heartbeat.raise_if_lost()",
        "complete_job(db, job, result, worker_id=worker_id)",
        "except saas_queue.LeaseLostError",
    ],
    BACKEND_ROOT / "amodb/jobs/platform_command_worker.py": [
        "LeaseHeartbeat",
        "heartbeat.raise_if_lost()",
        "worker_id=current_worker",
        "except saas_queue.LeaseLostError",
    ],
    BACKEND_ROOT / "amodb/alembic/versions/saas_20260722_runtime_fencing.py": [
        'revision = "saas_20260722_runtime_fence"',
        'down_revision = "saas_20260722_messaging"',
        '"lease_token"',
        "ix_saas_jobs_lease_fence",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_secrets.py": [
        "PLATFORM_SECRETS_KEY",
        "Fernet",
        "def encrypt_secret",
        "def decrypt_secret",
        "def redact_mapping",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_providers.py": [
        'ProviderDefinition("stripe"',
        'ProviderDefinition("mpesa_daraja"',
        'ProviderDefinition("etims_oscu"',
        'ProviderDefinition("openai"',
        "def verify_stripe_signature",
        "def fiscalize_etims_invoice",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_router.py": [
        '@platform_saas_router.get("/providers")',
        '@platform_saas_router.get("/jobs")',
        '@webhook_router.post("/stripe"',
        '@support_router.post("/tickets"',
        "def _visible_support_payload",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_usage.py": [
        "ON CONFLICT (amo_id, meter_key)",
        "usage_meters.used_units + EXCLUDED.used_units",
        "application._queue_api_usage = enqueue_only",
    ],
    BACKEND_ROOT / "amodb/apps/realtime/realtime_auth.py": [
        "def validate_connect_token",
        "hmac.compare_digest",
        "RealtimeConnectToken.expires_at > now",
        "User.is_active.is_(True)",
    ],
    BACKEND_ROOT / "amodb/apps/realtime/broker_auth.py": [
        'GATEWAY_SHARED_SUBSCRIPTION = "$share/amo-portal-gateway/amo/+/user/+/outbox"',
        "def validate_production_config",
        "MQTT_BROKER_WS_URL must use wss:// in production",
        "def authenticate_client",
        "def authorize_topic",
        'topic == f"{base}/outbox"',
        'topic in {f"{base}/inbox", f"{base}/ack"}',
    ],
    BACKEND_ROOT / "amodb/apps/realtime/broker_router.py": [
        '@router.post("/authenticate"',
        '@router.post("/authorize"',
        "require_broker_webhook_secret",
    ],
    BACKEND_ROOT / "amodb/apps/realtime/secure_messaging.py": [
        "def _reconcile_thread_memberships",
        "Only current department members may open this channel",
        "User is not a current member of this group",
        "mention_user_ids",
        'level == "MENTIONS"',
        "Mentioned users must be current conversation members",
    ],
    BACKEND_ROOT / "amodb/apps/realtime/notification_counts.py": [
        'PortalNotification.kind != "CHAT_MESSAGE"',
        "MessageReceipt.read_at.is_(None)",
        '"total": int(notifications) + int(messages)',
    ],
    BACKEND_ROOT / "amodb/apps/realtime/gateway.py": [
        "broker_auth.validate_production_config",
        "username_pw_set",
        "broker_auth.GATEWAY_SHARED_SUBSCRIPTION",
        "realtime_auth.validate_connect_token",
        "secure_messaging.process_inbound_envelope",
        'model_copy(update={"authToken": None})',
        "with_for_update(skip_locked=True)",
    ],
    BACKEND_ROOT / "amodb/apps/realtime/router.py": [
        "router.include_router(broker_router.router)",
        "secure_messaging as messaging",
        "notification_counts.unread_notification_count",
        "realtime_auth.prune_user_tokens",
    ],
    FRONTEND_ROOT / "src/services/realtime/mqtt.ts": [
        "private sessionToken",
        "scheduleTokenRefresh",
        "publishWithAcknowledgement",
        "MQTT publish acknowledgement timed out",
        "authToken: token",
        "await removeOutbound(item.id)",
        "queued MQTT publish retained for retry",
        "delete queued.authToken",
        "delete decoded.authToken",
    ],
    FRONTEND_ROOT / "src/services/realtime/queue.ts": [
        "MAX_OUTBOUND_MESSAGES = 500",
        "def", 
    ],
    FRONTEND_ROOT / "src/services/messaging.ts": [
        "mentionUserIds: string[] = []",
        "mention_user_ids",
        "openDirect:",
        "openDepartment:",
        "openGroup:",
        "markThreadRead:",
        "updatePreferences:",
    ],
    FRONTEND_ROOT / "src/components/messaging/MessagingHub.tsx": [
        "mentionUserIds",
        "Mentioned you",
        "@ Mention",
        'notification.kind !== "CHAT_MESSAGE"',
    ],
    FRONTEND_ROOT / "src/styles/components/messaging.css": [
        ".messaging-mentions",
        ".messaging-composer-row",
        ".messaging-mentioned",
    ],
    ROOT / "deploy/saas/docker-compose.yml": [
        "CORS_ALLOWED_ORIGINS is required in production",
        "MQTT_BROKER_WS_URL is required",
        "REALTIME_BROKER_WEBHOOK_SECRET is required",
        "amodb.jobs.saas_worker_safe",
        "SAAS_WORKER_BATCH_SIZE:-1",
    ],
    ROOT / "loadtests/k6_saas_control_plane.js": [
        "TENANT_VUS || 1000",
        "http_req_failed",
        '"p(95)<800"',
        "/quality/calendar",
    ],
}

FORBIDDEN: dict[Path, list[str]] = {
    FRONTEND_ROOT / "src/services/platformControl.ts": [
        "VITE_OPENAI_API_KEY",
        "VITE_STRIPE_SECRET",
    ],
    BACKEND_ROOT / "amodb/apps/realtime/gateway.py": [
        'client.subscribe("amo/+/user/+/outbox"',
        "messaging.process_inbound_envelope(db, envelope)",
    ],
    BACKEND_ROOT / "amodb/apps/platform/saas_services.py": [
        '"encrypted_secret":',
        '"secret": provider_secrets',
    ],
}

EXTRA_COMPILE = [
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_control_plane.py",
    BACKEND_ROOT / "amodb/apps/platform/tests/test_saas_queue_fencing.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_broker_auth.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_messaging_hardening.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_realtime_security_hardening.py",
    BACKEND_ROOT / "amodb/apps/realtime/tests/test_realtime_services.py",
    Path(__file__),
]


def _missing(text: str, values: Iterable[str]) -> list[str]:
    return [value for value in values if value not in text]


def _present(text: str, values: Iterable[str]) -> list[str]:
    return [value for value in values if value in text]


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT.parent))
    except ValueError:
        return str(path)


def main() -> int:
    passed = True
    checks: dict[str, object] = {}
    for path, tokens in REQUIRED.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        absent = _missing(text, tokens)
        ok = path.exists() and not absent
        passed = passed and ok
        checks[_display(path)] = {"passed": ok, "missing": absent}

    # Queue contract is checked structurally here instead of forbidding the word
    # authToken, because sanitization must explicitly delete that field.
    queue_text = (FRONTEND_ROOT / "src/services/realtime/queue.ts").read_text(encoding="utf-8")
    queue_ok = all(token in queue_text for token in (
        "export function sanitizeOutbound",
        "delete clean.authToken",
        "store.put(clean)",
        "existing.slice(0, excess)",
        "db.close()",
    )) and "store.put(envelope)" not in queue_text
    passed = passed and queue_ok
    checks["realtime-outbound-sanitized-and-bounded"] = {"passed": queue_ok}

    for path, tokens in FORBIDDEN.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        found = _present(text, tokens)
        ok = path.exists() and not found
        passed = passed and ok
        checks[f"forbidden:{_display(path)}"] = {"passed": ok, "present": found}

    gateway = (BACKEND_ROOT / "amodb/apps/realtime/gateway.py").read_text(encoding="utf-8")
    auth_order = gateway.index("realtime_auth.validate_connect_token") < gateway.index("secure_messaging.process_inbound_envelope")
    passed = passed and auth_order
    checks["gateway-auth-before-dispatch"] = {"passed": auth_order}

    compile_rows = []
    compile_targets = list(REQUIRED) + EXTRA_COMPILE
    for path in dict.fromkeys(path for path in compile_targets if path.suffix == ".py"):
        try:
            py_compile.compile(str(path), doraise=True)
            compile_rows.append({"path": _display(path), "passed": True})
        except Exception as exc:
            passed = False
            compile_rows.append({"path": _display(path), "passed": False, "error": str(exc)})

    package = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    expected_script = "vitest run src/services/platformControl.test.ts src/services/messaging.test.ts src/services/realtime/reliability.test.ts"
    actual_script = package.get("scripts", {}).get("test:platform")
    script_ok = actual_script == expected_script
    passed = passed and script_ok
    checks["frontend-test-script"] = {"passed": script_ok, "command": actual_script}

    print(json.dumps({"passed": passed, "checks": checks, "compile": compile_rows}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
