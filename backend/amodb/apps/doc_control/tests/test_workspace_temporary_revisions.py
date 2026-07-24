from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import workspace_tr_router as tr_guards


def test_temporary_revision_lifecycle_has_terminal_states() -> None:
    assert tr_guards._ALLOWED_TRANSITIONS["DRAFT"] == {"IN_REVIEW", "WITHDRAWN"}
    assert "IN_FORCE" not in tr_guards._ALLOWED_TRANSITIONS["DRAFT"]
    assert tr_guards._ALLOWED_TRANSITIONS["WITHDRAWN"] == set()
    assert tr_guards._ALLOWED_TRANSITIONS["INCORPORATED"] == set()


def test_campaign_validation_is_tenant_and_tr_specific(monkeypatch) -> None:
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
