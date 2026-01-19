# backend/amodb/main.py
import os
from typing import List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt

from .database import Base, engine, WriteSessionLocal  
from .security import JWT_ALGORITHM, SECRET_KEY

from .apps.accounts.router_public import router as accounts_public_router
from .apps.accounts.router_admin import router as accounts_admin_router
from .apps.fleet.router import router as fleet_router
from .apps.work.router import router as work_router
from .apps.crs.router import router as crs_router
from .apps.training.router import router as training_router
from .apps.quality import router as quality_router  
from .apps.reliability.router import router as reliability_router
from .apps.accounts.router_billing import router as billing_router
from .apps.accounts import services as account_services


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


@app.middleware("http")
async def meter_api_calls(request: Request, call_next):
    response = await call_next(request)
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
app.include_router(billing_router)
