"""Tenant-scoped scanned SL/MCM/1 evidence retained in shared object storage.

Source-file custody belongs to Technical Records; uploading here creates an
immutable reference for OCTM verification but does not issue or certify a CRS.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Session

from amodb import storage
from amodb.database import Base
from amodb.apps.fleet.models import Aircraft
from amodb.utils.identifiers import generate_uuid7
from . import octm
from . import advanced_services as access

MAX_SOURCE_BYTES = 20 * 1024 * 1024
PREFIX = "OCTM_ASSET:"
router = APIRouter()


class OCTMSourceAsset(Base):
    __tablename__ = "reliability_octm_source_assets"
    __table_args__ = (
        Index("ix_octm_source_asset_page", "amo_id", "aircraft_serial_number", "techsheet_ref"),
        Index("ix_octm_source_asset_checksum", "amo_id", "sha256"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    aircraft_serial_number = Column(String(50), nullable=False)
    techsheet_ref = Column(String(160), nullable=False)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    object_uri = Column(String(2048), nullable=False)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=octm.utcnow)


def _asset_ref(asset: OCTMSourceAsset) -> str:
    return PREFIX + asset.id


def _details(asset: OCTMSourceAsset) -> dict:
    return {
        "id": asset.id, "source_evidence_ref": _asset_ref(asset),
        "aircraft_serial_number": asset.aircraft_serial_number,
        "techsheet_ref": asset.techsheet_ref, "filename": asset.filename,
        "mime_type": asset.mime_type, "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _checked_asset(db: Session, amo_id: str, asset_id: str) -> OCTMSourceAsset:
    try:
        UUID(asset_id)
    except (ValueError, TypeError):
        raise HTTPException(404, "Technical-log source file not found") from None
    asset = db.query(OCTMSourceAsset).filter(
        OCTMSourceAsset.amo_id == amo_id, OCTMSourceAsset.id == asset_id
    ).first()
    if not asset:
        raise HTTPException(404, "Technical-log source file not found")
    return asset


def validate_source_reference(
    db: Session, amo_id: str, aircraft: str, techsheet: str, reference: str | None,
) -> None:
    """An internally retained asset can NEVER be attached to another aircraft,
    technical-log page or tenant. Legacy external references remain descriptive.
    """
    if not reference or not reference.startswith(PREFIX):
        return
    asset = _checked_asset(db, amo_id, reference[len(PREFIX):])
    if asset.aircraft_serial_number != aircraft or asset.techsheet_ref != techsheet:
        raise HTTPException(422, "Source file belongs to another aircraft or technical-log page")


def _source_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    raise HTTPException(422, "Only signed/scanned PDF, PNG or JPEG technical-log page sources are accepted")


@router.post("/octm/source-assets", status_code=201)
async def upload_techlog_asset(
    aircraft_serial_number: str = Form(...),
    techsheet_ref: str = Form(...),
    file: UploadFile = File(...),
    ctx=Depends(octm.context),
):
    db, amo_id, actor = ctx
    permissions = access.capabilities_for_user(db, actor)
    if not ({"reliability.ingest", "reliability.data_quality.resolve"} & set(permissions)):
        raise HTTPException(403, "Reliability source capture or data-quality permission required")
    aircraft = aircraft_serial_number.strip()
    page = techsheet_ref.strip()
    if not aircraft or len(aircraft) > 50 or not page or len(page) > 160:
        raise HTTPException(422, "A registered aircraft and a valid page number are required")
    if not db.query(Aircraft).filter(
        Aircraft.amo_id == amo_id, Aircraft.serial_number == aircraft
    ).first():
        raise HTTPException(422, "Aircraft does not belong to this tenant")
    data = await file.read(MAX_SOURCE_BYTES + 1)
    await file.close()
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(413, "Source document must be nonempty and at most 20 MB")
    mime, ext = _source_type(data)
    digest = hashlib.sha256(data).hexdigest()
    safe_name = Path((file.filename or "").replace("\\", "/")).name.strip()[:255] or "technical-log" + ext
    if not safe_name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
        raise HTTPException(422, "Source filename must identify a PDF, PNG or JPEG file")
    if mime == "application/pdf" and not safe_name.lower().endswith(".pdf"):
        raise HTTPException(422, "Filename extension conflicts with PDF content")
    if mime == "image/png" and not safe_name.lower().endswith(".png"):
        raise HTTPException(422, "Filename extension conflicts with PNG content")
    if mime == "image/jpeg" and not safe_name.lower().endswith((".jpg", ".jpeg")):
        raise HTTPException(422, "Filename extension conflicts with JPEG content")
    existing = db.query(OCTMSourceAsset).filter_by(
        amo_id=amo_id, aircraft_serial_number=aircraft, techsheet_ref=page,
        sha256=digest,
    ).first()
    if existing:
        return _details(existing)
    asset = OCTMSourceAsset(
        amo_id=amo_id, aircraft_serial_number=aircraft, techsheet_ref=page,
        filename=safe_name, mime_type=mime, size_bytes=len(data), sha256=digest,
        uploaded_by_user_id=str(actor.id),
    )
    # UUID exists before object storage and serves as an unguessable immutable key.
    asset.id = str(generate_uuid7())
    key = f"tenants/{amo_id}/reliability/octm/techlogs/{asset.id}{ext}"
    stored = storage.put_stream(BytesIO(data), key=key, content_type=mime)
    asset.object_uri = stored.uri
    try:
        db.add(asset)
        access.append_audit(db, amo_id=amo_id, entity_type="OCTM_SOURCE_ASSET",
                            entity_id=asset.id, action="SOURCE_SCAN_RETAINED",
                            payload={"techsheet_ref": page, "aircraft": aircraft,
                                     "sha256": digest, "mime_type": mime, "bytes": len(data)},
                            actor_user_id=str(actor.id))
        db.commit()
        db.refresh(asset)
    except Exception:
        db.rollback()
        storage.delete(stored.uri)
        raise
    return _details(asset)


@router.get("/octm/source-assets/{asset_id}")
def get_source_asset(asset_id: str, ctx=Depends(octm.context)):
    octm.require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    return _details(_checked_asset(db, amo_id, asset_id))


@router.get("/octm/source-assets/{asset_id}/content")
def read_source_asset(asset_id: str, ctx=Depends(octm.context)):
    octm.require(ctx, "reliability.read")
    db, amo_id, _ = ctx
    asset = _checked_asset(db, amo_id, asset_id)
    try:
        path = storage.materialize(asset.object_uri, expected_sha256=asset.sha256)
    except (FileNotFoundError, IOError, ValueError) as exc:
        raise HTTPException(503, "Retained technical-log evidence unavailable or checksum verification failed") from exc
    return FileResponse(
        path, media_type=asset.mime_type, filename=asset.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
