from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AISettingsUpdate(BaseModel):
    enabled: bool
    provider: str = Field(default="openai", min_length=2, max_length=32)
    default_model: str = Field(min_length=2, max_length=96)
    lightweight_model: str = Field(min_length=2, max_length=96)
    embedding_model: str = Field(min_length=2, max_length=96)
    plan_type: str = Field(min_length=2, max_length=32)
    monthly_token_allowance: int = Field(default=0, ge=0)
    monthly_request_allowance: int = Field(default=0, ge=0)
    max_input_tokens_per_request: int = Field(default=0, ge=0)
    max_output_tokens_per_request: int = Field(default=0, ge=0)
    usage_limits: dict[str, int | float | str | bool] = Field(default_factory=dict)
    enabled_features: list[str] = Field(default_factory=list, max_length=64)
    allow_external_document_context: bool = False
    reason: str = Field(min_length=4, max_length=1000)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("plan_type")
    @classmethod
    def normalize_plan(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("default_model", "lightweight_model", "embedding_model")
    @classmethod
    def clean_model(cls, value: str) -> str:
        return value.strip()

    @field_validator("enabled_features")
    @classmethod
    def normalize_features(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(str(item).strip().upper() for item in value if str(item).strip()))


class AITestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, min_length=2, max_length=96)
