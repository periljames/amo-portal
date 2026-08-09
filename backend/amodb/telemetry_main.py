"""Production ASGI entrypoint with fail-open OpenTelemetry instrumentation."""
from amodb.main import app
from amodb.database import read_engine, write_engine
from amodb.observability import configure_telemetry

configure_telemetry(app, service_name="amo-portal-api", engines=(write_engine, read_engine))

__all__ = ["app"]
