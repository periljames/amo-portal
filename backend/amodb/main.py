# backend/amodb/main.py
import os
import time
import logging
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Lock
from typing import Callable, Dict, List

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from jose import JWTError, jwt
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as SQLAlchemyTimeoutError

from .database import (
    Base,
    engine,
    WriteSessionLocal,
    close_session_safely,
    dispose_engines,
    probe_database,
)
from .database_resilience import database_circuit
from .db_capacity import connection_budget, validate_connection_budget
from .query_metrics import begin_counting, end_counting, query_count
from .security import JWT_ALGORITHM, SECRET_KEY
from .apps.accounts import models as accounts_models

from .apps.accounts.router_public import router as accounts_public_router
from .apps.accounts.router_admin import router as accounts_admin_router
from .apps.accounts.router_modules_admin import router as accounts_modules_router
from .apps.accounts.router_amo_assets import router as accounts_amo_assets_router
from .apps.accounts.router_onboarding import router as accounts_onboarding_router
from .apps.fleet.router import router as fleet_router
from .apps.aircraft_architecture.router import router as aircraft_architecture_router
from .apps.work.router import router as work_router
from .apps.crs.router import router as crs_router
from .apps.training.router import router as training_router, public_router as training_public_router
from .apps.quality import router as quality_router, public_router as quality_public_router
from .apps.reliability.router import router as reliability_router
from .apps.reliability import advanced_scheduler as reliability_scheduler
from .apps.inventory.router import router as inventory_router
from .apps.finance.router import router as finance_router
from .apps.audit.router import router as audit_router
from .apps.audit.router_events import router as audit_events_router
from .apps.notifications.router import router as notifications_router
from .apps.tasks.router import router as tasks_router
from .apps.accounts.router_billing import router as billing_router
from .apps.bootstrap.router import router as bootstrap_router
from .apps.integrations.router import router as integrations_router
from .apps.events.router import router as events_router
from .apps.realtime.router import router as realtime_router
from .apps.realtime.gateway import gateway as realtime_gateway
from .apps.accounts import services as account_services
from .apps.manuals.router import router as manuals_router
from .apps.manuals.router_branding import router as manuals_branding_router
from .apps.aerodoc_router import router as aerodoc_router
from .apps.doc_control.router import router as doc_control_router
from .apps.technical_records.router import router as technical_records_router
from .apps.quality.canonical_router import router as canonical_quality_router
from .apps.quality.planner_schedule_router import (
    start_quality_planner_scheduler,
    stop_quality_planner_scheduler,
)
from .apps.platform.router import router as platform_router
from .apps.platform import metrics as platform_metrics
from .apps.foundations.router import router as foundations_router
from .apps.rostering.router import router as rostering_router
from .apps.resilience.router import router as resilience_router
from .apps.resilience import models as resilience_models  # noqa: F401 - register ORM tables
from .jobs.portal_job_supervisor import (
    portal_job_supervisor_status,
    start_portal_job_supervisor,
    stop_portal_job_supervisor,
)


logger = logging.getLogger(__name__)


def _allowed_origins() -> List[str]:
    """
    Parse CORS_ALLOWED_ORIGINS from env.

    Accepts comma-separated origins. If unset, defaults to local dev ports.
    """
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if origins:
            return origins
    return [
        "https://127.0.0.1:5173",
        "https://localhost:5173",
        "https://localhost:4173",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://localhost:4173",
        "http://100.117.215.109:5173",
        "https://100.117.215.109:5173",
    ]


app = FastAPI(title="AMO Portal API", version="1.0.0")
app.state.is_shutting_down = False
cors_origins = _allowed_origins()
cors_origin_regex = (os.getenv("CORS_ALLOWED_ORIGIN_REGEX") or "").strip()
if not cors_origin_regex:
    cors_origin_regex = (
        r"https?://("
        r".*\.ts\.net"
        r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r")(?::\d+)?"
    )
allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in (
    "1",
    "true",
    "yes",
)
default_gzip_minimum_size = int(os.getenv("GZIP_MINIMUM_SIZE", "1024"))
default_gzip_compresslevel = int(os.getenv("GZIP_COMPRESSLEVEL", "6"))
max_request_body_bytes = int(os.getenv("MAX_REQUEST_BODY_BYTES", "0") or "0")
platform_settings_cache_ttl = int(
    os.getenv("PLATFORM_SETTINGS_CACHE_TTL_SEC", "30") or "30"
)
_platform_settings_cache: dict[str, object] = {"at": 0.0, "data": None}

