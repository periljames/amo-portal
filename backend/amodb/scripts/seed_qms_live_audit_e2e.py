"""Seed a deterministic real QMS Live Audit browser-acceptance fixture.

This script is only intended for the disposable PostgreSQL service created by
QMS Live Audit CI. It deliberately uses the production ORM, signed external
access-grant format and tenant-scoped audit models so Playwright can exercise a
real browser -> Vite preview -> FastAPI -> PostgreSQL journey without route
mocks or production credentials.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Importing the application registers the complete ORM graph before rows are
# created in the disposable CI database.
from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.quality import models as quality_models  # noqa: E402
from amodb.apps.quality.audit_checklist_execution_models import (  # noqa: E402
    QualityAuditChecklistExecutionGovernance,
)
from amodb.apps.quality.audit_external_access_models import (  # noqa: E402
    QualityAuditAccessGrant,
    QualityAuditFindingReleaseEvent,
    QualityAuditParticipant,
    QualityExternalIdentity,
)
from amodb.apps.quality.audit_external_access_router import _hash_token, _make_access_token  # noqa: E402
from amodb.apps.quality.enums import (  # noqa: E402
    FindingLevel,
    QMSAuditKind,
    QMSAuditStatus,
    QMSDomain,
    QMSFindingSeverity,
    QMSFindingType,
)
from amodb.database import WriteSessionLocal  # noqa: E402

AMO_ID = "00000000-0000-4000-8000-000000000701"
AUDIT_ID = uuid.UUID("00000000-0000-4000-8000-000000000702")
CHECKLIST_ITEM_ID = uuid.UUID("00000000-0000-4000-8000-000000000703")
FINDING_ID = uuid.UUID("00000000-0000-4000-8000-000000000704")
EXTERNAL_IDENTITY_ID = "00000000-0000-4000-8000-000000000705"
EXTERNAL_PARTICIPANT_ID = "00000000-0000-4000-8000-000000000706"
EXTERNAL_GRANT_ID = "00000000-0000-4000-8000-000000000707"
AUDITEE_IDENTITY_ID = "00000000-0000-4000-8000-000000000708"
AUDITEE_PARTICIPANT_ID = "00000000-0000-4000-8000-000000000709"
AUDITEE_GRANT_ID = "00000000-0000-4000-8000-000000000710"
GOVERNANCE_ID = "00000000-0000-4000-8000-000000000711"
RELEASE_EVENT_ID = "00000000-0000-4000-8000-000000000712"

AMO_CODE = "QMSLIVE"
AMO_SLUG = "qmslive"
AUDIT_REF = "QAR-MO-26-990"
FIXTURE_PATH = Path(os.environ.get("E2E_QMS_LIVE_FIXTURE", "/tmp/qms-live-audit-real-e2e.json"))


def _grant_token(*, amo_id: str, grant: QualityAuditAccessGrant) -> str:
    token = _make_access_token(amo_id=amo_id, grant_id=grant.id, expires_at=grant.expires_at)
    grant.token_hash = _hash_token(token)
    return token


def seed() -> None:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=8)
    db = WriteSessionLocal()
    try:
        amo = account_models.AMO(
            id=AMO_ID,
            amo_code=AMO_CODE,
            name="QMS Live Audit Browser Acceptance AMO",
            login_slug=AMO_SLUG,
            country="KE",
            time_zone="Africa/Nairobi",
            is_active=True,
            is_demo=False,
        )
        db.add(amo)
        db.flush()

        audit = quality_models.QMSAudit(
            id=AUDIT_ID,
            amo_id=amo.id,
            domain=QMSDomain.AMO,
            kind=QMSAuditKind.INTERNAL,
            status=QMSAuditStatus.IN_PROGRESS,
            audit_ref=AUDIT_REF,
            reference_family="QAR",
            unit_code="MO",
            ref_year=26,
            ref_sequence=990,
            title="Real browser live audit acceptance",
            scope="Quality management system and controlled operational processes.",
            criteria="Approved QMS manual and applicable regulatory requirements.",
            auditee="Browser Acceptance Auditee",
            auditee_email="auditee@example.com",
            planned_start=date.today(),
            planned_end=date.today() + timedelta(days=1),
            actual_start=date.today(),
            notify_auditors=False,
            notify_auditees=False,
        )
        db.add(audit)
        db.flush()

        checklist_item = quality_models.QualityAuditChecklistItem(
            id=CHECKLIST_ITEM_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            section="Document control",
            checklist_ref="CHK-LIVE-001",
            requirement_ref="QMSM 4.2.3",
            prompt="Verify only the current controlled procedure is available at the sampled point of use.",
            response_status="PENDING",
            objective_evidence=None,
            sort_order=10,
        )
        db.add(checklist_item)
        db.flush()

        db.add(QualityAuditChecklistExecutionGovernance(
            id=GOVERNANCE_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            checklist_item_id=checklist_item.id,
            canonical_response_status="NOT_VERIFIED",
            auditor_notes=None,
            evidence_references=[],
            entity_version=1,
        ))

        finding = quality_models.QMSAuditFinding(
            id=FINDING_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            finding_ref=f"{AUDIT_REF}-F-001",
            finding_type=QMSFindingType.NON_CONFORMITY,
            severity=QMSFindingSeverity.MAJOR,
            level=FindingLevel.LEVEL_2,
            requirement_ref="QMSM 4.2.3",
            description="A superseded controlled procedure was available at a sampled point of use.",
            objective_evidence="Controlled sample compared with the current DMS revision.",
            target_close_date=date.today() + timedelta(days=28),
        )
        db.add(finding)
        db.flush()
        db.add(QualityAuditFindingReleaseEvent(
            id=RELEASE_EVENT_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            finding_id=finding.id,
            action="RELEASED",
            include_objective_evidence=True,
            released_evidence_refs=[],
            reason="Release deterministic browser-acceptance finding to the auditee.",
            actor_user_id=None,
        ))

        external_identity = QualityExternalIdentity(
            id=EXTERNAL_IDENTITY_ID,
            amo_id=amo.id,
            email="external.auditor@example.com",
            display_name="Independent Browser Auditor",
            organisation="External Assurance CI",
            identity_status="ACTIVE",
            assurance_level="EMAIL_LINK",
        )
        db.add(external_identity)
        db.flush()
        external_participant = QualityAuditParticipant(
            id=EXTERNAL_PARTICIPANT_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            participant_type="EXTERNAL_AUDITOR",
            external_identity_id=external_identity.id,
            role="AUDITOR",
            permissions_json=[
                "audit:read_assigned",
                "audit:read_summary",
                "audit:read_progress",
                "audit:checklist_execute",
                "audit:finding_draft",
            ],
            status="INVITED",
            invited_at=now,
            expires_at=expires_at,
        )
        db.add(external_participant)
        db.flush()
        external_grant = QualityAuditAccessGrant(
            id=EXTERNAL_GRANT_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            participant_id=external_participant.id,
            token_hash="pending-external",
            scope_json=list(external_participant.permissions_json),
            expires_at=expires_at,
        )
        db.add(external_grant)
        db.flush()
        external_token = _grant_token(amo_id=amo.id, grant=external_grant)

        auditee_identity = QualityExternalIdentity(
            id=AUDITEE_IDENTITY_ID,
            amo_id=amo.id,
            email="auditee@example.com",
            display_name="Browser Acceptance Auditee",
            organisation="QMS Live Audit Browser Acceptance AMO",
            identity_status="ACTIVE",
            assurance_level="EMAIL_LINK",
        )
        db.add(auditee_identity)
        db.flush()
        auditee_participant = QualityAuditParticipant(
            id=AUDITEE_PARTICIPANT_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            participant_type="AUDITEE_GUEST",
            external_identity_id=auditee_identity.id,
            role="AUDITEE",
            permissions_json=[
                "audit:read_summary",
                "audit:read_progress",
                "audit:read_released_findings",
                "audit:acknowledge",
            ],
            status="INVITED",
            invited_at=now,
            expires_at=expires_at,
        )
        db.add(auditee_participant)
        db.flush()
        auditee_grant = QualityAuditAccessGrant(
            id=AUDITEE_GRANT_ID,
            amo_id=amo.id,
            audit_id=audit.id,
            participant_id=auditee_participant.id,
            token_hash="pending-auditee",
            scope_json=list(auditee_participant.permissions_json),
            expires_at=expires_at,
        )
        db.add(auditee_grant)
        db.flush()
        auditee_token = _grant_token(amo_id=amo.id, grant=auditee_grant)

        db.commit()

        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE_PATH.write_text(json.dumps({
            "amo_id": AMO_ID,
            "amo_slug": AMO_SLUG,
            "audit_id": str(AUDIT_ID),
            "audit_ref": AUDIT_REF,
            "checklist_item_id": str(CHECKLIST_ITEM_ID),
            "finding_id": str(FINDING_ID),
            "external_auditor_token": external_token,
            "auditee_token": auditee_token,
        }, indent=2), encoding="utf-8")
        print(f"Seeded real QMS Live Audit browser fixture at {FIXTURE_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
