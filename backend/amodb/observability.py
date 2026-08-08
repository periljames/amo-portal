from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

logger = logging.getLogger(__name__)
_CONFIGURED = False
_METER = None
_JOB_DURATION = None
_JOB_RESULT = None
_JOB_RETRY = None
_QUEUE_CACHE_LOCK = threading.Lock()
_QUEUE_CACHE: tuple[float, dict] = (0.0, {})

_ALLOWED_JOB_TYPES = {
    "PLATFORM_COMMAND_JOB",
    "STRIPE_WEBHOOK",
    "ETIMS_FISCALIZE_INVOICE",
    "AI_SUPPORT_REPLY",
    "PROVIDER_HEALTH_CHECK",
    "SEND_EMAIL",
    "MOBILE_PUSH",
    "WEBHOOK_DELIVERY",
    "BILLING_RECONCILIATION",
}
_ALLOWED_DB_OPERATIONS = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "CALL", "DDL", "OTHER"}


def _enabled() -> bool:
    return (os.getenv("OTEL_ENABLED") or "false").strip().lower() in {"1", "true", "yes", "on"}


def _signal_endpoint(signal: str) -> str:
    explicit = (os.getenv(f"OTEL_EXPORTER_OTLP_{signal.upper()}_ENDPOINT") or "").strip()
    if explicit:
        return explicit
    base = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith(":4318") or ":4318/" in base:
        return f"{base}/v1/{signal}"
    return base


