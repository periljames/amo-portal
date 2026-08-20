from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from . import models as training_models
from . import record_lifecycle as training_record_lifecycle


AUTO_SEEDED_MARKER = "AUTO-SEEDED FROM INITIAL "
DERIVED_VERIFICATION_COMMENT = "Derived from a verified initial-course completion."


@dataclass(frozen=True)
class SyntheticRecurrentCandidate:
    record_id: str
    amo_id: str
    user_id: str
    course_id: str
    completion_date: Optional[str]
    valid_until: Optional[str]
    remarks: str
    has_evidence: bool
    deterministic: bool
    action: str


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else (str(value) if value is not None else None)


def identify_synthetic_recurrent_records(db: Session, *, amo_id: str) -> list[SyntheticRecurrentCandidate]:
    """Identify legacy auto-seeded rows using machine provenance, tenant-scoped.

    A row is deterministic only when it carries both the historical auto-seed
    marker and the verification comment emitted by the seeding function. Rows
    with linked evidence are never auto-reconciled and require human review.
    """

    rows = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == amo_id,
            training_models.TrainingRecord.remarks.ilike(f"%{AUTO_SEEDED_MARKER}%"),
        )
        .order_by(training_models.TrainingRecord.created_at.asc(), training_models.TrainingRecord.id.asc())
        .all()
    )
    if not rows:
        return []

    record_ids = [str(row.id) for row in rows]
    evidence_ids = {
        str(record_id)
        for (record_id,) in db.query(training_models.TrainingFile.record_id)
        .filter(
            training_models.TrainingFile.amo_id == amo_id,
            training_models.TrainingFile.record_id.in_(record_ids),
        )
        .all()
        if record_id
    }

    candidates: list[SyntheticRecurrentCandidate] = []
    for row in rows:
        has_evidence = str(row.id) in evidence_ids
        deterministic = (
            AUTO_SEEDED_MARKER in str(row.remarks or "")
            and str(getattr(row, "verification_comment", "") or "").strip() == DERIVED_VERIFICATION_COMMENT
        )
        if has_evidence:
            action = "REVIEW_REQUIRED_EVIDENCE_PRESENT"
        elif deterministic:
            action = "SUPERSEDE_SYNTHETIC_ROW"
        else:
            action = "REVIEW_REQUIRED_PROVENANCE_INCOMPLETE"
        candidates.append(
            SyntheticRecurrentCandidate(
                record_id=str(row.id),
                amo_id=str(row.amo_id),
                user_id=str(row.user_id),
                course_id=str(row.course_id),
                completion_date=_iso(row.completion_date),
                valid_until=_iso(row.valid_until),
                remarks=str(row.remarks or ""),
                has_evidence=has_evidence,
                deterministic=deterministic,
                action=action,
            )
        )
    return candidates


def reconcile_synthetic_recurrent_records(
    db: Session,
    *,
    amo_id: str,
    apply: bool = False,
    actor_user_id: Optional[str] = None,
) -> dict:
    """Dry-run by default; apply only deterministic, evidence-free candidates.

    No row is deleted. Applied rows become SUPERSEDED historical records and
    keep their original values and provenance in-place for audit/reversal.
    """

    candidates = identify_synthetic_recurrent_records(db, amo_id=amo_id)
    changed: list[str] = []
    if apply:
        by_id = {
            str(row.id): row
            for row in db.query(training_models.TrainingRecord)
            .filter(
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.id.in_([item.record_id for item in candidates]),
            )
            .all()
        }
        now = datetime.now(timezone.utc)
        for item in candidates:
            if item.action != "SUPERSEDE_SYNTHETIC_ROW":
                continue
            row = by_id.get(item.record_id)
            if row is None:
                continue
            row.record_status = training_record_lifecycle.RECORD_STATUS_SUPERSEDED
            row.source_status = training_record_lifecycle.RECORD_STATUS_SUPERSEDED
            row.superseded_at = now
            row.remarks = training_record_lifecycle.append_lifecycle_remark(
                f"{row.remarks or ''} | SyntheticRecurrentReconciliation={now.isoformat()}",
                training_record_lifecycle.RECORD_STATUS_SUPERSEDED,
            )
            if hasattr(row, "updated_by_user_id") and actor_user_id:
                row.updated_by_user_id = actor_user_id
            db.add(row)
            changed.append(item.record_id)
        db.flush()

    return {
        "amo_id": amo_id,
        "apply": apply,
        "candidate_count": len(candidates),
        "changed_count": len(changed),
        "changed_record_ids": changed,
        "candidates": [asdict(item) for item in candidates],
    }


def reconciliation_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def reconciliation_csv(candidates: Iterable[SyntheticRecurrentCandidate]) -> str:
    buffer = io.StringIO()
    fields = [field.name for field in SyntheticRecurrentCandidate.__dataclass_fields__.values()]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for item in candidates:
        writer.writerow(asdict(item))
    return buffer.getvalue()


__all__ = [
    "AUTO_SEEDED_MARKER",
    "DERIVED_VERIFICATION_COMMENT",
    "SyntheticRecurrentCandidate",
    "identify_synthetic_recurrent_records",
    "reconcile_synthetic_recurrent_records",
    "reconciliation_csv",
    "reconciliation_json",
]
