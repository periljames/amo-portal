"""CAR-linked Pareto based on the existing authoritative QMS analysis cohort.

This route is authenticated Quality-only. Bearer-token respondents cannot
query other tenant findings or make unsupported aggregate RCA assertions.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from .analysis_router import build_snapshot
from .car_rca_models import QualityCarRcaParetoSnapshot
from .car_rca_router import _car_for_employee
from .tenant_security import (
    TenantContext, assert_quality_permission, require_quality_permission,
    set_postgres_tenant_context, write_tenant_context
)

router = APIRouter(prefix="/cars/{car_id}/pareto-snapshots", tags=["Quality / CAR Pareto"])
GROUPS = {"severity": "severity", "finding_type": "types", "requirement": "requirements"}


class ParetoSnapshotCreate(BaseModel):
    start: date
    end: date
    group_by: Literal["severity", "finding_type", "requirement"] = "requirement"


def _serialize(row: QualityCarRcaParetoSnapshot):
    return {
        "id": str(row.id),
        "car_id": str(row.car_id),
        "filters": row.filters,
        "population": row.population,
        "sample_size": row.sample_size,
        "categories": row.categories,
        "source_references": row.source_references,
        "source_reference_count": row.source_reference_count,
        "source_references_truncated": row.sample_size > row.source_reference_count,
        "created_at": row.created_at,
        "created_by_user_id": row.created_by_user_id,
        "fingerprint": row.fingerprint,
        "source_kind": "QMS_AUDIT_FINDINGS",
    }


def _source_snapshot(db: Session, ctx: TenantContext, payload: ParetoSnapshotCreate):
    if payload.end < payload.start or (payload.end - payload.start).days > 366 * 5:
        raise HTTPException(status_code=422, detail="Select an ordered range of no more than five years.")
    snapshot = build_snapshot(
        db, ctx.amo_id, payload.start, payload.end, offset=0, limit=100
    )
    population = int(snapshot["total"])
    groups = [
        {"category": str(row["name"]), "count": int(row["count"])}
        for row in snapshot[GROUPS[payload.group_by]]
    ]
    if payload.group_by == "requirement" and snapshot.get("requirement_tail"):
        groups.append({
            "category": "Other requirements (beyond first 30)",
            "count": int(snapshot["requirement_tail"]),
        })
    groups.sort(key=lambda entry: (-entry["count"], entry["category"]))
    # Counts originate in one authoritative full-population query. A bounded
    # source listing is explicitly marked incomplete rather than invented.
    if sum(entry["count"] for entry in groups) != population:
        raise HTTPException(status_code=503, detail="QMS source frequencies did not reconcile to cohort population.")
    cumulative = 0
    frequencies = []
    for entry in groups:
        cumulative += entry["count"]
        frequencies.append({
            **entry,
            "share_percent": round(100 * entry["count"] / population, 4) if population else 0,
            "cumulative_percent": round(100 * cumulative / population, 4) if population else 0,
        })
    source_rows = [
        {
            "id": row["id"], "audit_id": row["audit_id"],
            "reference": row.get("reference"),
            "audit_reference": row.get("audit_reference"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
            "requirement": row.get("requirement"),
            "severity": row.get("severity"),
            "finding_type": row.get("finding_type"),
        }
        for row in snapshot["sources"]
    ]
    filters = {
        "start": payload.start.isoformat(), "end": payload.end.isoformat(),
        "group_by": payload.group_by, "source_type": "QMS_AUDIT_FINDINGS",
        "cohort_definition": "Finding created_at (UTC), non-deleted QMS audits",
    }
    return {
        "filters": filters, "population": snapshot["population"],
        "sample_size": population, "categories": frequencies,
        "source_references": source_rows, "source_reference_count": len(source_rows),
        "source_references_truncated": len(source_rows) < population,
        "source_kind": "QMS_AUDIT_FINDINGS",
        "warning": (
            "This analysis shows concentration of findings, not established causation."
            + (" Fewer than five occurrences; interpret cautiously." if population < 5 else "")
        ),
    }


@router.get("")
def list_pareto_snapshots(
    car_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")),
    db: Session = Depends(get_read_db),
):
    assert_quality_permission(db, ctx, "qms.reports.view")
    _car_for_employee(db, ctx, car_id)
    items = db.query(QualityCarRcaParetoSnapshot).filter(
        QualityCarRcaParetoSnapshot.amo_id == ctx.amo_id,
        QualityCarRcaParetoSnapshot.car_id == car_id,
    ).order_by(QualityCarRcaParetoSnapshot.created_at.desc()).limit(25).all()
    return [_serialize(row) for row in items]


@router.post("", status_code=201)
def save_pareto_snapshot(
    car_id: uuid.UUID,
    payload: ParetoSnapshotCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    assert_quality_permission(db, ctx, "qms.car.manage")
    assert_quality_permission(db, ctx, "qms.reports.view")
    car = _car_for_employee(db, ctx, car_id, lock=True)
    if str(getattr(car.status, "value", car.status)) in {"CLOSED", "CANCELLED", "ESCALATED"}:
        raise HTTPException(status_code=409, detail="This CAR is no longer open for new investigation snapshots.")
    snapshot = _source_snapshot(db, ctx, payload)
    basis = {key: snapshot[key] for key in ("filters", "sample_size", "categories", "source_references")}
    fingerprint = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = db.query(QualityCarRcaParetoSnapshot).filter(
        QualityCarRcaParetoSnapshot.amo_id == ctx.amo_id,
        QualityCarRcaParetoSnapshot.car_id == car_id,
        QualityCarRcaParetoSnapshot.fingerprint == fingerprint,
    ).first()
    if existing:
        return _serialize(existing)
    row = QualityCarRcaParetoSnapshot(
        id=uuid.uuid4(), amo_id=ctx.amo_id, car_id=car_id,
        fingerprint=fingerprint, filters=snapshot["filters"],
        population=snapshot["population"], sample_size=snapshot["sample_size"],
        categories=snapshot["categories"], source_references=snapshot["source_references"],
        source_reference_count=snapshot["source_reference_count"],
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    return _serialize(row)