def _bounded_job_type(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in _ALLOWED_JOB_TYPES else "OTHER"


def _db_operation(statement: object) -> str:
    text = str(statement or "").lstrip()
    if not text:
        return "OTHER"
    token = text.split(None, 1)[0].upper()
    if token in {"CREATE", "ALTER", "DROP", "TRUNCATE"}:
        return "DDL"
    return token if token in _ALLOWED_DB_OPERATIONS else "OTHER"


def _queue_snapshot() -> dict:
    global _QUEUE_CACHE
    ttl = max(5.0, float(os.getenv("OTEL_QUEUE_METRIC_CACHE_SEC", "10") or "10"))
    now_mono = time.monotonic()
    with _QUEUE_CACHE_LOCK:
        if now_mono - _QUEUE_CACHE[0] <= ttl and _QUEUE_CACHE[1]:
            return _QUEUE_CACHE[1]
    result = {"queues": {}, "workers": {}}
    db = None
    try:
        from sqlalchemy import func
        from amodb.database import ReadSessionLocal, close_session_safely
        from amodb.apps.platform import models as platform_models
        from amodb.apps.platform import saas_models

        db = ReadSessionLocal()
        rows = (
            db.query(saas_models.SaaSJob.queue_name, func.count(saas_models.SaaSJob.id), func.min(saas_models.SaaSJob.created_at))
            .filter(saas_models.SaaSJob.status.in_(["QUEUED", "RETRY", "RUNNING"]))
            .group_by(saas_models.SaaSJob.queue_name)
            .limit(50)
            .all()
        )
        now = datetime.now(timezone.utc)
        for queue_name, count, oldest in rows:
            name = str(queue_name or "default")[:64]
            if oldest is not None and oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            result["queues"][name] = {
                "depth": int(count or 0),
                "oldest_age_seconds": max(0.0, (now - oldest).total_seconds()) if oldest else 0.0,
            }
        workers = (
            db.query(platform_models.PlatformWorkerHeartbeat.worker_type, func.max(platform_models.PlatformWorkerHeartbeat.last_seen_at))
            .group_by(platform_models.PlatformWorkerHeartbeat.worker_type)
            .limit(50)
            .all()
        )
        for worker_type, last_seen in workers:
            if last_seen is not None and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            result["workers"][str(worker_type or "generic")[:64]] = max(0.0, (now - last_seen).total_seconds()) if last_seen else -1.0
    except Exception:
        logger.debug("Unable to refresh bounded queue telemetry", exc_info=True)
    finally:
        try:
            if db is not None:
                close_session_safely(db)
        except Exception:
            pass
    with _QUEUE_CACHE_LOCK:
        _QUEUE_CACHE = (now_mono, result)
    return result


def _configure_metrics(*, resource, endpoint: str, engines: tuple[object, ...]):
    global _METER, _JOB_DURATION, _JOB_RESULT, _JOB_RETRY
    if not endpoint:
        logger.warning("No OTLP metrics endpoint configured; trace export can continue without metrics.")
        return None
    try:
        import psutil
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.metrics import Observation
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        timeout = float(os.getenv("OTEL_EXPORT_TIMEOUT_SEC", "2") or "2")
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, timeout=timeout),
            export_interval_millis=max(5000, int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "10000") or "10000")),
            export_timeout_millis=max(500, int(timeout * 1000)),
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(provider)
        meter = provider.get_meter("amo-portal.operations")
        _METER = meter

        process = psutil.Process()
        process.cpu_percent(interval=None)
        meter.create_observable_gauge(
            "amo.process.cpu.percent",
            callbacks=[lambda _options: [Observation(float(process.cpu_percent(interval=None)), {})]],
            unit="%",
            description="Process CPU utilisation.",
        )
        meter.create_observable_gauge(
            "amo.process.memory.rss",
            callbacks=[lambda _options: [Observation(float(process.memory_info().rss), {})]],
            unit="By",
            description="Process resident memory.",
        )
        meter.create_observable_gauge(
            "amo.process.start_time",
            callbacks=[lambda _options: [Observation(float(process.create_time()), {})]],
            unit="s",
            description="Process start time as Unix epoch seconds.",
        )

        unique_engines: list[tuple[str, object]] = []
        seen: set[int] = set()
        for index, engine in enumerate(engines):
            if not engine or id(engine) in seen:
                continue
            seen.add(id(engine))
            unique_engines.append(("write" if index == 0 else "read", engine))

        def pool_observations(metric: str):
            observations = []
            for role, engine in unique_engines:
                pool = getattr(engine, "pool", None)
                function = getattr(pool, metric, None)
                if not callable(function):
                    continue
                try:
                    observations.append(Observation(float(function()), {"db.role": role}))
                except Exception:
                    continue
            return observations

        meter.create_observable_gauge("amo.db.pool.checked_out", callbacks=[lambda _options: pool_observations("checkedout")], unit="{connection}")
        meter.create_observable_gauge("amo.db.pool.idle", callbacks=[lambda _options: pool_observations("checkedin")], unit="{connection}")
        meter.create_observable_gauge("amo.db.pool.size", callbacks=[lambda _options: pool_observations("size")], unit="{connection}")
        meter.create_observable_gauge("amo.db.pool.overflow", callbacks=[lambda _options: pool_observations("overflow")], unit="{connection}")

        def queue_depth(_options):
            return [Observation(float(row["depth"]), {"queue": name}) for name, row in _queue_snapshot().get("queues", {}).items()]

        def queue_age(_options):
            return [Observation(float(row["oldest_age_seconds"]), {"queue": name}) for name, row in _queue_snapshot().get("queues", {}).items()]

        def worker_age(_options):
            return [Observation(float(age), {"worker.type": name}) for name, age in _queue_snapshot().get("workers", {}).items() if age >= 0]

        meter.create_observable_gauge("amo.job.queue_depth", callbacks=[queue_depth], unit="{job}")
        meter.create_observable_gauge("amo.job.queue_oldest_age_seconds", callbacks=[queue_age], unit="s")
        meter.create_observable_gauge("amo.worker.last_seen_age_seconds", callbacks=[worker_age], unit="s")

        _JOB_DURATION = meter.create_histogram("amo.job.duration", unit="s", description="Background job execution duration.")
        _JOB_RESULT = meter.create_counter("amo.job.result", unit="{job}", description="Background job outcomes.")
        _JOB_RETRY = meter.create_counter("amo.job.retry", unit="{retry}", description="Background job retry attempts.")

        try:
            from sqlalchemy import event
            db_histogram = meter.create_histogram("amo.db.query.duration", unit="ms", description="DB statement latency by bounded operation class.")
            for role, engine in unique_engines:
                @event.listens_for(engine, "before_cursor_execute")
                def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany, _role=role):
                    context._amo_otel_started = time.perf_counter()
                    context._amo_otel_operation = _db_operation(statement)
                    context._amo_otel_role = _role

                @event.listens_for(engine, "after_cursor_execute")
                def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                    started = getattr(context, "_amo_otel_started", None)
                    if started is None:
                        return
                    db_histogram.record(
                        (time.perf_counter() - started) * 1000.0,
                        {
                            "db.operation": str(getattr(context, "_amo_otel_operation", "OTHER")),
                            "db.role": str(getattr(context, "_amo_otel_role", "write")),
                        },
                    )
        except Exception:
            logger.exception("OpenTelemetry DB metric listeners failed; continuing without DB query metrics.")
        return provider
    except Exception:
        logger.exception("OpenTelemetry metric configuration failed; continuing without metric export.")
        return None