_api_usage_lock = Lock()
_api_usage_pending: Dict[str, int] = {}
_api_usage_last_flush = 0.0
_api_usage_flush_interval_sec = float(os.getenv("API_USAGE_FLUSH_INTERVAL_SEC", "5") or "5")
_api_usage_flush_batch_size = int(os.getenv("API_USAGE_FLUSH_BATCH_SIZE", "100") or "100")


def _queue_api_usage(amo_id: str) -> None:
    global _api_usage_last_flush
    if not amo_id:
        return

    payload_to_flush: Dict[str, int] | None = None
    now = time.monotonic()
    with _api_usage_lock:
        _api_usage_pending[amo_id] = _api_usage_pending.get(amo_id, 0) + 1
        total_pending = sum(_api_usage_pending.values())
        due_by_time = (now - _api_usage_last_flush) >= _api_usage_flush_interval_sec
        due_by_size = total_pending >= _api_usage_flush_batch_size
        if not due_by_time and not due_by_size:
            return
        payload_to_flush = dict(_api_usage_pending)
        _api_usage_pending.clear()
        _api_usage_last_flush = now

    if not payload_to_flush:
        return

    db = WriteSessionLocal()
    try:
        for pending_amo_id, quantity in payload_to_flush.items():
            if quantity <= 0:
                continue
            account_services.record_usage(
                db,
                amo_id=pending_amo_id,
                meter_key=account_services.METER_KEY_API_CALLS,
                quantity=quantity,
            )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        with _api_usage_lock:
            for pending_amo_id, quantity in payload_to_flush.items():
                _api_usage_pending[pending_amo_id] = _api_usage_pending.get(pending_amo_id, 0) + quantity
    finally:
        close_session_safely(db)


def _flush_api_usage_metrics() -> None:
    global _api_usage_last_flush
    with _api_usage_lock:
        if not _api_usage_pending:
            return
        payload_to_flush = dict(_api_usage_pending)
        _api_usage_pending.clear()
        _api_usage_last_flush = time.monotonic()

    db = WriteSessionLocal()
    try:
        for pending_amo_id, quantity in payload_to_flush.items():
            if quantity <= 0:
                continue
            account_services.record_usage(
                db,
                amo_id=pending_amo_id,
                meter_key=account_services.METER_KEY_API_CALLS,
                quantity=quantity,
            )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        close_session_safely(db)


def _load_platform_performance_settings() -> None:
    global default_gzip_minimum_size
    global default_gzip_compresslevel
    global max_request_body_bytes
    db = WriteSessionLocal()
    try:
        settings = db.query(accounts_models.PlatformSettings).first()
        if not settings:
            return
        _platform_settings_cache["data"] = settings
        _platform_settings_cache["at"] = time.monotonic()
        if settings.gzip_minimum_size is not None:
            default_gzip_minimum_size = int(settings.gzip_minimum_size)
        if settings.gzip_compresslevel is not None:
            default_gzip_compresslevel = int(settings.gzip_compresslevel)
        if max_request_body_bytes <= 0 and settings.max_request_body_bytes is not None:
            max_request_body_bytes = int(settings.max_request_body_bytes)
    except Exception:
        return
    finally:
        close_session_safely(db)


def _get_platform_settings_cached() -> accounts_models.PlatformSettings | None:
    if platform_settings_cache_ttl <= 0:
        return _platform_settings_cache.get("data")  # type: ignore[return-value]
    now = time.monotonic()
    cached_at = float(_platform_settings_cache.get("at") or 0.0)
    cached_data = _platform_settings_cache.get("data")
    if cached_data and now - cached_at <= platform_settings_cache_ttl:
        return cached_data  # type: ignore[return-value]
    if not database_circuit.allow_request():
        # Request-size enforcement must not bypass the global circuit and open
        # a fresh PostgreSQL connection for every request during an outage.
        return cached_data  # type: ignore[return-value]
    db = WriteSessionLocal()
    try:
        cached_data = db.query(accounts_models.PlatformSettings).first()
    except Exception:
        cached_data = None
    finally:
        close_session_safely(db)
    _platform_settings_cache["data"] = cached_data
    _platform_settings_cache["at"] = now
    return cached_data  # type: ignore[return-value]


