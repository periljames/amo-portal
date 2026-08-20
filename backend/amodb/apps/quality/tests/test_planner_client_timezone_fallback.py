from datetime import timezone

from starlette.requests import Request

from amodb.apps.quality.planner_calendar_enrichment_router import _client_timezone_fallback
from amodb.apps.quality.tenant_timezone import TenantTimezone


def _request(timezone_name: str | None = None) -> Request:
    headers = []
    if timezone_name:
        headers.append((b"x-amo-client-timezone", timezone_name.encode("ascii")))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_client_timezone_is_used_only_when_tenant_timezone_is_missing():
    configured = TenantTimezone(
        name="UTC",
        tzinfo=timezone.utc,
        warning="Tenant timezone is not configured; UTC is being used.",
    )

    resolved, source = _client_timezone_fallback(_request("Africa/Nairobi"), configured)

    assert source == "client"
    assert resolved.name == "Africa/Nairobi"
    assert resolved.warning is None


def test_configured_tenant_timezone_remains_authoritative():
    configured = TenantTimezone(name="Europe/London", tzinfo=timezone.utc)

    resolved, source = _client_timezone_fallback(_request("Africa/Nairobi"), configured)

    assert source == "tenant"
    assert resolved is configured


def test_invalid_client_timezone_does_not_replace_safe_utc_fallback():
    configured = TenantTimezone(
        name="UTC",
        tzinfo=timezone.utc,
        warning="Tenant timezone is not configured; UTC is being used.",
    )

    resolved, source = _client_timezone_fallback(_request("Definitely/Not-A-Timezone"), configured)

    assert source == "utc_fallback"
    assert resolved is configured
