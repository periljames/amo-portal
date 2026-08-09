"""Deterministic 10k-document PostgreSQL scale gate for Document Control.

Runs only against disposable CI data. It proves that both the authoritative
Library table and the richer MD discovery/search route keep access filtering,
counting and pagination in PostgreSQL and materialize at most the requested
page when tenant volume exceeds 10,000 documents.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from time import perf_counter
import uuid

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control.workspace_library_discovery_router import library_discovery
from amodb.apps.doc_control.workspace_library_router import list_visible_documents
from amodb.apps.manuals import models as manual_models
from amodb.database import WriteSessionLocal
from amodb.scripts.seed_document_governance_e2e import (
    ADMIN_EMAIL,
    TENANT_ID,
    seed as seed_governed_fixture,
)


SCALE_DOCUMENTS = 10_000
MAX_QUERY_SECONDS = 5.0
EVIDENCE_PATH = Path("test-results/document-control-library-scale.json")


def _scale_id(index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"amo-portal-dms-scale-{index}"))


def _query_library(*, db, user, q: str | None, page: int, per_page: int):
    return list_visible_documents(
        tenant_slug="dmsgate",
        q=q,
        document_class=None,
        status=None,
        node_type=None,
        owner_user_id=None,
        department_id=None,
        indexing_status=None,
        unresolved_ownership=False,
        unresolved_relationships=False,
        structure_status=None,
        superseded_referenced=False,
        sort="code",
        direction="asc",
        page=page,
        per_page=per_page,
        db=db,
        current_user=user,
    )


def _query_discovery(*, db, user, q: str | None, page: int, per_page: int):
    return library_discovery(
        tenant_slug="dmsgate",
        view="all",
        q=q,
        page=page,
        per_page=per_page,
        db=db,
        current_user=user,
    )


def main() -> None:
    seed_governed_fixture()
    db = WriteSessionLocal()
    try:
        existing = int(
            db.query(manual_models.Manual)
            .filter(manual_models.Manual.tenant_id == TENANT_ID)
            .count()
        )
        rows = [
            {
                "id": _scale_id(index),
                "tenant_id": TENANT_ID,
                "code": f"DMS-SCALE-{index:05d}",
                "title": f"Scale controlled document {index:05d}",
                "manual_type": "PROCEDURE",
                "owner_role": "DOCUMENT_CONTROL",
                "current_published_rev_id": None,
                "status": "ACTIVE",
            }
            for index in range(1, SCALE_DOCUMENTS + 1)
        ]
        db.bulk_insert_mappings(manual_models.Manual, rows)
        db.commit()

        user = db.query(account_models.User).filter(account_models.User.email == ADMIN_EMAIL).one()

        started = perf_counter()
        first_page = _query_library(db=db, user=user, q=None, page=1, per_page=100)
        first_page_seconds = perf_counter() - started

        started = perf_counter()
        searched = _query_library(db=db, user=user, q="DMS-SCALE-09999", page=1, per_page=25)
        search_seconds = perf_counter() - started

        started = perf_counter()
        discovered = _query_discovery(db=db, user=user, q="DMS-SCALE-09999", page=1, per_page=25)
        discovery_search_seconds = perf_counter() - started

        evidence = {
            "seeded_scale_documents": SCALE_DOCUMENTS,
            "total_visible_documents": first_page["pagination"]["total"],
            "first_page_returned": first_page["pagination"]["returned"],
            "first_page_seconds": round(first_page_seconds, 4),
            "exact_search_returned": searched["pagination"]["returned"],
            "exact_search_seconds": round(search_seconds, 4),
            "discovery_exact_search_returned": discovered["pagination"]["returned"],
            "discovery_exact_search_seconds": round(discovery_search_seconds, 4),
            "threshold_seconds": MAX_QUERY_SECONDS,
        }
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))

        total_expected = existing + SCALE_DOCUMENTS
        assert first_page["pagination"]["total"] == total_expected, first_page["pagination"]
        assert first_page["pagination"]["returned"] <= 100, first_page["pagination"]
        assert len(first_page["items"]) <= 100
        assert searched["pagination"]["total"] == 1, searched["pagination"]
        assert searched["pagination"]["returned"] == 1, searched["pagination"]
        assert searched["items"][0]["code"] == "DMS-SCALE-09999"
        assert discovered["pagination"]["total"] == 1, discovered["pagination"]
        assert discovered["pagination"]["returned"] == 1, discovered["pagination"]
        assert discovered["items"][0]["code"] == "DMS-SCALE-09999"
        assert len(discovered["items"]) <= 25
        assert first_page_seconds <= MAX_QUERY_SECONDS, f"10k first page took {first_page_seconds:.3f}s"
        assert search_seconds <= MAX_QUERY_SECONDS, f"10k exact search took {search_seconds:.3f}s"
        assert discovery_search_seconds <= MAX_QUERY_SECONDS, f"10k rich discovery search took {discovery_search_seconds:.3f}s"
    finally:
        db.close()


if __name__ == "__main__":
    main()
