"""Tenant-owned Training report control metadata.

The portal must not assign a Safarilink form number, issue date or revision to every
AMO. New tenants start with blank control metadata and configure it explicitly in
the Training frontend. Existing tenant values are preserved unchanged.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from . import models as training_models


def _payload(row: Optional[training_models.TrainingReportSettings]) -> dict[str, Any]:
    return {
        "title": getattr(row, "title", None) or "Personnel Training Record",
        "subtitle": getattr(row, "subtitle", None),
        "form_no": getattr(row, "form_no", None) or "",
        "issue_date": getattr(row, "issue_date", None) or "",
        "revision": getattr(row, "revision", None) or "",
        "prepared_by": getattr(row, "prepared_by", None),
        "approved_by": getattr(row, "approved_by", None),
        "show_logo": bool(getattr(row, "show_logo", True)),
        "show_qr": bool(getattr(row, "show_qr", True)),
        "show_summary": bool(getattr(row, "show_summary", True)),
        "show_deferrals": bool(getattr(row, "show_deferrals", True)),
        "footer_note": getattr(row, "footer_note", None),
    }


def install_tenant_report_control(router_module) -> None:
    """Replace only the legacy defaulting boundary; keep established routes."""

    router_module._TRAINING_RECORD_FORM_NO = ""
    router_module._TRAINING_RECORD_ISSUE_DATE = ""
    router_module._TRAINING_RECORD_REVISION = ""
    router_module._training_report_settings_payload = _payload

    def get_or_create(
        db: Session,
        *,
        amo_id: str,
        actor_user_id: Optional[str] = None,
    ) -> training_models.TrainingReportSettings:
        router_module._ensure_training_report_settings_table(db)
        row = (
            db.query(training_models.TrainingReportSettings)
            .filter(training_models.TrainingReportSettings.amo_id == amo_id)
            .first()
        )
        if row:
            return row
        row = training_models.TrainingReportSettings(
            amo_id=amo_id,
            title="Personnel Training Record",
            subtitle="Controlled training record generated from the Training module profile.",
            form_no="",
            issue_date="",
            revision="",
            updated_by_user_id=actor_user_id,
        )
        db.add(row)
        db.flush()
        return row

    router_module._get_or_create_training_report_settings = get_or_create


__all__ = ["install_tenant_report_control"]
