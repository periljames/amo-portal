"""Seed deterministic real QMS Live Audit browser-acceptance fixtures.

This script is only intended for the disposable PostgreSQL service created by
QMS Live Audit CI. It uses the production ORM, password hashing, signed external
access-grant format and tenant-scoped audit models so Playwright can exercise
real browser -> production preview -> FastAPI -> PostgreSQL journeys without
route mocks or production credentials.
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
from amodb.security import get_password_hash  # noqa: E402

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

QUALITY_DEPARTMENT_ID = "00000000-0000-4000-8000-000000000713"
REALTIME_USER_A_ID = "00000000-0000-4000-8000-000000000714"
REALTIME_USER_B_ID = "00000000-0000-4000-8000-000000000715"
REALTIME_AUDIT_ID = uuid.UUID("00000000-0000-4000-8000-000000000716")
REALTIME_CHECKLIST_ITEM_ID = uuid.UUID("00000000-0000-4000-8000-000000000717")
REALTIME_GOVERNANCE_ID = "00000000-0000-4000-8000-000000000718"
QUALITY_MODULE_SUBSCRIPTION_ID = "00000000-0000-4000-8000-000000000719"

AMO_CODE = "QMSLIVE"
AMO_SLUG = "qmslive"
AUDIT_REF = "QAR-MO-26-990"
REALTIME_AUDIT_REF = "QAR-MO-26-991"
REALTIME_USER_A_EMAIL = "qms-live-a@example.com"
REALTIME_USER_B_EMAIL = "qms-live-b@example.com"
REALTIME_PASSWORD = "QmsLive!2026-Local"
FIXTURE_PATH = Path(os.environ.get("E2E_QMS_LIVE_FIXTURE", "/tmp/qms-live-audit-real-e2e.json"))


def _grant_token(*, amo_id: str, grant: QualityAuditAccessGrant) -> str:
    token = _make_access_token(amo_id=amo_id, grant_id=grant.id, expires_at=grant.expires_at)
    grant.token_hash = _hash_token(token)
    return token


def _quality_user(
    *,
    user_id: str,
    amo_id: str,
    department_id: str,
    email: str,
    first_name: str,
    last_name: str,
    staff_code: str,
) -> account_models.User:
    return account_models.User(
        id=user_id,
        amo_id=amo_id,
        department_id=department_id,
        staff_code=staff_code,
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=f"{first_name} {last_name}",
        role=account_models.AccountRole.QUALITY_MANAGER,
        position_title="Quality Manager",
        hashed_password=get_password_hash(REALTIME_PASSWORD),
        is_active=True,
        is_amo_admin=False,
        is_superuser=False,
        is_auditor=True,
        is_system_account=False,
        must_change_password=False,
        password_changed_at=datetime.now(timezone.utc),
    )


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

        department = account_models.Department(
            id=QUALITY_DEPARTMENT_ID,
            amo_id=amo.id,
            code="quality",
            name="Quality",
            default_route=f"/maintenance/{AMO_SLUG}/quality",
            is_active=True,
            sort_order=10,
        )
        db.add(department)
        db.flush()

        user_a = _quality_user(
            user_id=REALTIME_USER_A_ID,
            amo_id=amo.id,
            department_id=department.id,
            email=REALTIME_USER_A_EMAIL,
            first_name="Quality",
            last_name="Alpha",
            staff_code="QMS-LIVE-A",
        )
        user_b = _quality_user(
            user_id=REALTIME_USER_B_ID,
            amo_id=amo.id,
            department_id=department.id,
            email=REALTIME_USER_B_EMAIL,
            first_name="Quality",
            last_name="Bravo",
            staff_code="QMS-LIVE-B",
        )
        db.add_all([user_a, user_b])
        db.flush()

        # A direct tenant module subscription is sufficient for module gating in
        # this disposable acceptance tenant and avoids inventing a commercial SKU.
        db.add(account_models.ModuleSubscription(
            id=QUALITY_MODULE_SUBSCRIPTION_ID,
            amo_id=amo.id,
            module_code="quality",
            status=account_models.ModuleSubscriptionStatus.ENABLED,
            effective_from=now - timedelta(minutes=5),
            effective_to=now + timedelta(days=1),
            plan_code="CI-QMS-LIVE",
            metadata_json=json.dumps({"source": "qms_live_audit_real_browser_ci"}),
        ))

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
            lead_auditor_user_id=user_a.id,
            observer_auditor_user_id=user_b.id,
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

        realtime_audit = quality_models.QMSAudit(
            id=REALTIME_AUDIT_ID,
            amo_id=amo.id,
            domain=QMSDomain.AMO,
            kind=QMSAuditKind.INTERNAL,
            status=QMSAuditStatus.IN_PROGRESS,
            audit_ref=REALTIME_AUDIT_REF,
            reference_family="QAR",
            unit_code="MO",
            ref_year=26,
            ref_sequence=991,
            title="Concurrent realtime browser acceptance",
            scope="Two authenticated Quality users collaborating on the same live audit.",
            criteria="QMS live-audit realtime event propagation contract.",
            auditee="Internal realtime fixture",
            planned_start=date.today(),
            planned_end=date.today() + timedelta(days=1),
            actual_start=date.today(),
            lead_auditor_user_id=user_a.id,
            observer_auditor_user_id=user_b.id,
            notify_auditors=False,
            notify_auditees=False,
        )
        db.add(realtime_audit)
        db.flush()
        realtime_item = quality_models.QualityAuditChecklistItem(
            id=REALTIME_CHECKLIST_ITEM_ID,
            amo_id=amo.id,
            audit_id=realtime_audit.id,
            section="Realtime collaboration",
            checklist_ref="CHK-RT-001",
            requirement_ref="QMS-RT-001",
            prompt="Verify concurrent authenticated browsers receive committed fieldwork updates without manual refresh.",
            response_status="PENDING",
            objective_evidence=None,
            sort_order=10,
        )
        db.add(realtime_item)
        db.flush()
        db.add(QualityAuditChecklistExecutionGovernance(
            id=REALTIME_GOVERNANCE_ID,
            amo_id=amo.id,
            audit_id=realtime_audit.id,
            checklist_item_id=realtime_item.id,
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
            "realtime_audit_id": str(REALTIME_AUDIT_ID),
            "realtime_audit_ref": REALTIME_AUDIT_REF,
            "realtime_checklist_item_id": str(REALTIME_CHECKLIST_ITEM_ID),
            "realtime_user_a_id": REALTIME_USER_A_ID,
            "realtime_user_a_email": REALTIME_USER_A_EMAIL,
            "realtime_user_b_id": REALTIME_USER_B_ID,
            "realtime_user_b_email": REALTIME_USER_B_EMAIL,
            "realtime_password": REALTIME_PASSWORD,
        }, indent=2), encoding="utf-8")
        print(f"Seeded real QMS Live Audit browser fixture at {FIXTURE_PATH}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
