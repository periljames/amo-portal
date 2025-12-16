# backend/amodb/main.py
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

app = FastAPI(title="AMO Portal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