_load_platform_performance_settings()


def _enforce_schema_head_sync_if_configured() -> None:
    if os.getenv("SCHEMA_STRICT", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    script = ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parent / "alembic.ini")))
    repo_heads = set(script.get_heads())

    db = WriteSessionLocal()
    try:
        rows = db.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    finally:
        close_session_safely(db)

    db_versions = {str(row[0]) for row in rows}
    if db_versions != repo_heads:
        logger.error(
            "Schema strict mode failed: database alembic versions %s do not match repository heads %s. "
            "Run 'alembic -c backend/amodb/alembic.ini upgrade heads' before starting the API.",
            sorted(db_versions),
            sorted(repo_heads),
        )
        raise RuntimeError("Database schema is not at repository Alembic head(s).")


@app.on_event("startup")
def _schema_preflight() -> None:
    app.state.is_shutting_down = False
    app.state.connection_budget = validate_connection_budget().payload()
    _enforce_schema_head_sync_if_configured()
    realtime_gateway.connect()
    if os.getenv("PORTAL_EMBEDDED_SCHEDULED_WORKER", "false").lower() in {"1", "true", "yes", "on"}:
        reliability_scheduler.start_reliability_scheduler()
        start_quality_planner_scheduler()
    start_portal_job_supervisor()


def _run_shutdown_step(name: str, fn: Callable[[], None], timeout_seconds: float) -> None:
    """Run a blocking shutdown function with a bounded wait.

    The previous implementation used a ThreadPoolExecutor context manager. That
    still waited for the worker during __exit__, so a hung MQTT/database call made
    Ctrl+C appear stuck even after the timeout fired. This version intentionally
    shuts the pool down with wait=False after the bounded wait.
    """
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"shutdown-{name}")
    future = pool.submit(fn)
    try:
        future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        logger.warning("Shutdown step '%s' exceeded %.1fs and was detached.", name, timeout_seconds)
        future.cancel()
    except Exception:
        logger.debug("Shutdown step '%s' failed", name, exc_info=True)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


@app.on_event("shutdown")
def _flush_usage_metrics_on_shutdown() -> None:
    app.state.is_shutting_down = True
    timeout_seconds = float(os.getenv("AMODB_SHUTDOWN_STEP_TIMEOUT_SEC", "3") or "3")

    _run_shutdown_step("portal-job-supervisor", stop_portal_job_supervisor, timeout_seconds)
    _run_shutdown_step("quality-planner-scheduler", stop_quality_planner_scheduler, timeout_seconds)
    _run_shutdown_step("reliability-scheduler", reliability_scheduler.stop_reliability_scheduler, timeout_seconds)
    _run_shutdown_step("realtime-disconnect", realtime_gateway.disconnect, timeout_seconds)

    if os.getenv("API_USAGE_FLUSH_ON_SHUTDOWN", "false").lower() in {"1", "true", "yes", "on"}:
        _run_shutdown_step("api-usage-flush", _flush_api_usage_metrics, timeout_seconds)

    _run_shutdown_step("sqlalchemy-dispose", dispose_engines, timeout_seconds)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    GZipMiddleware,
    minimum_size=default_gzip_minimum_size,
    compresslevel=default_gzip_compresslevel,
)


def _normalise_route_for_metrics(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return str(path)
    return request.url.path


def _tenant_from_token_for_metrics(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization") or ""
    if " " not in auth_header:
        return None
    scheme, token = auth_header.split(" ", 1)
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        amo_id = payload.get("amo_id")
        return str(amo_id) if amo_id else None
    except Exception:
        return None


def _pool_timeout_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database connection pool is temporarily exhausted. The request was isolated instead of taking down the portal.",
            "error_code": "DB_POOL_TIMEOUT",
            "retryable": True,
            "request_accepted": False,
        },
        headers={"Retry-After": "5", "X-Portal-Readiness": "degraded"},
    )


def _database_unavailable_response() -> JSONResponse:
    retry_after = database_circuit.retry_after_seconds()
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database is temporarily unavailable. The request is safe to retry.",
            "error_code": "DB_TEMPORARILY_UNAVAILABLE",
            "retryable": True,
            "request_accepted": False,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-Portal-Readiness": "offline",
        },
    )


_CIRCUIT_BYPASS_PATHS = frozenset({"/", "/health", "/healthz", "/livez", "/readyz", "/time"})

