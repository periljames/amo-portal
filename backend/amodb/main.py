# backend/amodb/main.py
import os
import time
import logging
from pathlib import Path
from typing import List

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from jose import JWTError, jwt
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from .database import Base, engine, WriteSessionLocal  
from .security import JWT_ALGORITHM, SECRET_KEY
from .apps.accounts import models as accounts_models

from .apps.accounts.router_public import router as accounts_public_router
from .apps.accounts.router_admin import router as accounts_admin_router
from .apps.accounts.router_modules_admin import router as accounts_modules_router
from .apps.accounts.router_amo_assets import router as accounts_amo_assets_router
from .apps.accounts.router_onboarding import router as accounts_onboarding_router
from .apps.fleet.router import router as fleet_router
from .apps.work.router import router as work_router
from .apps.crs.router import router as crs_router
from .apps.training.router import router as training_router
from .apps.quality import router as quality_router  
from .apps.reliability.router import router as reliability_router
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
        db.close()


def _get_platform_settings_cached() -> accounts_models.PlatformSettings | None:
    if platform_settings_cache_ttl <= 0:
        return _platform_settings_cache.get("data")  # type: ignore[return-value]
    now = time.monotonic()
    cached_at = float(_platform_settings_cache.get("at") or 0.0)
    cached_data = _platform_settings_cache.get("data")
    if cached_data and now - cached_at <= platform_settings_cache_ttl:
        return cached_data  # type: ignore[return-value]
    db = WriteSessionLocal()
    try:
        cached_data = db.query(accounts_models.PlatformSettings).first()
    except Exception:
        cached_data = None
    finally:
        db.close()
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
        db.close()

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
    _enforce_schema_head_sync_if_configured()
    realtime_gateway.connect()

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


@app.middleware("http")
async def meter_api_calls(request: Request, call_next):
    try:
        response = await call_next(request)
    except RuntimeError as exc:
        # Starlette can raise this when the client disconnects mid-flight
        # (common with long-poll/SSE reconnect churn). We treat it as a
        # non-fatal disconnect to avoid bubbling noisy ExceptionGroups.
        if "No response returned" in str(exc):
            return Response(status_code=499)
        raise
    auth_header = request.headers.get("Authorization") or ""
    if " " in auth_header:
        scheme, token = auth_header.split(" ", 1)
        if scheme.lower() == "bearer" and token:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
                amo_id = payload.get("amo_id")
                if amo_id:
                    db = WriteSessionLocal()
                    try:
                        account_services.record_usage(
                            db,
                            amo_id=amo_id,
                            meter_key=account_services.METER_KEY_API_CALLS,
                            quantity=1,
                        )
                    except Exception:
                        db.rollback()
                    finally:
                        db.close()
            except (JWTError, Exception):
                pass
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

@app.get("/healthz", tags=["health"])
def healthz():
    db_ok = True
    try:
        db = WriteSessionLocal()
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    finally:
        try:
            db.close()
        except Exception:
            pass
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "broker": realtime_gateway.health()}

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
app.include_router(accounts_admin_router)
app.include_router(accounts_modules_router)
app.include_router(accounts_amo_assets_router)
app.include_router(accounts_onboarding_router)
app.include_router(fleet_router)
app.include_router(work_router)
app.include_router(crs_router)
app.include_router(training_router)
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
app.include_router(aerodoc_router)
