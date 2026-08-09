from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BASE_INTERVAL_FIELDS = {"hours", "cycles", "landings", "days", "months", "years"}
COMPOUND_INTERVAL_FIELDS = {"threshold", "repeat"}
CONTROLLED_INTERVAL_FIELDS = BASE_INTERVAL_FIELDS | COMPOUND_INTERVAL_FIELDS
MPD_INTERVAL_PHASES = {
    "INTERVAL",
    "THRESHOLD",
    "INITIAL",
    "REPEAT_CUT_IN",
    "REPEAT",
    "LIMIT",
}
MPD_INTERVAL_MODES = {"SINGLE", "WHICHEVER_FIRST", "ALL_DUE", "OPPORTUNITY"}
MPD_COUNTER_CODES = {
    "FH",
    "FC",
    "EH",
    "APUH",
    "LANDINGS",
    "DY",
    "MO",
    "YR",
    "STARTS",
    "CUSTOM",
}
PLACEHOLDER_VALUES = {
    "dummy",
    "example",
    "example task",
    "not provided",
    "placeholder",
    "sample task",
    "tbd",
    "test task",
    "to be provided",
    "todo",
    "unknown",
}


def _normalised_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _reject_placeholder(value: str, *, field_name: str) -> None:
    normalised = _normalised_text(value)
    if normalised in PLACEHOLDER_VALUES or any(
        normalised.startswith(f"{marker} ")
        for marker in ("placeholder", "dummy", "tbd", "todo")
    ):
        raise ValueError(f"{field_name} contains fabricated placeholder content")


def _positive_decimal(value: Any, *, field_name: str) -> None:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{field_name} must use an exact integer or canonical decimal string")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"{field_name} must be greater than zero")
        return
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} must be a canonical decimal string") from exc
    else:
        raise ValueError(f"{field_name} must use an exact integer or canonical decimal string")
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError(f"{field_name} must be a finite value greater than zero")


