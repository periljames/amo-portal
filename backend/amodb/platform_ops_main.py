from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amodb.apps.platform.ops_console_router import broker, router as console_router
from amodb.database import dispose_engines


app = FastAPI(
    title="AMO Portal Platform Operations Gateway",
    version="1.0.0",
    docs_url=None if os.getenv("APP_ENV", "").lower() in {"prod", "production"} else "/docs",
)

origins = [value.strip() for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173", "https://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
)
app.include_router(console_router, prefix="/platform")


@app.on_event("startup")
async def _start_broker() -> None:
    await broker.ensure_started()


@app.on_event("shutdown")
async def _stop_broker() -> None:
    await broker.stop()
    dispose_engines()


@app.get("/healthz", tags=["health"])
def healthz():
    health = broker.health()
    status_value = "ok" if health.get("running") else "starting"
    return {"status": status_value, "broker": health}


@app.get("/readyz", tags=["health"])
def readyz():
    health = broker.health()
    ready = bool(health.get("prepared_snapshot"))
    return {"status": "ready" if ready else "not_ready", "broker": health}
