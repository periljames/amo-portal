from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcurementDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: str
    document_kind: str
    title: str
    source_type: str
    status: str
    file_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    physical_reference: Optional[str] = None
    physical_location: Optional[str] = None
    dms_document_id: Optional[str] = None
    dms_revision_id: Optional[str] = None
    notes: Optional[str] = None
    is_verified: bool
    uploaded_by_user_id: Optional[str] = None
    verified_by_user_id: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    download_url: Optional[str] = None


class ProcurementDocumentLinkCreate(BaseModel):
    entity_type: str = Field(min_length=2, max_length=40)
    entity_id: str = Field(min_length=1, max_length=128)
    document_kind: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=2, max_length=255)
    source_type: str = Field(pattern="^(PHYSICAL_RECORD|DMS_LINK)$")
    physical_reference: Optional[str] = Field(default=None, max_length=255)
    physical_location: Optional[str] = Field(default=None, max_length=255)
    dms_document_id: Optional[str] = Field(default=None, max_length=64)
    dms_revision_id: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_type == "PHYSICAL_RECORD" and not self.physical_reference:
            raise ValueError("A physical record reference is required.")
        if self.source_type == "DMS_LINK" and not self.dms_document_id:
            raise ValueError("A DMS document ID is required.")
        return self


class ProcurementDocumentVerify(BaseModel):
    verified: bool = True
    note: Optional[str] = None
