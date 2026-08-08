from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)
_CONFIGURED = False


def _enabled() -> bool:
    return (os.getenv("OTEL_ENABLED") or "false").strip().lower() in {"1", "true", "yes", "on"}


def configure_telemetry(app, *, service_name: str, engines: tuple[object, ...] = ()) -> bool:
    """Configure fail-open OpenTelemetry export.

    Telemetry is intentionally opt-in. Import/config/export failures are logged and
    never prevent the tenant API or the platform operations gateway from starting.
    """
    global _CONFIGURED
    if not _enabled():
        return False
    if _CONFIGURED:
        return True
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        logger.warning("OTEL_ENABLED is true but no OTLP endpoint is configured; telemetry remains disabled.")
        return False
    if endpoint.rstrip("/").endswith(":4318"):
        endpoint = endpoint.rstrip("/") + "/v1/traces"
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({
            "service.name": service_name,
            "deployment.environment": (os.getenv("APP_ENV") or os.getenv("ENV") or "development"),
            "service.namespace": "amo-portal",
        }))
        exporter = OTLPSpanExporter(endpoint=endpoint, timeout=float(os.getenv("OTEL_EXPORT_TIMEOUT_SEC", "2") or "2"))
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=int(os.getenv("OTEL_BSP_MAX_QUEUE_SIZE", "512") or "512"),
                max_export_batch_size=int(os.getenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "128") or "128"),
                schedule_delay_millis=int(os.getenv("OTEL_BSP_SCHEDULE_DELAY_MS", "5000") or "5000"),
                export_timeout_millis=int(float(os.getenv("OTEL_EXPORT_TIMEOUT_SEC", "2") or "2") * 1000),
            )
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="/health,/healthz")
        seen: set[int] = set()
        for engine in engines:
            if not engine or id(engine) in seen:
                continue
            seen.add(id(engine))
            SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
        _CONFIGURED = True
        return True
    except Exception:
        logger.exception("OpenTelemetry configuration failed; continuing without telemetry export.")
        return False


@contextmanager
def operation_span(name: str, **attributes: object) -> Iterator[None]:
    if not _enabled():
        yield
        return
    try:
        from opentelemetry import trace
        with trace.get_tracer("amo-portal.operations").start_as_current_span(name) as span:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
            yield
    except Exception:
        yield
