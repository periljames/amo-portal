from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amodb.apps.platform.ops_api_router import router as versioned_ops_router
from amodb.apps.platform.ops_console_router import broker, router as console_router
from amodb.apps.platform.ops_gateway import router as operations_router, snapshot_refresher, snapshot_store
from amodb.apps.platform.ops_management_router import router as management_router
from amodb.database import dispose_engines, read_engine, write_engine
from amodb.observability import configure_telemetry


app = FastAPI(
    title="AMO Portal Platform Operations Gateway",
    version="2.3.0",
    docs_url=None if os.getenv("APP_ENV", "").lower() in {"prod", "production"} else "/docs",
)

origins = [value.strip() for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173", "https://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Cache-Control", "Last-Event-ID"],
)
app.include_router(console_router, prefix="/platform")
app.include_router(operations_router)
app.include_router(versioned_ops_router)
app.include_router(management_router)
configure_telemetry(app, service_name=os.getenv("OTEL_PLATFORM_OPS_SERVICE_NAME", "amo-portal-platform-ops"), engines=(write_engine, read_engine))


@app.on_event("startup")
async def _start_operations_gateway() -> None:
    await broker.ensure_started()
    stop = asyncio.Event()
    app.state.ops_stop = stop
    app.state.snapshot_task = asyncio.create_task(snapshot_refresher(stop), name="platform-ops-intelligence-refresh")


@app.on_event("shutdown")
async def _stop_operations_gateway() -> None:
    stop = getattr(app.state, "ops_stop", None)
    if stop is not None:
        stop.set()
    await broker.stop()
    task = getattr(app.state, "snapshot_task", None)
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)
    dispose_engines()


@app.get("/healthz", tags=["health"])
def healthz():
    broker_health = broker.health()
    intelligence = snapshot_store.status()
    running = bool(broker_health.get("running"))
    return {
        "status": "ok" if running and intelligence.get("modes") else "starting" if running else "degraded",
        "broker": broker_health,
        "intelligence": intelligence,
        "role": "platform-operations-gateway",
    }


@app.get("/readyz", tags=["health"])
def readyz():
    broker_health = broker.health()
    intelligence = snapshot_store.status()
    ready = bool(broker_health.get("prepared_snapshot") and intelligence.get("modes"))
    return {"status": "ready" if ready else "not_ready", "broker": broker_health, "intelligence": intelligence}
