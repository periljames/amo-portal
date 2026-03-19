from __future__ import annotations

import importlib
from contextlib import contextmanager
from datetime import date

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import schemas as quality_schemas

quality_router = importlib.import_module("amodb.apps.quality.router")


def _request() -> Request:
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})


def _create_quality_user(db_session, *, amo: account_models.AMO, email: str) -> account_models.User:
    user = account_models.User(
        amo_id=amo.id,
        email=email,
        staff_code=email.split("@", 1)[0][:8].upper(),
        first_name="Quality",
        last_name="User",
        full_name="Quality User",
        hashed_password="hash",
        role=account_models.AccountRole.QUALITY_MANAGER,
        is_active=True,
        is_amo_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_derive_audit_unit_code_prefers_readable_cleaned_code(db_session):
    amo = account_models.AMO(amo_code="amo-west-hangar", icao_code="hkx1", name="West", login_slug="west")
    db_session.add(amo)
    db_session.commit()

    assert quality_router._derive_audit_unit_code(db_session, amo.id) == "AMOWESHA"


def test_generate_audit_reference_increments_existing_scope(db_session):
    amo = account_models.AMO(amo_code="amo-demo", name="Demo", login_slug="demo")
    db_session.add(amo)
    db_session.commit()
    db_session.add(
        quality_models.QMSAuditReferenceCounter(
            amo_id=amo.id,
            reference_family="QAR",
            unit_code="AMODEMO",
            ref_year=26,
            last_value=4,
        )
    )
    db_session.commit()

    audit_ref, unit_code, ref_year, ref_sequence = quality_router._generate_audit_reference(
        db_session,
        amo_id=amo.id,
        target_date=date(2026, 3, 19),
    )

    assert audit_ref == "QAR/AMODEMO/26/005"
    assert unit_code == "AMODEMO"
    assert ref_year == 26
    assert ref_sequence == 5


def test_generate_audit_reference_retries_first_insert_race():
    class FakeCounter:
        def __init__(self, last_value: int):
            self.last_value = last_value

    class FakeQuery:
        def __init__(self, responses):
            self._responses = responses

        def filter(self, *args, **kwargs):
            return self

        def with_for_update(self):
            return self

        def first(self):
            return self._responses.pop(0)

    class FakeSession:
        def __init__(self):
            self.responses = [None, FakeCounter(0)]
            self.flush_attempts = 0

        def query(self, *args, **kwargs):
            return FakeQuery(self.responses)

        @contextmanager
        def begin_nested(self):
            yield

        def add(self, obj):
            return None

        def flush(self):
            self.flush_attempts += 1
            if self.flush_attempts == 1:
                raise IntegrityError("insert", {}, Exception("duplicate counter scope"))

    fake_db = FakeSession()

    audit_ref, unit_code, ref_year, ref_sequence = quality_router._generate_audit_reference(
        fake_db,
        amo_id="amo-1",
        target_date=date(2026, 3, 19),
        reference_family="QAR",
    )

    assert audit_ref == "QAR/MO/26/001"
    assert unit_code == "MO"
    assert ref_year == 26
    assert ref_sequence == 1


def test_two_amos_with_same_display_unit_code_can_create_same_human_ref_without_collision(db_session, monkeypatch):
    amo_a = account_models.AMO(amo_code="AMO-CAR", name="Carrier", login_slug="carrier")
    amo_b = account_models.AMO(amo_code="AMO-CAP", name="Capstone", login_slug="capstone")
    db_session.add_all([amo_a, amo_b])
    db_session.commit()
    user_a = _create_quality_user(db_session, amo=amo_a, email="a@example.com")
    user_b = _create_quality_user(db_session, amo=amo_b, email="b@example.com")

    payload = quality_schemas.QMSAuditCreate(
        domain=quality_models.QMSDomain.AMO,
        kind=quality_models.QMSAuditKind.INTERNAL,
        title="Tenant scoped audit",
        planned_start=date(2026, 3, 19),
        planned_end=date(2026, 3, 20),
    )

    monkeypatch.setattr(quality_router, "_derive_audit_unit_code", lambda db, amo_id: "AMOC")

    audit_a = quality_router.create_audit(payload=payload, request=_request(), db=db_session, current_user=user_a)
    audit_b = quality_router.create_audit(payload=payload, request=_request(), db=db_session, current_user=user_b)

    assert audit_a.audit_ref == audit_b.audit_ref
    assert audit_a.amo_id != audit_b.amo_id


def test_qms_audit_constraints_are_scoped_per_amo(db_session):
    constraints = {item["name"]: tuple(item["column_names"]) for item in inspect(db_session.bind).get_unique_constraints("qms_audits")}
    assert constraints["uq_qms_audit_ref_per_amo"] == ("amo_id", "domain", "audit_ref")
    assert constraints["uq_qms_audit_ref_scope_per_amo"] == (
        "amo_id",
        "domain",
        "reference_family",
        "unit_code",
        "ref_year",
        "ref_sequence",
    )


def test_bulk_findings_endpoint_scopes_to_current_amo(db_session):
    amo_a = account_models.AMO(amo_code="AMO-A", name="A", login_slug="a")
    amo_b = account_models.AMO(amo_code="AMO-B", name="B", login_slug="b")
    db_session.add_all([amo_a, amo_b])
    db_session.commit()
    user_a = _create_quality_user(db_session, amo=amo_a, email="scope-a@example.com")
    user_b = _create_quality_user(db_session, amo=amo_b, email="scope-b@example.com")

    audit_a = quality_router.create_audit(
        payload=quality_schemas.QMSAuditCreate(domain=quality_models.QMSDomain.AMO, kind=quality_models.QMSAuditKind.INTERNAL, title="A", planned_start=date(2026, 3, 1)),
        request=_request(),
        db=db_session,
        current_user=user_a,
    )
    audit_b = quality_router.create_audit(
        payload=quality_schemas.QMSAuditCreate(domain=quality_models.QMSDomain.AMO, kind=quality_models.QMSAuditKind.INTERNAL, title="B", planned_start=date(2026, 3, 1)),
        request=_request(),
        db=db_session,
        current_user=user_b,
    )
    db_session.add_all(
        [
            quality_models.QMSAuditFinding(audit_id=audit_a.id, description="Finding A"),
            quality_models.QMSAuditFinding(audit_id=audit_b.id, description="Finding B"),
        ]
    )
    db_session.commit()

    findings = quality_router.list_findings_bulk(db=db_session, current_user=user_a, domain=quality_models.QMSDomain.AMO, audit_ids=None)
    assert len(findings) == 1
    assert findings[0].audit_id == audit_a.id