def configure_telemetry(app, *, service_name: str, engines: tuple[object, ...] = ()) -> bool:
    """Configure fail-open OTLP traces and bounded metrics.

    Export uses background batching/readers. Export failures never participate in
    tenant request success and no unrestricted tenant/user/document identifiers are
    metric attributes.
    """
    global _CONFIGURED
    if not _enabled():
        return False
    if _CONFIGURED:
        return True
    trace_endpoint = _signal_endpoint("traces")
    metrics_endpoint = _signal_endpoint("metrics")
    if not trace_endpoint and not metrics_endpoint:
        logger.warning("OTEL_ENABLED is true but no OTLP endpoint is configured; telemetry remains disabled.")
        return False

    resource = None
    tracer_provider = None
    meter_provider = None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        resource = Resource.create({
            "service.name": service_name,
            "service.namespace": "amo-portal",
            "service.instance.id": (os.getenv("OTEL_SERVICE_INSTANCE_ID") or f"pid-{os.getpid()}")[:128],
            "deployment.environment": (os.getenv("APP_ENV") or os.getenv("ENV") or "development"),
        })
        if trace_endpoint:
            tracer_provider = TracerProvider(resource=resource)
            timeout = float(os.getenv("OTEL_EXPORT_TIMEOUT_SEC", "2") or "2")
            exporter = OTLPSpanExporter(endpoint=trace_endpoint, timeout=timeout)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    exporter,
                    max_queue_size=max(128, int(os.getenv("OTEL_BSP_MAX_QUEUE_SIZE", "512") or "512")),
                    max_export_batch_size=max(32, int(os.getenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "128") or "128")),
                    schedule_delay_millis=max(1000, int(os.getenv("OTEL_BSP_SCHEDULE_DELAY_MS", "5000") or "5000")),
                    export_timeout_millis=max(500, int(timeout * 1000)),
                )
            )
            trace.set_tracer_provider(tracer_provider)
    except Exception:
        logger.exception("OpenTelemetry trace configuration failed; continuing without trace export.")

    if resource is not None:
        meter_provider = _configure_metrics(resource=resource, endpoint=metrics_endpoint, engines=engines)

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            excluded_urls="/health,/healthz,/readyz",
        )
    except Exception:
        logger.exception("FastAPI OpenTelemetry instrumentation failed; application will continue.")

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        seen: set[int] = set()
        for engine in engines:
            if not engine or id(engine) in seen:
                continue
            seen.add(id(engine))
            SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider, meter_provider=meter_provider)
    except Exception:
        logger.exception("SQLAlchemy OpenTelemetry instrumentation failed; database access will continue.")

    _CONFIGURED = bool(tracer_provider or meter_provider)
    return _CONFIGURED


def record_job_execution(*, job_type: object, status: str, duration_seconds: float, retry_count: int = 0) -> None:
    """Record bounded worker metrics; never raise into worker execution."""
    try:
        attrs = {"job.type": _bounded_job_type(job_type), "job.status": str(status or "UNKNOWN").upper()[:32]}
        if _JOB_DURATION is not None:
            _JOB_DURATION.record(max(0.0, float(duration_seconds)), attrs)
        if _JOB_RESULT is not None:
            _JOB_RESULT.add(1, attrs)
        if _JOB_RETRY is not None and retry_count > 0:
            _JOB_RETRY.add(int(retry_count), {"job.type": attrs["job.type"]})
    except Exception:
        logger.debug("Unable to record worker telemetry", exc_info=True)


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
                    # Span attributes are intentionally not metric labels. Callers
                    # must still avoid secrets and sensitive payload contents.
                    span.set_attribute(key, value)
            yield
    except Exception:
        yield