@app.middleware("http")
async def meter_api_calls(request: Request, call_next):
    query_token = begin_counting()
    started = time.perf_counter()
    status_code = 500
    timeout_error = False
    tenant_id = _tenant_from_token_for_metrics(request)
    try:
        if request.url.path not in _CIRCUIT_BYPASS_PATHS and not database_circuit.allow_request():
            response = _database_unavailable_response()
        else:
            response = await call_next(request)
        status_code = getattr(response, "status_code", 200)
    except asyncio.CancelledError:
        response = Response(status_code=499)
        status_code = 499
    except SQLAlchemyTimeoutError:
        timeout_error = True
        status_code = 503
        response = _pool_timeout_response()
    except OperationalError as exc:
        timeout_error = True
        status_code = 503
        if database_circuit.mark_failure(exc):
            logger.warning("Database circuit opened; API requests will fail fast until readiness recovers")
        response = _database_unavailable_response()
    except DBAPIError as exc:
        # Constraint and validation failures are application errors. Only an
        # invalidated connection represents dependency loss and may be retried.
        if not bool(getattr(exc, "connection_invalidated", False)):
            raise
        timeout_error = True
        status_code = 503
        if database_circuit.mark_failure(exc):
            logger.warning("Database circuit opened after an invalidated connection")
        response = _database_unavailable_response()
    except RuntimeError as exc:
        if "No response returned" in str(exc):
            response = Response(status_code=499)
            status_code = 499
        else:
            raise
    finally:
        try:
            platform_metrics.record_route_metric(
                method=request.method,
                route=_normalise_route_for_metrics(request),
                status_code=status_code,
                duration_ms=(time.perf_counter() - started) * 1000,
                tenant_id=tenant_id,
                is_platform_route=request.url.path.startswith("/platform") or request.url.path.startswith("/accounts/admin/platform"),
                timeout=timeout_error,
            )
        except Exception:
            logger.debug("Failed to record platform route metric", exc_info=True)
        count = query_count()
        end_counting(query_token)
    if os.getenv("EXPOSE_DB_QUERY_COUNT_HEADER", "false").lower() in {"1", "true", "yes", "on"}:
        response.headers["X-DB-Query-Count"] = str(count)
    if tenant_id and 200 <= status_code < 500:
        try:
            _queue_api_usage(str(tenant_id))
        except Exception:
            logger.debug("Failed to queue API usage", exc_info=True)
    return response


@app.middleware("http")
async def enforce_request_size_limit(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit():
        limit = max_request_body_bytes
        if limit <= 0:
            cached = _get_platform_settings_cached()
            if cached and cached.max_request_body_bytes:
                limit = int(cached.max_request_body_bytes)
        if limit > 0 and int(content_length) > limit:
            return Response(status_code=413, content="Request body too large.")
    try:
        return await call_next(request)
    except asyncio.CancelledError:
        return Response(status_code=499)
    except SQLAlchemyTimeoutError:
        return _pool_timeout_response()
    except RuntimeError as exc:
        if "No response returned" in str(exc):
            return Response(status_code=499)
        raise


@app.get("/", tags=["health"])
def read_root():
    return {"status": "ok", "message": "AMO Portal backend is running"}

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}

@app.get("/livez", tags=["health"])
def livez():
    """Process liveness only; never claims that PostgreSQL is ready."""
    return {"status": "alive", "process": True}


_readiness_migration_cache: dict[str, object] = {"checked_at": 0.0, "ready": False, "detail": "Not checked"}


def _revision_applied_in_database(
    script: ScriptDirectory,
    required: str,
    database_heads: set[str],
) -> bool:
    """Return True when ``required`` is a DB head row or an ancestor of any DB head.

    Alembic stores current branch tips in ``alembic_version``, not every historical
    revision. A configured expected revision that is an ancestor of an applied head
    is therefore already satisfied.
    """
    if required in database_heads:
        return True
    try:
        script.get_revision(required)
    except Exception:
        return False
    for head in database_heads:
        try:
            for rev in script.iterate_revisions(head, "base"):
                if rev.revision == required:
                    return True
        except Exception:
            continue
    return False


