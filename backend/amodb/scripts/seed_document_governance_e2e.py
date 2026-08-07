"""Seed an ephemeral AMO and governed publications for browser acceptance CI.

This script is intentionally deterministic and is only used against the disposable
PostgreSQL service created by Document Control Governance CI. It exercises the
same password login, tenant scoping, governed library, hierarchy, external-data
currency, physical custody and Publications reader routes used in production
without depending on production credentials or data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys

# Executing this file directly sets sys.path[0] to backend/amodb/scripts rather
# than backend. Make the backend package root explicit so the deterministic CI
# seed works regardless of the caller's working directory or PYTHONPATH.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Importing the application registers the full model graph before we seed rows.
from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.accounts import models as account_models  # noqa: E402
from amodb.apps.doc_control import domain_models, governance_models, knowledge_models  # noqa: E402
from amodb.apps.manuals import models as manual_models  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402
from amodb.security import get_password_hash  # noqa: E402

DEPARTMENT_ID = "00000000-0000-4000-8000-000000000476"
AMO_ID = "00000000-0000-4000-8000-000000000477"
USER_ID = "00000000-0000-4000-8000-000000000478"
TENANT_ID = "00000000-0000-4000-8000-000000000479"
MANUAL_ID = "00000000-0000-4000-8000-000000000480"
REVISION_ID = "00000000-0000-4000-8000-000000000481"
SECTION_ID = "00000000-0000-4000-8000-000000000482"
BLOCK_ID = "00000000-0000-4000-8000-000000000483"
ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000484"
ROOT_NODE_ID = "00000000-0000-4000-8000-000000000485"
MANUAL_NODE_ID = "00000000-0000-4000-8000-000000000486"
POLICY_MANUAL_ID = "00000000-0000-4000-8000-000000000487"
POLICY_REVISION_ID = "00000000-0000-4000-8000-000000000488"
POLICY_NODE_ID = "00000000-0000-4000-8000-000000000489"
EXTERNAL_MANUAL_ID = "00000000-0000-4000-8000-000000000490"
EXTERNAL_REVISION_ID = "00000000-0000-4000-8000-000000000491"
EXTERNAL_NODE_ID = "00000000-0000-4000-8000-000000000492"
EXTERNAL_PROFILE_ID = "00000000-0000-4000-8000-000000000493"
EXTERNAL_SOURCE_ID = "00000000-0000-4000-8000-000000000494"
EXTERNAL_RECEIPT_ID = "00000000-0000-4000-8000-000000000495"

AMO_CODE = "DMSGATE"
AMO_SLUG = "dmsgate"
# example.com is reserved by RFC 2606 for documentation/testing and passes the
# application's standards-compliant email validator unlike the invalid TLD.
ADMIN_EMAIL = "dms-gate@example.com"
ADMIN_PASSWORD = "DmsGate!2026-Local"


def _published_revision(
    *,
    revision_id: str,
    manual_id: str,
    user_id: str,
    revision_number: str,
    issue_number: str,
) -> manual_models.ManualRevision:
    return manual_models.ManualRevision(
        id=revision_id,
        manual_id=manual_id,
        rev_number=revision_number,
        issue_number=issue_number,
        effective_date=date.today(),
        status_enum=manual_models.ManualRevisionStatus.PUBLISHED,
        created_by=user_id,
        created_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        immutable_locked=True,
    )


def seed() -> None:
    db = WriteSessionLocal()
    try:
        # This runs against a newly migrated disposable database. Explicit IDs make
        # the browser route stable and make accidental duplicate execution obvious.
        amo = account_models.AMO(
            id=AMO_ID,
            amo_code=AMO_CODE,
            name="Document Governance CI AMO",
            login_slug=AMO_SLUG,
            country="KE",
            time_zone="Africa/Nairobi",
            is_active=True,
            is_demo=False,
        )
        db.add(amo)
        db.flush()

        # The route boundary intentionally requires a normal tenant user to have
        # an assigned department unless an Admin Profile session is actively
        # elevated. Seed a real Document Control department so browser acceptance
        # proves the production access path rather than bypassing that guard.
        department = account_models.Department(
            id=DEPARTMENT_ID,
            amo_id=amo.id,
            code="document-control",
            name="Document Control",
            default_route=f"/maintenance/{AMO_SLUG}/document-control",
            is_active=True,
            sort_order=40,
        )
        db.add(department)
        db.flush()

        user = account_models.User(
            id=USER_ID,
            amo_id=amo.id,
            department_id=department.id,
            staff_code="DMS-CI-001",
            email=ADMIN_EMAIL,
            first_name="Document",
            last_name="Controller",
            full_name="Document Controller CI",
            role=account_models.AccountRole.AMO_ADMIN,
            position_title="AMO Administrator",
            hashed_password=get_password_hash(ADMIN_PASSWORD),
            is_active=True,
            is_amo_admin=True,
            is_superuser=False,
            is_auditor=False,
            is_system_account=False,
            must_change_password=False,
            password_changed_at=datetime.now(timezone.utc),
        )
        db.add(user)

        tenant = manual_models.Tenant(
            id=TENANT_ID,
            amo_id=amo.id,
            slug=AMO_SLUG,
            name="Document Governance CI",
            settings_json={"ack_due_days": 10},
        )
        db.add(tenant)
        db.flush()

        manual = manual_models.Manual(
            id=MANUAL_ID,
            tenant_id=tenant.id,
            code="DMS-CI-MOM",
            title="Document Governance Browser Acceptance Manual",
            manual_type="MOM",
            owner_role="DOCUMENT_CONTROL",
            status="ACTIVE",
        )
        db.add(manual)
        db.flush()

        source_sha = hashlib.sha256(b"amo-portal-document-governance-browser-gate-v1").hexdigest()
        revision = _published_revision(
            revision_id=REVISION_ID,
            manual_id=manual.id,
            user_id=user.id,
            revision_number="1",
            issue_number="1",
        )
        # Mark the authoritative revision as PDF so the browser exercises the
        # hardened PDF reader. With no source file, the backend deterministically
        # renders the controlled section/block content into a PDF response.
        revision.source_type_enum = manual_models.ManualSourceType.PDF
        revision.source_filename = "document-governance-browser-gate.pdf"
        revision.source_mime_type = "application/pdf"
        revision.source_sha256 = source_sha
        revision.source_page_count = 1
        db.add(revision)
        db.flush()
        manual.current_published_rev_id = revision.id

        section = manual_models.ManualSection(
            id=SECTION_ID,
            revision_id=revision.id,
            order_index=1,
            heading="Controlled document governance acceptance",
            anchor_slug="controlled-document-governance-acceptance",
            level=1,
            metadata_json={"source": "ci_seed"},
        )
        db.add(section)
        db.flush()

        text = (
            "This controlled publication is generated only for the disposable "
            "Document Control Governance CI environment. It verifies authenticated "
            "tenant access, governed document routing and authoritative PDF rendering."
        )
        db.add(
            manual_models.ManualBlock(
                id=BLOCK_ID,
                section_id=section.id,
                order_index=1,
                block_type="paragraph",
                html_sanitized=f"<p>{text}</p>",
                text_plain=text,
                change_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )

        # Seed real hierarchy nodes so category filtering and the full-tree route
        # prove governed data, not merely the presence of navigation buttons.
        root_node = knowledge_models.DocumentationNode(
            id=ROOT_NODE_ID,
            tenant_id=amo.id,
            node_type="ROOT",
            code="DMS-CI",
            normalized_code="DMS-CI",
            title="Document Governance CI Library",
            path="DMS-CI",
            depth=0,
            order_index=0,
            status="ACTIVE",
            created_by_user_id=user.id,
        )
        db.add(root_node)
        db.flush()
        db.add(
            knowledge_models.DocumentationNode(
                id=MANUAL_NODE_ID,
                tenant_id=amo.id,
                parent_id=root_node.id,
                manual_id=manual.id,
                node_type="MANUAL",
                code=manual.code,
                normalized_code=manual.code.upper(),
                title=manual.title,
                path=f"DMS-CI/{manual.code}",
                depth=1,
                order_index=10,
                status="ACTIVE",
                created_by_user_id=user.id,
            )
        )

        policy = manual_models.Manual(
            id=POLICY_MANUAL_ID,
            tenant_id=tenant.id,
            code="DMS-CI-POL-001",
            title="Controlled Information Policy",
            manual_type="POLICY",
            owner_role="DOCUMENT_CONTROL",
            status="ACTIVE",
        )
        db.add(policy)
        db.flush()
        policy_revision = _published_revision(
            revision_id=POLICY_REVISION_ID,
            manual_id=policy.id,
            user_id=user.id,
            revision_number="1",
            issue_number="1",
        )
        db.add(policy_revision)
        db.flush()
        policy.current_published_rev_id = policy_revision.id
        db.add(
            knowledge_models.DocumentationNode(
                id=POLICY_NODE_ID,
                tenant_id=amo.id,
                parent_id=root_node.id,
                manual_id=policy.id,
                node_type="POLICY",
                code=policy.code,
                normalized_code=policy.code.upper(),
                title=policy.title,
                path=f"DMS-CI/{policy.code}",
                depth=1,
                order_index=20,
                status="ACTIVE",
                created_by_user_id=user.id,
            )
        )

        external = manual_models.Manual(
            id=EXTERNAL_MANUAL_ID,
            tenant_id=tenant.id,
            code="KCAA-CI-EXT-001",
            title="KCAA Controlled External Technical Data",
            manual_type="EXTERNAL_DOCUMENT",
            owner_role="DOCUMENT_CONTROL",
            status="ACTIVE",
        )
        db.add(external)
        db.flush()
        external_revision = _published_revision(
            revision_id=EXTERNAL_REVISION_ID,
            manual_id=external.id,
            user_id=user.id,
            revision_number="2026-1",
            issue_number="2026",
        )
        db.add(external_revision)
        db.flush()
        external.current_published_rev_id = external_revision.id
        db.add_all([
            knowledge_models.DocumentationNode(
                id=EXTERNAL_NODE_ID,
                tenant_id=amo.id,
                parent_id=root_node.id,
                manual_id=external.id,
                node_type="EXTERNAL_DOCUMENT",
                code=external.code,
                normalized_code=external.code.upper(),
                title=external.title,
                path=f"DMS-CI/{external.code}",
                depth=1,
                order_index=30,
                status="ACTIVE",
                created_by_user_id=user.id,
            ),
            domain_models.DocumentControlProfile(
                id=EXTERNAL_PROFILE_ID,
                tenant_id=amo.id,
                manual_id=external.id,
                document_class="EXTERNAL",
                owner_department="DOCUMENT_CONTROL",
                acknowledgement_required=False,
                access_scope_json={},
                tags_json=["KCAA", "external-data", "ci-proof"],
                metadata_json={"source": "document_governance_ci_seed"},
            ),
        ])
        external_source = domain_models.ExternalDocumentSource(
            id=EXTERNAL_SOURCE_ID,
            tenant_id=amo.id,
            manual_id=external.id,
            provider="Kenya Civil Aviation Authority",
            authority="KCAA",
            subscription_reference="DMS-CI-EXT",
            access_url="https://www.kcaa.or.ke/",
            update_method="MANUAL_CHECK",
            status="ACTIVE",
            last_checked_at=datetime.now(timezone.utc),
            next_check_due_at=datetime.now(timezone.utc) + timedelta(days=30),
            metadata_json={"source": "document_governance_ci_seed"},
        )
        db.add(external_source)
        db.flush()
        db.add(
            domain_models.ExternalRevisionReceipt(
                id=EXTERNAL_RECEIPT_ID,
                tenant_id=amo.id,
                source_id=external_source.id,
                manual_id=external.id,
                revision_label="KCAR 2025 CI proof",
                publication_date=date.today(),
                received_at=datetime.now(timezone.utc),
                received_by_user_id=user.id,
                checksum_sha256=hashlib.sha256(b"amo-portal-external-data-ci-proof").hexdigest(),
                currency_status="CURRENT",
                applicability_status="APPLICABLE",
                evidence_json=[{"type": "ci_fixture", "reference": "KCAA-CI-EXT-001"}],
                notes="Deterministic external-data currency evidence for browser acceptance.",
            )
        )

        # One unresolved owner proposal makes the dashboard queue and URL-backed
        # bounded-library filter observable without inventing production data.
        db.add(
            governance_models.DocumentResponsibilityAssignment(
                id=ASSIGNMENT_ID,
                tenant_id=amo.id,
                manual_id=manual.id,
                revision_id=revision.id,
                responsibility_type="DOCUMENT_OWNER",
                assignee_type="USER",
                assignee_user_id=user.id,
                is_primary=True,
                effective_from=date.today(),
                assignment_source="MIGRATED",
                confidence_percent=95,
                confirmation_status="MATCH_PROPOSED",
                provenance_json={"source": "document_governance_ci_seed"},
                created_by_user_id=user.id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"E2E_AMO_CODE={AMO_SLUG}")
    print(f"E2E_AMO_ADMIN_EMAIL={ADMIN_EMAIL}")
    print(f"E2E_AMO_ADMIN_PASSWORD={ADMIN_PASSWORD}")
    print(f"E2E_DOCUMENT_GOVERNANCE_ID={MANUAL_ID}")


if __name__ == "__main__":
    seed()
