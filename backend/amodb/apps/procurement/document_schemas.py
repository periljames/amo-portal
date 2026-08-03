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
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    notes: Optional[str] = None
    is_quality_evidence: bool
    qms_reference: Optional[str] = None
    status: document_models.ProcurementDocumentStatus
    uploaded_by_user_id: Optional[str] = None
    uploaded_at: datetime
    voided_by_user_id: Optional[str] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    download_url: str

    class Config:
        from_attributes = True


class ProcurementDocumentVoid(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)