def _migration_readiness() -> tuple[bool, str | None]:
    now = time.monotonic()
    if now - float(_readiness_migration_cache["checked_at"] or 0.0) < 30.0:
        detail = str(_readiness_migration_cache["detail"] or "") or None
        return bool(_readiness_migration_cache["ready"]), detail
    db = WriteSessionLocal()
    try:
        script = ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parent / "alembic.ini")))
        repository_heads = set(script.get_heads())
        database_heads = {str(row[0]) for row in db.execute(text("SELECT version_num FROM alembic_version")).fetchall()}
        configured_heads = {
            value.strip()
            for value in (os.getenv("DATABASE_EXPECTED_ALEMBIC_HEADS") or "").split(",")
            if value.strip()
        }
        required_heads = configured_heads or repository_heads
        # Independent module branches may intentionally create multiple heads.
        # A release can declare its required subset without reporting unrelated
        # module heads as missing. Historical ancestors of applied heads count as
        # satisfied — they are not expected to remain as alembic_version rows.
        missing = sorted(
            revision
            for revision in required_heads
            if not _revision_applied_in_database(script, revision, database_heads)
        )
        ready = bool(database_heads) and not missing
        detail = None if ready else (
            f"Database migrations {sorted(database_heads)} do not include required heads {missing}"
        )
    except Exception as exc:
        ready = False
        detail = f"Migration readiness check failed: {str(exc)[:240]}"
    finally:
        close_session_safely(db)
    _readiness_migration_cache.update({"checked_at": now, "ready": ready, "detail": detail or ""})
    return ready, detail


def _readiness_response() -> JSONResponse:
    db_ok = probe_database(force=database_circuit.allow_request())
    migrations_ok, migration_detail = _migration_readiness() if db_ok else (False, "Database unavailable")
    job_runtime = portal_job_supervisor_status()
    worker_families = dict(job_runtime.get("families") or {})
    jobs_ok = not job_runtime["enabled"] or (
        job_runtime["running"] and bool(worker_families) and all(worker_families.values())
    )
    healthy = db_ok and migrations_ok and jobs_ok
    circuit = database_circuit.snapshot()
    payload = {
        "status": "ok" if healthy else "degraded",
        "db": db_ok,
        "migrations": {"ready": migrations_ok, "detail": migration_detail},
        "ready": healthy,
        "request_accepted": healthy,
        "error_code": None if healthy else (
            "DB_TEMPORARILY_UNAVAILABLE" if not db_ok else "SERVICE_NOT_READY"
        ),
        "retryable": not healthy,
        "broker": realtime_gateway.health(),
        "jobs": job_runtime,
        "database_circuit": circuit,
        "connection_budget": connection_budget().payload(),
    }
    headers = {
        "Cache-Control": "no-store",
        "X-Portal-Readiness": "ready" if healthy else "degraded",
    }
    if not healthy:
        headers["Retry-After"] = str(max(1, int(circuit.get("retry_after_seconds") or 1)))
    return JSONResponse(status_code=200 if healthy else 503, content=payload, headers=headers)


@app.get("/readyz", tags=["health"])
def readyz():
    return _readiness_response()


@app.get("/healthz", tags=["health"])
def healthz():
    return _readiness_response()

@app.get("/time", tags=["health"])
def server_time():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return {
        "utc": now.isoformat(),
        "epoch_ms": int(now.timestamp() * 1000),
        "source": "server",
    }

app.include_router(accounts_public_router)
app.include_router(platform_router)
app.include_router(foundations_router)
app.include_router(rostering_router)
app.include_router(resilience_router)
app.include_router(accounts_admin_router)
app.include_router(accounts_modules_router)
app.include_router(accounts_amo_assets_router)
app.include_router(accounts_onboarding_router)
app.include_router(fleet_router)
app.include_router(aircraft_architecture_router)
app.include_router(work_router)
app.include_router(crs_router)
app.include_router(training_router)
app.include_router(training_public_router)
app.include_router(quality_public_router)
app.include_router(quality_router)
app.include_router(reliability_router)
app.include_router(inventory_router)
app.include_router(finance_router)
app.include_router(billing_router)
app.include_router(audit_router)
app.include_router(audit_events_router)
app.include_router(notifications_router)
app.include_router(tasks_router)
app.include_router(bootstrap_router)
app.include_router(integrations_router)
app.include_router(events_router)
app.include_router(realtime_router)
app.include_router(manuals_router)
app.include_router(manuals_branding_router)
app.include_router(doc_control_router)
app.include_router(technical_records_router)
app.include_router(canonical_quality_router)
app.include_router(aerodoc_router)