def _positive_integer(value: Any, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _reject_inexact_numbers(value: Any, *, field_name: str) -> None:
    if isinstance(value, float):
        raise ValueError(f"{field_name} must not contain IEEE-754 floating-point values")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_inexact_numbers(item, field_name=f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_inexact_numbers(item, field_name=f"{field_name}[{index}]")


def _validate_mpd_interval_expression(value: dict[str, Any], *, field_name: str) -> None:
    allowed_top = {"schema", "groups", "notes", "raw", "opportunity_reference"}
    unknown = sorted(set(value) - allowed_top)
    if unknown:
        raise ValueError(f"{field_name} contains unsupported MPD fields: {', '.join(unknown)}")
    if value.get("schema") != "MPD_INTERVAL_V1":
        raise ValueError(f"{field_name}.schema must be MPD_INTERVAL_V1")
    groups = value.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError(f"{field_name}.groups must contain at least one interval group")
    for group_index, group in enumerate(groups):
        path = f"{field_name}.groups[{group_index}]"
        if not isinstance(group, dict):
            raise ValueError(f"{path} must be an object")
        allowed_group = {"phase", "mode", "limits", "reference", "notes"}
        group_unknown = sorted(set(group) - allowed_group)
        if group_unknown:
            raise ValueError(f"{path} contains unsupported fields: {', '.join(group_unknown)}")
        phase = group.get("phase")
        if phase not in MPD_INTERVAL_PHASES:
            raise ValueError(f"{path}.phase is not a supported MPD interval phase")
        mode = group.get("mode", "SINGLE")
        if mode not in MPD_INTERVAL_MODES:
            raise ValueError(f"{path}.mode is not a supported MPD interval mode")
        if mode == "OPPORTUNITY":
            reference = group.get("reference") or value.get("opportunity_reference")
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError(f"{path}.reference is required for opportunity intervals")
            if group.get("limits") not in (None, []):
                raise ValueError(f"{path}.limits must be empty for opportunity intervals")
            continue
        limits = group.get("limits")
        if not isinstance(limits, list) or not limits:
            raise ValueError(f"{path}.limits must contain at least one controlled limit")
        if mode == "SINGLE" and len(limits) != 1:
            raise ValueError(f"{path}.mode SINGLE requires exactly one limit")
        for limit_index, limit_row in enumerate(limits):
            limit_path = f"{path}.limits[{limit_index}]"
            if not isinstance(limit_row, dict):
                raise ValueError(f"{limit_path} must be an object")
            allowed_limit = {"counter", "value", "custom_counter"}
            limit_unknown = sorted(set(limit_row) - allowed_limit)
            if limit_unknown:
                raise ValueError(
                    f"{limit_path} contains unsupported fields: {', '.join(limit_unknown)}"
                )
            counter = limit_row.get("counter")
            if counter not in MPD_COUNTER_CODES:
                raise ValueError(f"{limit_path}.counter is not supported")
            if counter == "CUSTOM":
                custom_counter = limit_row.get("custom_counter")
                if not isinstance(custom_counter, str) or not custom_counter.strip():
                    raise ValueError(f"{limit_path}.custom_counter is required")
            _positive_decimal(limit_row.get("value"), field_name=f"{limit_path}.value")


def _validate_interval_mapping(value: dict[str, Any], *, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if value.get("schema") == "MPD_INTERVAL_V1":
        _validate_mpd_interval_expression(value, field_name=field_name)
        return
    unknown = sorted(set(value) - CONTROLLED_INTERVAL_FIELDS)
    if unknown:
        raise ValueError(
            f"{field_name} contains unsupported interval fields: {', '.join(unknown)}"
        )
    for key, item in value.items():
        path = f"{field_name}.{key}"
        if key in COMPOUND_INTERVAL_FIELDS:
            if not isinstance(item, dict):
                raise ValueError(f"{path} must be a controlled interval object")
            if not item:
                raise ValueError(f"{path} must not be empty")
            nested_unknown = sorted(set(item) - BASE_INTERVAL_FIELDS)
            if nested_unknown:
                raise ValueError(
                    f"{path} contains unsupported interval fields: {', '.join(nested_unknown)}"
                )
            for nested_key, nested_value in item.items():
                nested_path = f"{path}.{nested_key}"
                if nested_key == "hours":
                    _positive_decimal(nested_value, field_name=nested_path)
                else:
                    _positive_integer(nested_value, field_name=nested_path)
        elif key == "hours":
            _positive_decimal(item, field_name=path)
        else:
            _positive_integer(item, field_name=path)


def _validate_labour_hours(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = value.strip()
    if not normalised:
        return None
    if normalised.upper() in {"TBD", "N/A", "-"}:
        return normalised.upper()
    _positive_decimal(normalised, field_name="labour_hours")
    return normalised


class OemPublicationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    manufacturer: str = Field(min_length=1, max_length=120)
    family: str = Field(min_length=1, max_length=120)
    series: str | None = Field(default=None, max_length=80)
    publication_code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    publication_kind: str = Field(min_length=1, max_length=40)


class OemPublicationRevisionCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=80)
    issue_date: date | None = None
    effective_date: date | None = None
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_filename: str | None = Field(default=None, max_length=255)
    storage_locator: str | None = None
    source_url: str | None = None
    change_summary: str | None = None
    supersedes_revision_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def require_controlled_locator(self):
        if not self.storage_locator and not self.source_url and not self.source_filename:
            raise ValueError("A controlled source filename, storage locator, or source URL is required")
        return self


class OemPublicationRevisionDecision(BaseModel):
    action: Literal["VERIFY", "MAKE_CURRENT", "REJECT", "WITHDRAW"]
    decision_note: str = Field(min_length=1)


class OemTemporaryRevisionCreate(BaseModel):
    temporary_revision_code: str = Field(min_length=1, max_length=80)
    issue_date: date | None = None
    effective_date: date | None = None
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_filename: str | None = Field(default=None, max_length=255)
    storage_locator: str | None = None
    source_url: str | None = None
    replaces_temporary_revision_code: str | None = Field(default=None, max_length=80)
    filing_instructions: str | None = None
    change_summary: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def require_controlled_locator(self):
        if not self.storage_locator and not self.source_url and not self.source_filename:
            raise ValueError("A controlled source filename, storage locator, or source URL is required")
        return self


class OemTemporaryRevisionDecision(BaseModel):
    status: Literal["ACTIVE", "INCORPORATED", "SUPERSEDED", "WITHDRAWN", "REPLACED"]
    decision_note: str = Field(min_length=1)


class OemSourceWatchCreate(BaseModel):
    channel_type: Literal["MANUAL_UPLOAD", "OEM_PORTAL", "EMAIL_NOTICE", "RSS", "API", "OTHER"]
    reference: str = Field(min_length=1)
    is_active: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OemSourceWatchCheck(BaseModel):
    seen_marker: str | None = Field(default=None, max_length=255)
    result: str = Field(min_length=1)


class ContentSourceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=40)
    reference: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    effective_date: date | None = None
    checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    authority: str = Field(min_length=1, max_length=80)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    publication_revision_id: str | None = None
    temporary_revision_id: str | None = None
    source_page_ref: str | None = Field(default=None, max_length=120)
    document_locator: str | None = None

    @field_validator("checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def require_or_build_provenance(self):
        if "provenance_json" not in self.model_fields_set:
            self.provenance_json = {
                "authority": self.authority,
                "source_reference": self.reference,
                "source_revision": self.source_revision,
                "checksum_sha256": self.checksum_sha256,
                "provenance_basis": "CONTROLLED_SOURCE_TUPLE",
            }
        elif not self.provenance_json:
            raise ValueError("Controlled sources require provenance metadata")
        return self


class ContentPositionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=160)
    position_kind: str = Field(min_length=1, max_length=40)
    required: bool = True
    source_reference: str = Field(min_length=1, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ContentComponentCreate(BaseModel):
    definition_code: str = Field(min_length=1, max_length=80)
    position_code: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=255)
    component_class: str = Field(min_length=1, max_length=50)
    accepted_part_numbers_json: list[str] = Field(default_factory=list)
    life_limit_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=255)

    @field_validator("life_limit_json")
    @classmethod
    def exact_life_limits(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_inexact_numbers(value, field_name="life_limit_json")
        return value


class ContentTaskCreate(BaseModel):
    task_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    ata_chapter: str | None = Field(default=None, max_length=12)
    programme_section: str | None = Field(default=None, max_length=40)
    task_type: str | None = Field(default=None, max_length=16)
    intervals_json: dict[str, Any]
    raw_interval_text: str | None = None
    effectivity_expression_json: dict[str, Any] = Field(default_factory=dict)
    raw_effectivity_text: str | None = None
    source_requirements_json: list[dict[str, Any]] = Field(default_factory=list)
    task_card_number: str | None = Field(default=None, max_length=120)
    task_card_configuration: str | None = Field(default=None, max_length=120)
    amm_reference: str | None = Field(default=None, max_length=120)
    zones_json: list[str] = Field(default_factory=list)
    panels_json: list[str] = Field(default_factory=list)
    general_references_json: list[str] = Field(default_factory=list)
    skill_code: str | None = Field(default=None, max_length=40)
    labour_hours: str | None = Field(default=None, max_length=24)
    number_of_persons: int | None = Field(default=None, ge=1)
    program_notes_json: list[str] = Field(default_factory=list)
    packaging_json: dict[str, Any] = Field(default_factory=dict)
    source_page_ref: str | None = Field(default=None, max_length=120)
    source_reference: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_controlled_content(self):
        _reject_placeholder(self.task_code, field_name="task_code")
        _reject_placeholder(self.title, field_name="title")
        _validate_interval_mapping(self.intervals_json, field_name="intervals_json")
        _reject_inexact_numbers(
            self.effectivity_expression_json,
            field_name="effectivity_expression_json",
        )
        _reject_inexact_numbers(self.source_requirements_json, field_name="source_requirements_json")
        _reject_inexact_numbers(self.packaging_json, field_name="packaging_json")
        return self

    @field_validator("source_checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()

    @field_validator("labour_hours")
    @classmethod
    def exact_labour_hours(cls, value: str | None) -> str | None:
        return _validate_labour_hours(value)


class ContentResourceCreate(BaseModel):
    resource_kind: str = Field(min_length=1, max_length=50)
    resource_code: str = Field(min_length=1, max_length=140)
    title: str = Field(min_length=1, max_length=255)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    source_reference: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=80)
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_page_ref: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_checksum_sha256")
    @classmethod
    def checksum_lower(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def controlled_payload(self):
        _reject_placeholder(self.resource_code, field_name="resource_code")
        _reject_placeholder(self.title, field_name="title")
        _reject_inexact_numbers(self.payload_json, field_name="payload_json")
        return self


class ContentRevisionCreate(BaseModel):
    revision_code: str = Field(min_length=1, max_length=40)
    change_summary: str | None = None
    sources: list[ContentSourceCreate] = Field(default_factory=list)
    positions: list[ContentPositionCreate] = Field(default_factory=list)
    components: list[ContentComponentCreate] = Field(default_factory=list)
    tasks: list[ContentTaskCreate] = Field(default_factory=list)
    resources: list[ContentResourceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_controlled_identities(self):
        identities = {
            "source": [(row.reference, row.source_revision) for row in self.sources],
            "position": [row.code for row in self.positions],
            "component": [row.definition_code for row in self.components],
            "task": [row.task_code for row in self.tasks],
            "resource": [(row.resource_kind, row.resource_code) for row in self.resources],
        }
        for label, values in identities.items():
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate controlled {label} identity")
        return self


class PublishContentRevision(BaseModel):
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContentPackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    manufacturer: str
    family: str
    series: str | None = None
    description: str
    status: str
    created_at: datetime


class ContentRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pack_id: str
    revision_code: str
    status: str
    content_hash: str | None
    change_summary: str | None
    created_at: datetime
    published_at: datetime | None


class ContentSourceRead(ContentSourceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class ContentTaskRead(ContentTaskCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class ContentResourceRead(ContentResourceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class ContentRevisionDetailRead(ContentRevisionRead):
    sources: list[ContentSourceRead] = Field(default_factory=list)
    tasks: list[ContentTaskRead] = Field(default_factory=list)
    resources: list[ContentResourceRead] = Field(default_factory=list)


class OemPublicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    manufacturer: str
    family: str
    series: str | None
    publication_code: str
    title: str
    publication_kind: str
    status: str
    created_at: datetime


class OemPublicationRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    publication_id: str
    revision_code: str
    status: str
    issue_date: date | None
    effective_date: date | None
    checksum_sha256: str
    source_filename: str | None
    storage_locator: str | None
    source_url: str | None
    change_summary: str | None
    supersedes_revision_id: str | None
    submitted_by_amo_id: str | None
    verified_at: datetime | None
    created_at: datetime


class OemTemporaryRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    publication_revision_id: str
    temporary_revision_code: str
    status: str
    issue_date: date | None
    effective_date: date | None
    checksum_sha256: str
    source_filename: str | None
    storage_locator: str | None
    source_url: str | None
    replaces_temporary_revision_code: str | None
    filing_instructions: str | None
    change_summary: str | None
    submitted_by_amo_id: str | None
    verified_at: datetime | None
    created_at: datetime


class OemSourceWatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    publication_id: str
    channel_type: str
    reference: str
    is_active: bool
    last_checked_at: datetime | None
    last_seen_marker: str | None
    last_result: str | None
    created_at: datetime


class OemPublicationCurrentnessRead(BaseModel):
    publication: OemPublicationRead
    current_revision: OemPublicationRevisionRead | None
    newest_candidate: OemPublicationRevisionRead | None
    active_temporary_revisions: list[OemTemporaryRevisionRead]
    watches: list[OemSourceWatchRead]
    currentness_status: Literal[
        "NO_CURRENT_REVISION",
        "CURRENT",
        "CANDIDATE_REVIEW_REQUIRED",
        "TEMPORARY_REVISION_ACTIVE",
        "SOURCE_CHECK_REQUIRED",
    ]


class ContentRevisionDiffRead(BaseModel):
    base_revision_id: str
    target_revision_id: str
    added_tasks: list[str]
    removed_tasks: list[str]
    changed_tasks: list[str]
    unchanged_tasks: int
    added_resources: list[str]
    removed_resources: list[str]
    changed_resources: list[str]
