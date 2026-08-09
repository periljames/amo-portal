from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from amodb.apps.platform.change_markers import record_deployment_marker
from amodb.apps.platform.ops_data_models import PlatformChangeMarker


def _session_with_existing(row: PlatformChangeMarker | None) -> MagicMock:
    db = MagicMock()
    query = db.query.return_value
    filtered = query.filter.return_value
    ordered = filtered.order_by.return_value
    ordered.first.return_value = row
    return db


def test_record_deployment_marker_creates_automation_owned_marker() -> None:
    db = _session_with_existing(None)

    row = record_deployment_marker(
        db,
        reference="abc123@20260809T083500Z",
        title="Deployment abc123",
        details={
            "git_sha": "abc123",
            "source": "scripts/deploy.sh",
            "nested": {"not": "retained"},
        },
    )

    assert row.kind == "DEPLOYMENT"
    assert row.reference == "abc123@20260809T083500Z"
    assert row.title == "Deployment abc123"
    assert row.actor_user_id is None
    assert row.details_json == {"git_sha": "abc123", "source": "scripts/deploy.sh"}
    db.add.assert_called_once_with(row)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(row)


def test_record_deployment_marker_reuses_same_automation_reference() -> None:
    existing = PlatformChangeMarker(
        kind="DEPLOYMENT",
        reference="abc123@20260809T083500Z",
        title="Old deployment title",
        details_json={"source": "old"},
        actor_user_id=None,
    )
    db = _session_with_existing(existing)

    row = record_deployment_marker(
        db,
        reference="abc123@20260809T083500Z",
        title="Deployment abc123",
        details={"source": "scripts/deploy.sh", "deployed_at": "20260809T083500Z"},
    )

    assert row is existing
    assert row.title == "Deployment abc123"
    assert row.details_json == {
        "source": "scripts/deploy.sh",
        "deployed_at": "20260809T083500Z",
    }
    db.add.assert_not_called()
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(existing)


def test_record_deployment_marker_rejects_empty_reference() -> None:
    db = _session_with_existing(None)

    with pytest.raises(ValueError, match="reference is required"):
        record_deployment_marker(db, reference="   ")

    db.commit.assert_not_called()
