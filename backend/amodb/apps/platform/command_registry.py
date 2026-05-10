from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PlatformCommandDefinition:
    command_name: str
    description: str
    risk_level: str
    requires_tenant_id: bool
    requires_reason: bool
    requires_approval: bool
    supports_dry_run: bool
    timeout_seconds: int
    max_retries: int
    safe_to_retry: bool
    rollback_supported: bool
    output_redaction_rules: list[str]


_COMMANDS = [
    PlatformCommandDefinition("TENANT_RECHECK_ENTITLEMENT", "Recalculate billing access and entitlement state for a tenant.", "LOW", True, True, False, True, 10, 1, True, False, []),
    PlatformCommandDefinition("TENANT_REFRESH_ACCESS_STATUS", "Refresh the tenant access status cache and billing gate output.", "LOW", True, True, False, True, 10, 1, True, False, []),
    PlatformCommandDefinition("TENANT_UNLOCK_TEMPORARILY", "Clear read-only state for a tenant after manual verification.", "HIGH", True, True, True, True, 10, 0, False, True, []),
    PlatformCommandDefinition("TENANT_SET_READ_ONLY", "Set or clear tenant read-only state.", "HIGH", True, True, True, True, 10, 0, False, True, []),
    PlatformCommandDefinition("TENANT_REACTIVATE", "Reactivate a suspended or inactive tenant.", "MEDIUM", True, True, False, True, 10, 0, False, True, []),
    PlatformCommandDefinition("TENANT_DEACTIVATE", "Deactivate a tenant without deleting data.", "HIGH", True, True, True, True, 10, 0, False, True, []),
    PlatformCommandDefinition("TENANT_REBUILD_MODULE_SUMMARY", "Rebuild module summary snapshots for one tenant.", "LOW", True, True, False, True, 20, 1, True, False, []),
    PlatformCommandDefinition("RUN_PLATFORM_HEALTH_PROBE", "Run a bounded health probe and create a health snapshot.", "LOW", False, False, False, True, 20, 1, True, False, ["smtp_secret", "password"]),
    PlatformCommandDefinition("RUN_NETWORK_DIAGNOSTIC", "Run bounded internet, SMTP TCP and storage checks.", "LOW", False, False, False, True, 20, 1, True, False, ["smtp_secret", "password"]),
    PlatformCommandDefinition("RUN_THROUGHPUT_PROBE", "Flush and summarize route throughput metrics.", "LOW", False, False, False, True, 20, 1, True, False, []),
    PlatformCommandDefinition("SEND_TEST_EMAIL", "Send or validate a bounded test email through configured SMTP.", "MEDIUM", False, True, False, True, 20, 0, False, False, ["smtp_password", "smtp_secret"]),
    PlatformCommandDefinition("RETRY_FAILED_WEBHOOKS", "Retry failed webhook deliveries where safe.", "MEDIUM", False, True, False, True, 30, 1, True, False, ["secret"]),
    PlatformCommandDefinition("ROTATE_TENANT_API_KEY", "Rotate a tenant API key where key model exists.", "HIGH", True, True, True, True, 15, 0, False, False, ["raw_key", "key_hash"]),
    PlatformCommandDefinition("CLEAR_TENANT_CACHE", "Clear a tenant cache if a cache layer exists.", "LOW", True, True, False, True, 10, 0, True, False, []),
    PlatformCommandDefinition("INFRA_RESET_GLOBAL_API_TOKENS", "Create a critical job to reset global platform API tokens.", "CRITICAL", False, True, True, True, 30, 0, False, False, ["raw_key", "token"]),
    PlatformCommandDefinition("INFRA_FAILOVER_DATABASE", "Request database failover. Returns unsupported unless real failover is configured.", "CRITICAL", False, True, True, True, 30, 0, False, False, ["password", "dsn", "secret"]),
]

COMMANDS = {cmd.command_name: cmd for cmd in _COMMANDS}


def catalog() -> list[dict]:
    return [asdict(cmd) for cmd in _COMMANDS]


def get_definition(command_name: str) -> PlatformCommandDefinition | None:
    return COMMANDS.get((command_name or "").strip().upper())
