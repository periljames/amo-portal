from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from amodb import observability

_ALLOWED_JOB_STATUS = {"SUCCEEDED", "FAILED", "BLOCKED", "LEASE_LOST", "RETRY", "CANCELLED", "UNSUPPORTED", "OTHER"}


def _bounded_status(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in _ALLOWED_JOB_STATUS else "OTHER"


def _span_attributes(attributes: dict[str, object]) -> dict[str, str | int | float | bool]:
    safe: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        name = str(key).strip()[:64]
        if not name:
            continue
        if isinstance(value, bool):
            safe[name] = value
        elif isinstance(value, (int, float)):
            safe[name] = value
        else:
            safe[name] = str(value)[:128]
    return safe


@contextmanager
def operation_span(name: str, **attributes: object) -> Iterator[object | None]:
    """Create a fail-open bounded span around an internal operation.

    This helper never makes business execution depend on OpenTelemetry. Callers
    pass operation classes and queue/provider names only; tenant/user/business
    identifiers are deliberately excluded from metric dimensions.
    """

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("amo-portal.operations")
        with tracer.start_as_current_span(str(name)[:128], attributes=_span_attributes(attributes)) as span:
            yield span
        return
    except Exception:
        # Telemetry must not participate in application availability.
        yield None


def record_job_execution(*, job_type: object, status: object, duration_seconds: float, retry_count: int = 0) -> None:
    job = observability._bounded_job_type(job_type)
    outcome = _bounded_status(status)
    attributes = {"job.type": job, "outcome": outcome}
    try:
        if observability._JOB_DURATION is not None:
            observability._JOB_DURATION.record(max(0.0, float(duration_seconds)), attributes)
        if observability._JOB_RESULT is not None:
            observability._JOB_RESULT.add(1, attributes)
        if observability._JOB_RETRY is not None and retry_count > 0:
            observability._JOB_RETRY.add(max(0, int(retry_count)), {"job.type": job})
    except Exception:
        return


def record_provider_execution(
    *,
    provider: object,
    operation: object,
    outcome: object,
    duration_seconds: float,
) -> None:
    provider_name = observability._bounded_provider(provider)
    operation_name = observability._bounded_provider_operation(operation)
    result = "SUCCESS" if str(outcome or "").strip().upper() in {"SUCCESS", "SUCCEEDED", "OK"} else "ERROR"
    attributes = {
        "provider": provider_name,
        "operation": operation_name,
        "outcome": result,
    }
    try:
        if observability._PROVIDER_DURATION is not None:
            observability._PROVIDER_DURATION.record(max(0.0, float(duration_seconds)), attributes)
        if observability._PROVIDER_RESULT is not None:
            observability._PROVIDER_RESULT.add(1, attributes)
    except Exception:
        return


@contextmanager
def provider_operation(provider: object, operation: object) -> Iterator[object | None]:
    """Trace and measure one bounded external-provider call."""

    provider_name = observability._bounded_provider(provider)
    operation_name = observability._bounded_provider_operation(operation)
    started = time.perf_counter()
    outcome = "ERROR"
    try:
        with operation_span(
            "provider.operation",
            provider=provider_name,
            operation=operation_name,
        ) as span:
            yield span
        outcome = "SUCCESS"
    finally:
        record_provider_execution(
            provider=provider_name,
            operation=operation_name,
            outcome=outcome,
            duration_seconds=time.perf_counter() - started,
        )
