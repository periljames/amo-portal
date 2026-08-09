"""Seed a newer external revision that requires controlled applicability assessment.

This extends the disposable DMS browser fixture with both a known-current receipt
and a later unverified receipt plus one confirmed relationship to an internal
manual. Browser acceptance must therefore record a real applicability decision
instead of proving only the presence of the assessment drawer.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.main import app as _app  # noqa: F401,E402
from amodb.apps.doc_control import domain_models, governance_models  # noqa: E402
from amodb.database import WriteSessionLocal  # noqa: E402

AMO_ID = "00000000-0000-4000-8000-000000000477"
CONTROLLER_USER_ID = "00000000-0000-4000-8000-000000000478"
INTERNAL_MANUAL_ID = "00000000-0000-4000-8000-000000000480"
EXTERNAL_MANUAL_ID = "00000000-0000-4000-8000-000000000490"
EXTERNAL_REVISION_ID = "00000000-0000-4000-8000-000000000491"
EXTERNAL_SOURCE_ID = "00000000-0000-4000-8000-000000000494"
NEW_RECEIPT_ID = "00000000-0000-4000-8000-000000000506"
RELATIONSHIP_ID = "00000000-0000-4000-8000-000000000507"


def seed() -> None:
    db = WriteSessionLocal()
    try:
        if db.query(domain_models.ExternalRevisionReceipt).filter(domain_models.ExternalRevisionReceipt.id == NEW_RECEIPT_ID).first():
            raise RuntimeError("External assessment fixture already exists; use a fresh disposable database")
        source = db.query(domain_models.ExternalDocumentSource).filter(domain_models.ExternalDocumentSource.id == EXTERNAL_SOURCE_ID).one()
        latest_existing = (
            db.query(domain_models.ExternalRevisionReceipt)
            .filter(domain_models.ExternalRevisionReceipt.source_id == source.id)
            .order_by(domain_models.ExternalRevisionReceipt.received_at.desc())
            .first()
        )
        received_at = max(
            datetime.now(timezone.utc),
            (latest_existing.received_at + timedelta(seconds=1)) if latest_existing and latest_existing.received_at else datetime.now(timezone.utc),
        )
        db.add(
            domain_models.ExternalRevisionReceipt(
                id=NEW_RECEIPT_ID,
                tenant_id=AMO_ID,
                source_id=source.id,
                manual_id=EXTERNAL_MANUAL_ID,
                revision_label="KCAR 2025 CI proof Rev 2",
                publication_date=date.today(),
                received_at=received_at,
                received_by_user_id=CONTROLLER_USER_ID,
                checksum_sha256=hashlib.sha256(b"amo-portal-external-data-ci-proof-rev-2").hexdigest(),
                currency_status="UNVERIFIED",
                applicability_status="PENDING",
                evidence_json=[{"kind": "RECEIPT", "reference": "KCAA-CI-EXT-001-REV2"}],
                notes="Newer external revision awaiting controlled applicability assessment.",
            )
        )
        db.add(
            governance_models.DocumentGovernedRelationship(
                id=RELATIONSHIP_ID,
                tenant_id=AMO_ID,
                source_manual_id=EXTERNAL_MANUAL_ID,
                source_revision_id=EXTERNAL_REVISION_ID,
                target_entity_type="DOCUMENT",
                target_entity_id=INTERNAL_MANUAL_ID,
                target_manual_id=INTERNAL_MANUAL_ID,
                relationship_type="REFERENCES",
                relationship_source="MANUAL",
                occurrence_key="ci-external-rev2-affects-dms-mom",
                exact_token="DMS-CI-MOM",
                confidence_percent=100,
                resolution_status="CONFIRMED",
                provenance_json={"source": "document_external_assessment_ci_seed"},
                created_by_user_id=CONTROLLER_USER_ID,
                confirmed_by_user_id=CONTROLLER_USER_ID,
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"E2E_DMS_EXTERNAL_SOURCE_ID={EXTERNAL_SOURCE_ID}")
    print(f"E2E_DMS_EXTERNAL_RECEIPT_ID={NEW_RECEIPT_ID}")


if __name__ == "__main__":
    seed()
