from __future__ import annotations

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_integration_router as integrations


def test_training_course_resolves_to_authoritative_training_table() -> None:
    table = integrations._resolve_source_table(
        "TRAINING",
        "training_course",
        {"source_table": "training_courses"},
    )
    assert table.name == "training_courses"


def test_qms_document_resolves_to_authoritative_qms_table() -> None:
    table = integrations._resolve_source_table(
        "QMS",
        "qms_document",
        {"source_table": "qms_documents"},
    )
    assert table.name == "qms_documents"


def test_module_cannot_point_to_an_unrelated_table() -> None:
    with pytest.raises(HTTPException) as caught:
        integrations._resolve_source_table(
            "TRAINING",
            "user",
            {"source_table": "users"},
        )
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "INTEGRATION_SOURCE_UNRESOLVED"


def test_unknown_entity_type_fails_instead_of_creating_an_unverified_link() -> None:
    with pytest.raises(HTTPException) as caught:
        integrations._resolve_source_table(
            "QMS",
            "imaginary_quality_record",
            {},
        )
    assert caught.value.status_code == 422
