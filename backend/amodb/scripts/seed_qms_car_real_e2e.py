"""Add an independent CAR control-loop record to the disposable QMS fixture."""
from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.quality import models as quality_models  # noqa: E402
from amodb.apps.quality.enums import (  # noqa: E402
    CARPriority,
    CARProgram,
    CARStatus,
    FindingLevel,
    QMSFindingSeverity,
    QMSFindingType,
)
from amodb.database import WriteSessionLocal  # noqa: E402

FIXTURE_PATH = Path(os.environ.get("E2E_QMS_LIVE_FIXTURE", "/tmp/qms-live-audit-real-e2e.json"))
CAR_FINDING_ID = uuid.UUID("00000000-0000-4000-8000-000000000733")
CAR_ID = uuid.UUID("00000000-0000-4000-8000-000000000734")
CAR_NUMBER = "Q-2026-0993"


def seed() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    db = WriteSessionLocal()
    try:
        finding = quality_models.QMSAuditFinding(
            id=CAR_FINDING_ID,
            amo_id=fixture["amo_id"],
            audit_id=uuid.UUID(fixture["realtime_audit_id"]),
            finding_ref=f"{fixture['realtime_audit_ref']}-F-CAR",
            finding_type=QMSFindingType.NON_CONFORMITY,
            severity=QMSFindingSeverity.MINOR,
            level=FindingLevel.LEVEL_3,
            requirement_ref="QMS-CAR-REAL-001",
            description="A sampled corrective-action register entry lacked a staged effectiveness checkpoint and evidence index.",
            objective_evidence="The sampled entry had an owner and due date but no separately governed effectiveness milestone.",
            target_close_date=date.today() + timedelta(days=28),
        )
        invite_token = secrets.token_urlsafe(32)
        car = quality_models.CorrectiveActionRequest(
            id=CAR_ID,
            amo_id=fixture["amo_id"],
            program=CARProgram.QUALITY,
            car_number=CAR_NUMBER,
            title="Restore staged CAR effectiveness governance",
            summary="Add accountable RCA/CAPA milestones, evidence indexing and effectiveness verification before closure.",
            requested_by_user_id=fixture["realtime_user_a_id"],
            assigned_to_user_id=fixture["realtime_user_b_id"],
            priority=CARPriority.HIGH,
            status=CARStatus.OPEN,
            invite_token=invite_token,
            reminder_interval_days=7,
            due_date=date.today() + timedelta(days=21),
            target_closure_date=date.today() + timedelta(days=28),
            finding_id=finding.id,
            root_cause_status="PENDING",
            capa_status="PENDING",
            evidence_required=True,
        )
        db.add_all([finding, car])
        db.commit()
        fixture.update({
            "car_loop_finding_id": str(CAR_FINDING_ID),
            "car_loop_id": str(CAR_ID),
            "car_loop_number": CAR_NUMBER,
            "car_loop_invite_token": invite_token,
        })
        FIXTURE_PATH.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
        print(f"Seeded real CAR control-loop fixture {CAR_NUMBER}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
