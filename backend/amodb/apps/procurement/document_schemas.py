from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from . import document_models


class ProcurementDocumentRead(BaseModel):
    id: int
    entity_type: document_models.ProcurementDocumentEntityType
    entity_id: str
    document_type: str
    title: str
    document_number: Optional[str] = None
    revision: Optional[str] = None
    document_date: Optional[date] = None
    source: document_models.ProcurementDocumentSource
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    physical_reference: Optional[str] = None
    physical_location: Optional[str] = None
    external_system: Optional[str] = None
    external_reference: Optional[str] = None
    external_url: Optional[str] = None
    dms_document_id: Optional[str] = None
    dms_revision_id: Optional[str] = None
    notes: Optional[str] = None
    is_quality_evidence: bool
    qms_reference: Optional[str] = None
    verification_status: document_models.ProcurementDocumentVerificationStatus
    verification_notes: Optional[str] = None
    verified_by_user_id: Optional[str] = None
    verified_at: Optional[datetime] = None
    status: document_models.ProcurementDocumentStatus
    uploaded_by_user_id: Optional[str] = None
    uploaded_at: datetime
    voided_by_user_id: Optional[str] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    download_url: Optional[str] = None

    class Config:
        from_attributes = True


class ProcurementDocumentVoid(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)


class ProcurementDocumentVerify(BaseModel):
    outcome: document_models.ProcurementDocumentVerificationStatus
    notes: str = Field(..., min_length=3, max_length=2000)
