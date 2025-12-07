# backend/amodb/main.py

"""
Main FastAPI application for AMOdb.

Design:
- Authentication, user lifecycle, AMO & authorisations are handled in the
  accounts app (apps.accounts.router_public / router_admin).
- This file is responsible for:
    * Creating the FastAPI app
    * Global middleware (CORS, etc.)
    * Health endpoints
    * Including feature routers (accounts, fleet, work, CRS, training)
- Database schema creation is handled by Alembic migrations.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine  # kept for Alembic / tooling

# App routers
from .apps.accounts.router_public import router as accounts_public_router
from .apps.accounts.router_admin import router as accounts_admin_router
from .apps.fleet.router import router as fleet_router
from .apps.work.router import router as work_router
from .apps.crs.router import router as crs_router
from .apps.training.router import router as training_router  # NEW

# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------

# IMPORTANT:
# Schema creation is now handled by Alembic migrations.
# Do NOT call Base.metadata.create_all() here in production.
# (You can temporarily uncomment the next line on a throwaway dev DB.)
# Base.metadata.create_all(bind=engine)

app = FastAPI(title="AMO Portal API", version="1.0.0")

# CORS – open for now, we’ll tighten later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # TODO: restrict to your frontends in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------
# HEALTH
# --------------------------------------------------------------------


@app.get("/", tags=["health"])
def read_root():
    return {"status": "ok", "message": "AMO Portal backend is running"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------
# ROUTERS
# --------------------------------------------------------------------

# Auth + accounts (AMO-aware, lockout, password reset, etc.)
app.include_router(accounts_public_router)
app.include_router(accounts_admin_router)

# Fleet / aircraft master data
app.include_router(fleet_router)

# Work orders + tasks (must exist before CRS)
app.include_router(work_router)

# CRS (tied to aircraft + work orders and authorisations)
app.include_router(crs_router)

# Training / personnel competence records (Quality edits, others read-only)
app.include_router(training_router)
