"""Seed a deterministic governed Training OS fixture for live browser CI.

Runs only against the disposable PostgreSQL service created by Training CI.  The
fixture deliberately uses the real account, Training, approval, curriculum, facility,
technical-authorisation, examination and session-governance tables so Playwright can
prove browser -> FastAPI -> PostgreSQL behavior without production credentials.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import json
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.training import governance_models as gov  # noqa: E402
from amodb.apps.training import models as training  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402
from amodb.security import get_password_hash  # noqa: E402

AMO_ID = "00000000-0000-4000-8100-000000000001"
DEPARTMENT_ID = "00000000-0000-4000-8100-000000000002"
ADMIN_ID = "00000000-0000-4000-8100-000000000003"
COURSE_ID = "00000000-0000-4000-8100-000000000004"
EVENT_ID = "00000000-0000-4000-8100-000000000005"
PARTICIPANT_ID = "00000000-0000-4000-8100-000000000006"
AUTHORITY_ID = "00000000-0000-4000-8100-000000000007"
APPROVAL_ID = "00000000-0000-4000-8100-000000000008"
COURSE_REVISION_ID = "00000000-0000-4000-8100-000000000009"
MODULE_THEORY_ID = "00000000-0000-4000-8100-000000000010"
MODULE_PRACTICAL_ID = "00000000-0000-4000-8100-000000000011"
PRACTICAL_TASK_ID = "00000000-0000-4000-8100-000000000012"
FACILITY_ID = "00000000-0000-4000-8100-000000000013"
INSTRUCTOR_AUTH_ID = "00000000-0000-4000-8100-000000000014"
ASSESSOR_AUTH_ID = "00000000-0000-4000-8100-000000000015"
SESSION_GOVERNANCE_ID = "00000000-0000-4000-8100-000000000016"
MATERIAL_ID = "00000000-0000-4000-8100-000000000017"
QUESTION_ID = "00000000-0000-4000-8100-000000000018"
QUESTION_REVISION_ID = "00000000-0000-4000-8100-000000000019"
BLUEPRINT_ID = "00000000-0000-4000-8100-000000000020"
TRAINING_MODULE_SUBSCRIPTION_ID = "00000000-0000-4000-8100-000000000021"

AMO_CODE = "TRNGATE"
AMO_SLUG = "trngate"
ADMIN_EMAIL = "training-gate@example.com"
ADMIN_PASSWORD = "TrainingGate!2026-Local"
TODAY = date.today()


def seed() -> None:
    db = WriteSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        amo = account_models.AMO(
            id=AMO_ID,
            amo_code=AMO_CODE,
            name="Training Governance CI AMO",
            login_slug=AMO_SLUG,
            country="KE",
            time_zone="Africa/Nairobi",
            is_active=True,
            is_demo=False,
        )
        db.add(amo)
        db.flush()

        department = account_models.Department(
            id=DEPARTMENT_ID,
            amo_id=AMO_ID,
            code="training",
            name="Training",
            default_route=f"/maintenance/{AMO_SLUG}/training/competence",
            is_active=True,
            sort_order=20,
        )
        db.add(department)
        db.flush()

        admin = account_models.User(
            id=ADMIN_ID,
            amo_id=AMO_ID,
            department_id=DEPARTMENT_ID,
            staff_code="TRN-CI-001",
            email=ADMIN_EMAIL,
            first_name="Training",
            last_name="Controller",
            full_name="Training Controller CI",
            role=account_models.AccountRole.AMO_ADMIN,
            position_title="Training Controller",
            hashed_password=get_password_hash(ADMIN_PASSWORD),
            is_active=True,
            is_amo_admin=True,
            is_superuser=False,
            is_auditor=False,
            is_system_account=False,
            must_change_password=False,
            password_changed_at=now,
        )
        db.add(admin)
        db.flush()

        # The canonical Training router is protected by require_module("training").
        # The disposable live-browser tenant therefore needs the same explicit
        # tenant module subscription as a real enabled tenant.  This keeps the CI
        # journey behind production entitlement checks instead of bypassing them.
        db.add(account_models.ModuleSubscription(
            id=TRAINING_MODULE_SUBSCRIPTION_ID,
            amo_id=AMO_ID,
            module_code="training",
            status=account_models.ModuleSubscriptionStatus.ENABLED,
            effective_from=now - timedelta(minutes=5),
            effective_to=now + timedelta(days=1),
            plan_code="CI-TRAINING-GOVERNANCE",
            metadata_json=json.dumps({"source": "training_governance_live_browser_ci"}),
        ))
        db.flush()

        course = training.TrainingCourse(
            id=COURSE_ID,
            amo_id=AMO_ID,
            course_id="TRN-E2E",
            course_name="Governed Training Browser Acceptance",
            category=training.TrainingCourseCategory.INTERNAL_TECHNICAL,
            kind=training.TrainingKind.INITIAL,
            delivery_method=training.TrainingDeliveryMethod.MIXED,
            assessment_required=True,
            attendance_required=True,
            evidence_required=True,
            created_by_user_id=ADMIN_ID,
        )
        db.add(course)
        db.flush()

        event = training.TrainingEvent(
            id=EVENT_ID,
            amo_id=AMO_ID,
            course_id=COURSE_ID,
            title="Governed Training Browser Acceptance",
            starts_on=TODAY,
            ends_on=TODAY,
            status=training.TrainingEventStatus.PLANNED,
            created_by_user_id=ADMIN_ID,
        )
        db.add(event)
        db.flush()
        db.add(training.TrainingEventParticipant(
            id=PARTICIPANT_ID,
            amo_id=AMO_ID,
            event_id=EVENT_ID,
            user_id=ADMIN_ID,
            status=training.TrainingParticipantStatus.CONFIRMED,
        ))

        db.add(gov.TrainingAuthority(
            id=AUTHORITY_ID,
            amo_id=AMO_ID,
            code="KCAA-CI",
            name="KCAA CI Authority",
            jurisdiction="KE",
            status="ACTIVE",
            created_by_user_id=ADMIN_ID,
        ))
        db.flush()
        db.add(gov.TrainingApproval(
            id=APPROVAL_ID,
            amo_id=AMO_ID,
            authority_id=AUTHORITY_ID,
            approval_number="ATO-CI-001",
            approval_type="TRAINING_ORGANISATION",
            title="Training Governance CI Approval",
            effective_date=TODAY,
            status="ACTIVE",
            supporting_dms_document_id="ci-controlled-approval",
            supporting_dms_revision_id="ci-controlled-approval-rev-1",
            verified_by_user_id=ADMIN_ID,
            verified_at=now,
            created_by_user_id=ADMIN_ID,
        ))
        db.flush()

        revision = gov.TrainingCourseRevision(
            id=COURSE_REVISION_ID,
            amo_id=AMO_ID,
            course_id=COURSE_ID,
            revision_no=1,
            title="Governed Training Browser Acceptance Rev 1",
            status="ACTIVE",
            authority_id=AUTHORITY_ID,
            course_approval_id=APPROVAL_ID,
            effective_from=TODAY,
            theory_hours=Decimal("1.00"),
            practical_hours=Decimal("1.00"),
            total_hours=Decimal("2.00"),
            delivery_methods=["CLASSROOM", "PRACTICAL"],
            completion_rules={"course_approval_required": True},
            assessment_blueprint={"required": True},
            instructor_requirements={"aircraft": "DHC8"},
            facility_requirements={"approval_required": True},
            certificate_rules={"required": True},
            source_document_id="ci-training-manual",
            source_revision_id="ci-training-manual-rev-1",
            source_section="Training governance CI",
            created_by_user_id=ADMIN_ID,
            approved_by_user_id=ADMIN_ID,
        )
        db.add(revision)
        db.flush()

        db.add_all([
            gov.TrainingCourseModule(
                id=MODULE_THEORY_ID,
                amo_id=AMO_ID,
                course_revision_id=COURSE_REVISION_ID,
                sequence_no=1,
                code="THY",
                subject="Controlled theory module",
                theory_hours=Decimal("1.00"),
                practical_hours=Decimal("0.00"),
                delivery_method="CLASSROOM",
                required=True,
            ),
            gov.TrainingCourseModule(
                id=MODULE_PRACTICAL_ID,
                amo_id=AMO_ID,
                course_revision_id=COURSE_REVISION_ID,
                sequence_no=2,
                code="PRA",
                subject="Controlled practical module",
                theory_hours=Decimal("0.00"),
                practical_hours=Decimal("1.00"),
                delivery_method="PRACTICAL",
                required=True,
            ),
        ])
        db.flush()

        db.add(gov.TrainingPracticalTask(
            id=PRACTICAL_TASK_ID,
            amo_id=AMO_ID,
            course_revision_id=COURSE_REVISION_ID,
            module_id=MODULE_PRACTICAL_ID,
            code="PRA-001",
            title="Demonstrate controlled practical task",
            competency_reference="CI-COMP-001",
            evidence_requirements=["assessor decision"],
            required=True,
        ))
        db.add(gov.TrainingMaterialRevision(
            id=MATERIAL_ID,
            amo_id=AMO_ID,
            course_revision_id=COURSE_REVISION_ID,
            material_code="TRN-CI-MAT",
            title="Controlled Training CI Material",
            revision_no=1,
            material_type="LESSON_PLAN",
            dms_document_id="ci-training-material",
            dms_revision_id="ci-training-material-rev-1",
            effective_from=TODAY,
            status="ACTIVE",
            required=True,
            approved_by_user_id=ADMIN_ID,
        ))
        db.add(gov.TrainingFacility(
            id=FACILITY_ID,
            amo_id=AMO_ID,
            code="CI-CLASSROOM",
            name="Training Governance CI Classroom",
            facility_type="CLASSROOM",
            approval_id=APPROVAL_ID,
            authority_id=AUTHORITY_ID,
            classroom_capacity=20,
            practical_capacity=10,
            technical_library_access=True,
            evidence_json=[{"type": "ci_fixture", "reference": "FAC-CI-001"}],
            status="ACTIVE",
        ))
        db.flush()

        db.add_all([
            gov.TrainingTechnicalAuthorisation(
                id=INSTRUCTOR_AUTH_ID,
                amo_id=AMO_ID,
                user_id=ADMIN_ID,
                privilege_type="INSTRUCTOR",
                authority_id=AUTHORITY_ID,
                approval_id=APPROVAL_ID,
                aircraft="DHC8",
                course_ids=[COURSE_ID],
                theoretical_privilege=True,
                practical_privilege=True,
                issue_date=TODAY,
                status="ACTIVE",
                evidence_json=[{"type": "ci_fixture", "reference": "INST-CI-001"}],
                issued_by_user_id=ADMIN_ID,
                approved_by_user_id=ADMIN_ID,
            ),
            gov.TrainingTechnicalAuthorisation(
                id=ASSESSOR_AUTH_ID,
                amo_id=AMO_ID,
                user_id=ADMIN_ID,
                privilege_type="ASSESSOR",
                authority_id=AUTHORITY_ID,
                approval_id=APPROVAL_ID,
                aircraft="DHC8",
                course_ids=[COURSE_ID],
                practical_privilege=True,
                issue_date=TODAY,
                status="ACTIVE",
                evidence_json=[{"type": "ci_fixture", "reference": "ASSR-CI-001"}],
                issued_by_user_id=ADMIN_ID,
                approved_by_user_id=ADMIN_ID,
            ),
        ])
        db.flush()

        db.add(gov.TrainingSessionGovernance(
            id=SESSION_GOVERNANCE_ID,
            amo_id=AMO_ID,
            event_id=EVENT_ID,
            course_revision_id=COURSE_REVISION_ID,
            facility_id=FACILITY_ID,
            instructor_authorisation_ids=[INSTRUCTOR_AUTH_ID],
            assessor_authorisation_ids=[ASSESSOR_AUTH_ID],
            status="PLANNED",
        ))

        db.add(gov.TrainingQuestionBankItem(
            id=QUESTION_ID,
            amo_id=AMO_ID,
            question_code="CI-Q-001",
            course_revision_id=COURSE_REVISION_ID,
            module_id=MODULE_THEORY_ID,
            status="ACTIVE",
            exposure_count=0,
            created_by_user_id=ADMIN_ID,
        ))
        db.flush()
        db.add(gov.TrainingQuestionRevision(
            id=QUESTION_REVISION_ID,
            amo_id=AMO_ID,
            question_id=QUESTION_ID,
            revision_no=1,
            prompt="Which option is the controlled CI answer?",
            options_json=["A", "B"],
            answer_key_json={"correct_option": "A"},
            explanation="Private CI answer explanation",
            marks=Decimal("1.00"),
            source_document_id="ci-training-manual",
            source_revision_id="ci-training-manual-rev-1",
            author_user_id=ADMIN_ID,
            reviewer_user_id=ADMIN_ID,
            approved_by_user_id=ADMIN_ID,
            effective_from=TODAY,
            status="ACTIVE",
        ))
        db.add(gov.TrainingExamBlueprint(
            id=BLUEPRINT_ID,
            amo_id=AMO_ID,
            course_revision_id=COURSE_REVISION_ID,
            revision_no=1,
            title="Training Governance CI Exam",
            selection_rules={"question_count": 1},
            result_rules={"pass_mark": 75, "max_attempts": 2, "cooldown_hours": 0},
            security_rules={"proctor_required": False},
            status="ACTIVE",
            approved_by_user_id=ADMIN_ID,
            effective_from=TODAY,
        ))

        db.commit()
        print("Seeded governed Training browser fixture", AMO_SLUG, EVENT_ID)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
