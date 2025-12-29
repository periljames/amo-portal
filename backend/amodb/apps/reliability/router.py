# backend/amodb/apps/reliability/router.py

from __future__ import annotations

from fastapi import APIRouter, Depends

from amodb.entitlements import require_module

router = APIRouter(
    prefix="/reliability",
    tags=["reliability"],
    dependencies=[Depends(require_module("reliability"))],
)


@router.get("/ping")
def reliability_ping():
    return {"status": "reliability-ok"}
