# backend/amodb/main.py
import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine  

from .apps.accounts.router_public import router as accounts_public_router
from .apps.accounts.router_admin import router as accounts_admin_router
from .apps.fleet.router import router as fleet_router
from .apps.work.router import router as work_router
from .apps.crs.router import router as crs_router
from .apps.training.router import router as training_router
from .apps.quality import router as quality_router  
from .apps.reliability.router import router as reliability_router


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
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://localhost:4173",
    ]


app = FastAPI(title="AMO Portal API", version="1.0.0")
cors_origins = _allowed_origins()
allow_credentials = "*" not in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["health"])
def read_root():
    return {"status": "ok", "message": "AMO Portal backend is running"}

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}

app.include_router(accounts_public_router)
app.include_router(accounts_admin_router)
app.include_router(fleet_router)
app.include_router(work_router)
app.include_router(crs_router)
app.include_router(training_router)
app.include_router(quality_router) 
app.include_router(reliability_router)
