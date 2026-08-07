from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkbookSheetPreview(BaseModel):
    name: str
    state: str = "VISIBLE"
    row_count: int
    column_count: int
    sample_rows: list[list[Any]] = Field(default_factory=list)


class OemWorkbookPreview(BaseModel):
    filename: str
    extension: str
    size_bytes: int
    checksum_sha256: str
    detected_profile: str
    profile_confidence: str
    workbook_kind: str
    sheets: list[WorkbookSheetPreview]
    warnings: list[str] = Field(default_factory=list)
    recommended_pack_code: str | None = None
    source_manifest: dict[str, Any] = Field(default_factory=dict)
