from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

ADMIN_SETTINGS_KEY = "document_control_admin"


class DocumentReminderPolicy(BaseModel):
    enabled: bool = True
    lead_days: list[int] = Field(default_factory=lambda: [30, 14, 7], min_length=1, max_length=8)
    overdue_repeat_days: int = Field(default=7, ge=1, le=90)
    owner_escalation_days: int = Field(default=7, ge=1, le=365)
    quality_escalation_days: int = Field(default=14, ge=1, le=365)
    portal_notifications_enabled: bool = True
    email_notifications_enabled: bool = False

    @field_validator("lead_days")
    @classmethod
    def normalize_lead_days(cls, value: list[int]) -> list[int]:
        normalized = sorted({int(item) for item in value if 1 <= int(item) <= 365}, reverse=True)
        if not normalized:
            raise ValueError("At least one reminder lead day between 1 and 365 is required")
        return normalized


def reminder_policy_from_settings(settings_json: dict | None) -> DocumentReminderPolicy:
    settings = dict(settings_json or {})
    admin = settings.get(ADMIN_SETTINGS_KEY)
    admin_payload = dict(admin) if isinstance(admin, dict) else {}
    return DocumentReminderPolicy.model_validate(admin_payload.get("reminder_policy") or {})
