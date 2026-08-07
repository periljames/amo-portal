from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AmpComparisonTask(BaseModel):
    id: str
    source_content_task_id: str | None
    decision: Literal["INHERIT", "TIGHTEN", "ADD", "LEGACY"]
    task_code: str
    title: str
    ata_chapter: str | None
    programme_section: str | None = None
    task_type: str | None = None
    oem_intervals_json: dict[str, Any] | None = None
    amp_intervals_json: dict[str, Any]
    oem_raw_interval_text: str | None = None
    effectivity_expression_json: dict[str, Any]
    raw_effectivity_text: str | None = None
    source_requirements_json: list[dict[str, Any]] = Field(default_factory=list)
    source_reference: str
    source_revision: str | None = None
    source_page_ref: str | None = None
    justification: str | None = None
    approval_reference: str | None = None
    is_mandatory: bool = False
    comparison_state: Literal["SAME_AS_OEM", "MORE_RESTRICTIVE", "OPERATOR_ADDED", "LEGACY_UNMAPPED"]


class AmpComparisonPage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[AmpComparisonTask]
    counts: dict[str, int]
