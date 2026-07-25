from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_schemas as schemas
from amodb.apps.doc_control import workspace_tr_router as tr_guards


def _manual(current_revision_id: str = "revision-1"):
    return SimpleNamespace(current_published_rev_id=current_revision_id)


def _revision(
    revision_id: str,
    *,
    status: str,
    immutable: bool,
):
    return SimpleNamespace(
        id=revision_id,
        status_enum=status,
        immutable_locked=immutable,
    )


def _payload(**values):
    payload = {
        "manual_id": "manual-1",
        "base_revision_id": "revision-1",
        "revision_id": "revision-2",
        "tr_number": "TR-001",
        "title": "Temporary inspection interval amendment",
        "reason": "Immediate controlled amendment pending permanent incorporation",
        "affected_sections": [{"section": "Chapter 5, Section 3"}],
        "filing_instructions": "Insert after Chapter 5 page 12 and remove when incorporated.",
        "effective_date": date.today(),
        "expiry_date": date.today() + timedelta(days=90),
    }
    payload.update(values)
    return schemas.TemporaryRevisionCreate(**payload)


def test_temporary_revision_lifecycle_has_terminal_states() -> None:
    assert tr_guards._ALLOWED_TRANSITIONS["DRAFT"] == {"IN_REVIEW", "WITHDRAWN"}
    assert "IN_FORCE" not in tr_guards._ALLOWED_TRANSITIONS["DRAFT"]
    assert tr_guards._ALLOWED_TRANSITIONS["WITHDRAWN"] == set()
    assert tr_guards._ALLOWED_TRANSITIONS["INCORPORATED"] == set()


def test_temporary_revision_requires_current_published_base() -> None:
    with pytest.raises(HTTPException) as caught:
        tr_guards.validate_temporary_revision_create(
            _manual("another-revision"),
            _revision("revision-1", status="PUBLISHED", immutable=True),
            _payload(),
            _revision("revision-2", status="DRAFT", immutable=False),
        )
    assert caught.value.status_code == 409


def test_temporary_revision_requires_explicit_source_revision() -> None:
    with pytest.raises(HTTPException) as caught:
        tr_guards.validate_temporary_revision_create(
            _manual(),
            _revision("revision-1", status="PUBLISHED", immutable=True),
            _payload(revision_id=None),
            None,
        )
    assert caught.value.status_code == 422
    assert caught.value.detail["code"] == "TR_SOURCE_REVISION_REQUIRED"


def test_temporary_revision_requires_affected_sections() -> None:
    with pytest.raises(HTTPException) as caught:
        tr_guards.validate_temporary_revision_create(
            _manual(),
            _revision("revision-1", status="PUBLISHED", immutable=True),
            _payload(affected_sections=[]),
            _revision("revision-2", status="DRAFT", immutable=False),
        )
    assert caught.value.status_code == 422


def test_temporary_revision_requires_filing_instructions() -> None:
    with pytest.raises(HTTPException) as caught:
        tr_guards.validate_temporary_revision_create(
            _manual(),
            _revision("revision-1", status="PUBLISHED", immutable=True),
            _payload(filing_instructions=None),
            _revision("revision-2", status="DRAFT", immutable=False),
        )
    assert caught.value.status_code == 422


def test_temporary_revision_rejects_past_effective_date() -> None:
    with pytest.raises(HTTPException) as caught:
        tr_guards.validate_temporary_revision_create(
            _manual(),
            _revision("revision-1", status="PUBLISHED", immutable=True),
            _payload(effective_date=date.today() - timedelta(days=1)),
            _revision("revision-2", status="DRAFT", immutable=False),
        )
    assert caught.value.status_code == 422


def test_temporary_revision_source_must_remain_uncontrolled() -> None:
    with pytest.raises(HTTPException) as caught:
        tr_guards.validate_temporary_revision_create(
            _manual(),
            _revision("revision-1", status="PUBLISHED", immutable=True),
            _payload(),
            _revision("revision-2", status="PUBLISHED", immutable=True),
        )
    assert caught.value.status_code == 409


def test_valid_temporary_revision_source_and_filing_controls_are_allowed() -> None:
    tr_guards.validate_temporary_revision_create(
        _manual(),
        _revision("revision-1", status="PUBLISHED", immutable=True),
        _payload(),
        _revision("revision-2", status="DRAFT", immutable=False),
    )


def test_campaign_validation_is_tenant_and_tr_specific() -> None:
    class Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    db = SimpleNamespace(query=lambda *args, **kwargs: Query())
    tr = SimpleNamespace(
        id="tr-1",
        manual_id="manual-1",
        revision_id="revision-2",
        base_revision_id="revision-1",
    )
    with pytest.raises(HTTPException) as caught:
        tr_guards._validate_campaign(
            db,
            tenant_id="amo-1",
            tr=tr,
            campaign_id="campaign-from-another-context",
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "TR_DISTRIBUTION_INVALID"


def test_effectivity_window_examples_are_unambiguous() -> None:
    today = date.today()
    assert today - timedelta(days=1) < today < today + timedelta(days=1)
