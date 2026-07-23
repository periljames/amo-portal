from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.platform import (
    saas_admin_links,
    saas_fiscalization_policy,
    saas_services,
)
from amodb.apps.realtime.gateway import RealtimeGateway


tenant_saas_router = import_module("amodb.apps.platform.tenant_saas_router")


def _fiscalization_db(status: str) -> MagicMock:
    row = SimpleNamespace(status=status)
    query = MagicMock()
    query.filter.return_value.first.return_value = row
    db = MagicMock()
    db.query.return_value = query
    return db


def test_platform_package_installs_runtime_admin_and_fiscalization_policies():
    assert saas_admin_links._INSTALLED is True
    assert saas_fiscalization_policy._INSTALLED is True
    assert saas_services.enqueue_fiscalization.__name__ == "guarded_enqueue_fiscalization"

    tenant_links = tenant_saas_router._setup_links("amo-1", False)
    assert tenant_links["tenant_admin_path"] == "/maintenance/{amoCode}/admin/email-settings"
    assert tenant_links["platform_integrations_path"] is None
    assert tenant_links["platform_billing_path"] is None

    platform_links = tenant_saas_router._setup_links(None, True)
    assert platform_links["platform_integrations_path"] == "/platform/integrations"
    assert platform_links["platform_billing_path"] == "/platform/billing"


@pytest.mark.parametrize(
    ("state", "message"),
    [
        ("FISCALIZED", "already fiscalized"),
        ("RECONCILIATION_REQUIRED", "requires eTIMS reconciliation"),
        ("SUBMITTING", "already in progress"),
        ("SUBMITTED", "already in progress"),
        ("FAILED", "must be reviewed"),
    ],
)
def test_terminal_or_uncertain_fiscalization_state_cannot_be_reset(state: str, message: str):
    with pytest.raises(ValueError, match=message):
        saas_fiscalization_policy.validate_fiscalization_enqueue(
            _fiscalization_db(state),
            invoice_id="invoice-1",
        )


def test_new_or_queued_fiscalization_can_use_idempotent_enqueue_path():
    empty_query = MagicMock()
    empty_query.filter.return_value.first.return_value = None
    empty_db = MagicMock()
    empty_db.query.return_value = empty_query
    saas_fiscalization_policy.validate_fiscalization_enqueue(
        empty_db,
        invoice_id="invoice-new",
    )

    saas_fiscalization_policy.validate_fiscalization_enqueue(
        _fiscalization_db("QUEUED"),
        invoice_id="invoice-queued",
    )


def test_mqtt_connect_callback_only_wakes_background_drain():
    gateway = RealtimeGateway()
    gateway.flush_pending = MagicMock(return_value=0)
    client = MagicMock()

    gateway._on_connect(client, None, {}, 0)

    assert gateway._connected is True
    client.subscribe.assert_called_once()
    gateway.flush_pending.assert_not_called()
    assert gateway._drain_wakeup.is_set()


def test_failed_mqtt_connect_does_not_trigger_drain():
    gateway = RealtimeGateway()
    gateway.flush_pending = MagicMock(return_value=0)
    client = MagicMock()

    gateway._on_connect(client, None, {}, 1)

    assert gateway._connected is False
    client.subscribe.assert_not_called()
    gateway.flush_pending.assert_not_called()
    assert not gateway._drain_wakeup.is_set()
