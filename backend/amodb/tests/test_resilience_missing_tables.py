import os
import sys
from pathlib import Path

from sqlalchemy.exc import ProgrammingError

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/testdb")
sys.path.append(str(Path(__file__).resolve().parents[2]))

from amodb.apps.accounts import services as account_services  # noqa: E402
from amodb.apps.quality import service as quality_service  # noqa: E402


class _RaisingInvoicesQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        raise ProgrammingError("SELECT * FROM billing_invoices", {}, Exception("missing table"))


class _InvoiceDbStub:
    def query(self, *_args, **_kwargs):
        return _RaisingInvoicesQuery()


def test_list_invoices_returns_empty_when_table_missing():
    invoices = account_services.list_invoices(_InvoiceDbStub(), amo_id="amo-1")
    assert invoices == []


class _RaisingCarsQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        raise ProgrammingError("SELECT * FROM quality_cars", {}, Exception("missing table"))

    def count(self):
        raise ProgrammingError("SELECT count(*) FROM quality_cars", {}, Exception("missing table"))


class _SafeCountQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return 0


class _SnapshotDbStub:
    def query(self, model, *_args, **_kwargs):
        model_name = getattr(model, "__name__", "")
        if model_name == "CorrectiveActionRequest":
            return _RaisingCarsQuery()
        return _SafeCountQuery()


def test_get_cockpit_snapshot_survives_missing_car_table(monkeypatch):
    monkeypatch.setattr(
        quality_service,
        "get_dashboard",
        lambda db, domain=None: {
            "distributions_pending_ack": 0,
            "audits_open": 0,
            "audits_total": 0,
            "findings_overdue_total": 0,
            "findings_open_total": 0,
            "documents_active": 0,
            "documents_draft": 0,
            "documents_obsolete": 0,
            "change_requests_open": 0,
        },
    )
    monkeypatch.setattr(quality_service, "_build_audit_closure_trend", lambda db: [])
    monkeypatch.setattr(quality_service, "_build_most_common_finding_trend_12m", lambda db: [])

    snapshot = quality_service.get_cockpit_snapshot(_SnapshotDbStub())

    assert snapshot["cars_open_total"] == 0
    assert snapshot["cars_overdue"] == 0
    assert snapshot["action_queue"] == []
