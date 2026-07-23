"""Bounded ASGI entrypoint for Quality Management System deployments.

Run with::

    uvicorn amodb.quality_main:app --host 0.0.0.0 --port 8000

This profile exposes the Quality module and only the portal foundations required
for authentication, tenant/module administration, competence evidence, audit
trails, notifications, tasks, controlled documents, integrations and reporting.
It intentionally omits operational maintenance, fleet, inventory, finance,
reliability and rostering route families.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Final

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from .database import WriteSessionLocal, close_session_safely, dispose_engines
from .apps.accounts.router_public import router as accounts_public_router
from .apps.accounts.router_admin import router as accounts_admin_router
from .apps.accounts.router_modules_admin import router as accounts_modules_router
from .apps.accounts.router_onboarding import router as accounts_onboarding_router
from .apps.bootstrap.router import router as bootstrap_router
from .apps.training.router import router as training_router, public_router as training_public_router
from .apps.quality import router as quality_router, public_router as quality_public_router
from .apps.quality.canonical_router import router as canonical_quality_router, legacy_router as legacy_qms_router
from .apps.audit.router import router as audit_router
from .apps.audit.router_events import router as audit_events_router
from .apps.notifications.router import router as notifications_router
from .apps.tasks.router import router as tasks_router
from .apps.integrations.router import router as integrations_router
from .apps.events.router import router as events_router
from .apps.manuals.router import router as manuals_router
from .apps.manuals.router_branding import router as manuals_branding_router
from .apps.doc_control.router import router as doc_control_router


logger = logging.getLogger(__name__)

PROFILE_NAME: Final = "quality"
PROFILE_MODULES: Final[tuple[str, ...]] = (
    "accounts",
    "bootstrap",
    "quality",
    "training",
    "audit",
    "notifications",
    "tasks",
    "integrations",
    "events",
    "manuals",
    "doc_control",
)
OMITTED_OPERATIONAL_MODULES: Final[tuple[str, ...]] = (
    "fleet",
    "work",
    "crs",
    "reliability",
    "inventory",
    "finance",
    "billing",
    "technical_records",
    "rostering",
    "workforce",
)


def _enabled(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allowed_origins() -> list[str]:
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
    ]


def _schema_strict_enabled() -> bool:
    configured = os.getenv("QUALITY_SCHEMA_STRICT")
    if configured is not None:
        return _enabled(configured)
    return not _enabled(os.getenv("QUALITY_ALLOW_SCHEMA_DRIFT"), default=False)


def _enforce_schema_head_sync() -> None:
    if not _schema_strict_enabled():
        logger.warning("Quality schema strict mode is disabled; this is not recommended for production.")
        return

    config_path = Path(__file__).resolve().parent / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(config_path)))
    repository_heads = set(script.get_heads())

    db = WriteSessionLocal()
    try:
        database_heads = {
            str(row[0])
            for row in db.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        }
    except Exception as exc:
        raise RuntimeError(
            "Quality deployment schema preflight failed. Run "
            "'alembic -c backend/amodb/alembic.ini upgrade heads' before starting the service."
        ) from exc
    finally:
        close_session_safely(db)

    if database_heads != repository_heads:
        raise RuntimeError(
            "Quality deployment schema is not at the repository Alembic head(s). "
            f"Database={sorted(database_heads)} Repository={sorted(repository_heads)}. "
            "Run 'alembic -c backend/amodb/alembic.ini upgrade heads'."
        )


def _pool_timeout_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database connection capacity is temporarily exhausted.",
            "error_code": "DB_POOL_TIMEOUT",
            "retryable": True,
        },
        headers={"Retry-After": "5"},
    )


app = FastAPI(
    title="AMO Portal Quality Management System API",
    version="1.0.0",
    description="Bounded Quality/QMS delivery profile with required portal foundations.",
)
app.state.deployment_profile = PROFILE_NAME
app.state.is_shutting_down = False

cors_origin_regex = (os.getenv("CORS_ALLOWED_ORIGIN_REGEX") or "").strip() or None
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=cors_origin_regex,
    allow_credentials=_enabled(os.getenv("CORS_ALLOW_CREDENTIALS"), default=True),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    GZipMiddleware,
    minimum_size=int(os.getenv("GZIP_MINIMUM_SIZE", "1024") or "1024"),
    compresslevel=int(os.getenv("GZIP_COMPRESSLEVEL", "6") or "6"),
)


@app.middleware("http")
async def enforce_quality_request_limits(request: Request, call_next):
    content_length = request.headers.get("content-length")
    configured_limit = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(110 * 1024 * 1024)) or "0")
    if content_length and content_length.isdigit() and configured_limit > 0:
        if int(content_length) > configured_limit:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": "Request body exceeds the configured Quality upload limit.",
                    "error_code": "REQUEST_TOO_LARGE",
                },
            )
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


@app.on_event("startup")
def quality_schema_preflight() -> None:
    app.state.is_shutting_down = False
    _enforce_schema_head_sync()


@app.on_event("shutdown")
def quality_shutdown() -> None:
    app.state.is_shutting_down = True
    dispose_engines()


@app.get("/", tags=["health"])
def root() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "AMO Portal Quality Management System",
        "profile": PROFILE_NAME,
    }


@app.get("/health", tags=["health"])
def health() -> dict[str, object]:
    database_ok = True
    db = None
    try:
        db = WriteSessionLocal()
        db.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
    finally:
        close_session_safely(db)
    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "profile": PROFILE_NAME,
    }


@app.get("/deployment-profile", tags=["health"])
def deployment_profile() -> dict[str, object]:
    return {
        "profile": PROFILE_NAME,
        "included_modules": PROFILE_MODULES,
        "omitted_operational_modules": OMITTED_OPERATIONAL_MODULES,
        "canonical_quality_prefix": "/api/maintenance/{amo_code}/quality",
        "compatibility_prefix": "/api/maintenance/{amo_code}/qms",
        "direct_quality_prefix": "/quality",
        "schema_strict": _schema_strict_enabled(),
    }


# Authentication and tenant/module administration.
app.include_router(accounts_public_router)
app.include_router(accounts_admin_router)
app.include_router(accounts_modules_router)
app.include_router(accounts_onboarding_router)
app.include_router(bootstrap_router)

# QMS operations and public CAR response surfaces.
app.include_router(quality_public_router)
app.include_router(quality_router)
app.include_router(canonical_quality_router)
app.include_router(legacy_qms_router)

# Required Quality dependencies and evidence sources.
app.include_router(training_router)
app.include_router(training_public_router)
app.include_router(audit_router)
app.include_router(audit_events_router)
app.include_router(notifications_router)
app.include_router(tasks_router)
app.include_router(integrations_router)
app.include_router(events_router)
app.include_router(manuals_router)
app.include_router(manuals_branding_router)
app.include_router(doc_control_router)
