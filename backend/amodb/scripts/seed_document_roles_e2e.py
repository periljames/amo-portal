"""Seed deterministic DMS role-separation fixtures for authenticated browser CI.

Run only after ``seed_document_governance_e2e.py`` against the disposable
Document Control Governance CI database. The fixture deliberately uses normal
portal accounts plus confirmed governed responsibilities so browser/API tests
prove that workflow authority comes from the document model, not hidden buttons.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.doc_control import domain_models, governance_models  # noqa: E402
from amodb.apps.manuals import models as manual_models  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402
from amodb.security import get_password_hash  # noqa: E402

from amodb.scripts.seed_document_governance_e2e import (  # noqa: E402
    AMO_ID,
    DEPARTMENT_ID,
    MANUAL_ID,
    REVISION_ID,
)

ROLE_PASSWORD = "DmsRoles!2026-Local"
READER_USER_ID = "00000000-0000-4000-8000-000000000496"
TECH_REVIEWER_USER_ID = "00000000-0000-4000-8000-000000000497"
QUALITY_REVIEWER_USER_ID = "00000000-0000-4000-8000-000000000498"
MANAGEMENT_APPROVER_USER_ID = "00000000-0000-4000-8000-000000000499"
CANDIDATE_REVISION_ID = "00000000-0000-4000-8000-000000000500"
WORKFLOW_ID = "00000000-0000-4000-8000-000000000501"
TECH_ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000502"
QUALITY_ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000503"
APPROVER_ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000504"
CHANGE_ID = "00000000-0000-4000-8000-000000000505"

READER_EMAIL = "dms-reader@example.com"
TECH_REVIEWER_EMAIL = "dms-tech-reviewer@example.com"
QUALITY_REVIEWER_EMAIL = "dms-quality-reviewer@example.com"
MANAGEMENT_APPROVER_EMAIL = "dms-management-approver@example.com"


def _user(
    *,
    user_id: str,
    email: str,
    staff_code: str,
    first_name: str,
    last_name: str,
    title: str,
) -> account_models.User:
    return account_models.User(
        id=user_id,
        amo_id=AMO_ID,
        department_id=DEPARTMENT_ID,
        staff_code=staff_code,
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=f"{first_name} {last_name}",
        role=account_models.AccountRole.TECHNICIAN if user_id != READER_USER_ID else account_models.AccountRole.VIEW_ONLY,
        position_title=title,
        hashed_password=get_password_hash(ROLE_PASSWORD),
        is_active=True,
        is_amo_admin=False,
        is_superuser=False,
        is_auditor=False,
        is_system_account=False,
        must_change_password=False,
        password_changed_at=datetime.now(timezone.utc),
    )


def _assignment(
    *,
    assignment_id: str,
    responsibility_type: str,
    assignee_user_id: str,
) -> governance_models.DocumentResponsibilityAssignment:
    return governance_models.DocumentResponsibilityAssignment(
        id=assignment_id,
        tenant_id=AMO_ID,
        manual_id=MANUAL_ID,
        revision_id=CANDIDATE_REVISION_ID,
        responsibility_type=responsibility_type,
        assignee_type="USER",
        assignee_user_id=assignee_user_id,
        is_primary=True,
        effective_from=date.today(),
        assignment_source="MANUAL",
        confidence_percent=100,
        confirmation_status="CONFIRMED",
        provenance_json={"source": "document_roles_ci_seed", "purpose": "deterministic_role_matrix"},
        created_by_user_id=assignee_user_id,
        confirmed_by_user_id=assignee_user_id,
        confirmed_at=datetime.now(timezone.utc),
    )


def seed() -> None:
    db = WriteSessionLocal()
    try:
        if db.query(account_models.User).filter(account_models.User.id == READER_USER_ID).first():
            raise RuntimeError("DMS role fixture already exists; use a fresh disposable database")

        published = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.id == REVISION_ID).one()
        manual = db.query(manual_models.Manual).filter(manual_models.Manual.id == MANUAL_ID).one()

        reader = _user(
            user_id=READER_USER_ID,
            email=READER_EMAIL,
            staff_code="DMS-CI-RDR",
            first_name="Ordinary",
            last_name="Reader",
            title="Controlled Information Reader",
        )
        technical = _user(
            user_id=TECH_REVIEWER_USER_ID,
            email=TECH_REVIEWER_EMAIL,
            staff_code="DMS-CI-TECH",
            first_name="Technical",
            last_name="Reviewer",
            title="Technical Reviewer",
        )
        quality = _user(
            user_id=QUALITY_REVIEWER_USER_ID,
            email=QUALITY_REVIEWER_EMAIL,
            staff_code="DMS-CI-QREV",
            first_name="Quality",
            last_name="Reviewer",
            title="Quality Reviewer",
        )
        management = _user(
            user_id=MANAGEMENT_APPROVER_USER_ID,
            email=MANAGEMENT_APPROVER_EMAIL,
            staff_code="DMS-CI-MGMT",
            first_name="Management",
            last_name="Approver",
            title="Accountable Management Approver",
        )
        db.add_all([reader, technical, quality, management])
        db.flush()

        # Use real PDF bytes already created by the base seed. The candidate remains
        # mutable and explicitly in department review; publication continues to
        # point to REVISION_ID until the actual workflow publishes this revision.
        candidate = manual_models.ManualRevision(
            id=CANDIDATE_REVISION_ID,
            manual_id=manual.id,
            rev_number="2",
            issue_number="1",
            effective_date=None,
            status_enum=manual_models.ManualRevisionStatus.DEPARTMENT_REVIEW,
            created_by=technical.id,
            created_at=datetime.now(timezone.utc),
            immutable_locked=False,
            source_type_enum=published.source_type_enum,
            source_filename="document-governance-role-review-candidate.pdf",
            source_mime_type=published.source_mime_type,
            source_storage_path=published.source_storage_path,
            source_sha256=published.source_sha256,
            source_page_count=published.source_page_count,
            notes="Deterministic candidate revision for assignment-aware workflow acceptance.",
        )
        db.add(candidate)
        db.flush()

        workflow = domain_models.DocumentWorkflowInstance(
            id=WORKFLOW_ID,
            tenant_id=AMO_ID,
            manual_id=manual.id,
            revision_id=candidate.id,
            state="TECHNICAL_REVIEW",
            requires_authority=False,
            training_impact_required=False,
            training_readiness_status="NOT_REQUIRED",
            qms_readiness_status="NOT_REQUIRED",
            distribution_readiness_status="NOT_REQUIRED",
            version=1,
            created_by_user_id=technical.id,
        )
        db.add(workflow)
        db.flush()

        db.add_all([
            _assignment(
                assignment_id=TECH_ASSIGNMENT_ID,
                responsibility_type="TECHNICAL_REVIEWER",
                assignee_user_id=technical.id,
            ),
            _assignment(
                assignment_id=QUALITY_ASSIGNMENT_ID,
                responsibility_type="QUALITY_REVIEWER",
                assignee_user_id=quality.id,
            ),
            _assignment(
                assignment_id=APPROVER_ASSIGNMENT_ID,
                responsibility_type="APPROVER",
                assignee_user_id=management.id,
            ),
            domain_models.DocumentChangeRequest(
                id=CHANGE_ID,
                tenant_id=AMO_ID,
                manual_id=manual.id,
                revision_id=candidate.id,
                source_module="DOCUMENT_CONTROL",
                source_entity_type="manual_revision",
                source_entity_id=candidate.id,
                title="Role-separated controlled revision",
                description="Candidate revision used to prove technical, Quality, management and reader isolation.",
                priority="NORMAL",
                status="IMPLEMENTING",
                proposer_user_id=technical.id,
                owner_user_id=technical.id,
                impact_json={"ci_fixture": True},
                training_impact_required=False,
                qms_blocking=False,
            ),
        ])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"E2E_DMS_READER_EMAIL={READER_EMAIL}")
    print(f"E2E_DMS_TECH_REVIEWER_EMAIL={TECH_REVIEWER_EMAIL}")
    print(f"E2E_DMS_QUALITY_REVIEWER_EMAIL={QUALITY_REVIEWER_EMAIL}")
    print(f"E2E_DMS_MANAGEMENT_APPROVER_EMAIL={MANAGEMENT_APPROVER_EMAIL}")
    print(f"E2E_DMS_ROLE_PASSWORD={ROLE_PASSWORD}")
    print(f"E2E_DMS_CANDIDATE_REVISION_ID={CANDIDATE_REVISION_ID}")
    print(f"E2E_DMS_WORKFLOW_ID={WORKFLOW_ID}")


if __name__ == "__main__":
    seed()
