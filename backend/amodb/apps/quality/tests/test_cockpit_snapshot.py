from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality import service as quality_service
from amodb.apps.technical_records import models as tr_models


def _seed_amo_user(db_session, amo_code: str, user_id: str, role: account_models.AccountRole):
    amo = account_models.AMO(
        id=f"amo-{amo_code}",
        amo_code=amo_code,
        name=f"AMO {amo_code}",
        login_slug=amo_code.lower(),
        is_active=True,
    )
    dept = account_models.Department(id=f"dept-{amo_code}", amo_id=amo.id, code="quality", name="Quality")
    user = account_models.User(
        id=user_id,
        amo_id=amo.id,
        department_id=dept.id,
        staff_code=f"SC-{user_id}",
        email=f"{user_id}@example.com",
        hashed_password="x",
        first_name="First",
        last_name="Last",
        full_name="First Last",
        role=role,
        is_active=True,
        must_change_password=False,
    )
    db_session.add_all([amo, dept, user])
    db_session.commit()
    return amo, dept, user


def test_cockpit_snapshot_returns_compact_dashboard_and_action_queue(db_session, monkeypatch):
    for idx in range(30):
        db_session.add(
            quality_models.CorrectiveActionRequest(
                program=quality_models.CARProgram.QUALITY,
                car_number=f"Q-2026-{idx:04d}",
                title=f"CAR {idx}",
                summary="Action needed",
                priority=quality_models.CARPriority.MEDIUM,
                status=quality_models.CARStatus.OPEN,
                invite_token=f"token-{idx}",
                due_date=date.today() + timedelta(days=idx),
            )
        )
    db_session.commit()

    monkeypatch.setattr(quality_service, "get_dashboard", lambda *_args, **_kwargs: {
        "distributions_pending_ack": 3,
        "audits_open": 5,
        "audits_total": 11,
        "findings_overdue_total": 2,
        "findings_open_total": 7,
        "documents_active": 13,
        "documents_draft": 2,
        "documents_obsolete": 1,
        "change_requests_open": 4,
    })

    snapshot = quality_service.get_cockpit_snapshot(db_session)

    assert snapshot["generated_at"] is not None
    assert snapshot["pending_acknowledgements"] >= 0
    assert snapshot["audits_open"] >= 0
    assert snapshot["documents_active"] >= 0
    assert snapshot["documents_draft"] == 2
    assert snapshot["change_requests_open"] == 4
    assert snapshot["cars_open_total"] == 30
    assert "audit_closure_trend" in snapshot
    assert "most_common_finding_trend_12m" in snapshot
    assert len(snapshot["action_queue"]) == 25
    assert snapshot["action_queue"][0]["kind"] == "CAR"
    assert "manpower" in snapshot


def test_cockpit_snapshot_manpower_and_tenant_scoping(db_session, monkeypatch):
    amo_a, _dept_a, user_a = _seed_amo_user(db_session, "A1", "user-a", account_models.AccountRole.QUALITY_MANAGER)
    amo_b, _dept_b, user_b = _seed_amo_user(db_session, "B1", "user-b", account_models.AccountRole.TECHNICIAN)

    monkeypatch.setattr(quality_service, "get_dashboard", lambda *_args, **_kwargs: {
        "distributions_pending_ack": 0,
        "audits_open": 0,
        "audits_total": 0,
        "findings_overdue_total": 0,
        "findings_open_total": 0,
        "documents_active": 0,
        "documents_draft": 0,
        "documents_obsolete": 0,
        "change_requests_open": 0,
    })

    quality_models.UserAvailability.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    db_session.add_all([
        quality_models.UserAvailability(
            amo_id=amo_a.id,
            user_id=user_a.id,
            status=quality_models.UserAvailabilityStatus.ON_DUTY,
            effective_from=datetime.now(timezone.utc) - timedelta(hours=1),
            updated_by_user_id=user_a.id,
        ),
        quality_models.UserAvailability(
            amo_id=amo_b.id,
            user_id=user_b.id,
            status=quality_models.UserAvailabilityStatus.ON_LEAVE,
            effective_from=datetime.now(timezone.utc) - timedelta(hours=1),
            updated_by_user_id=user_b.id,
        ),
    ])
    db_session.commit()

    snapshot_a = quality_service.get_cockpit_snapshot(db_session, amo_id=amo_a.id, department_code="quality")
    snapshot_b = quality_service.get_cockpit_snapshot(db_session, amo_id=amo_b.id, department_code="quality")

    assert snapshot_a["manpower"]["total_employees"] == 1
    assert snapshot_a["manpower"]["availability"]["on_duty"] == 1
    assert snapshot_a["manpower"]["availability"]["on_leave"] == 0

    assert snapshot_b["manpower"]["total_employees"] == 1
    assert snapshot_b["manpower"]["availability"]["on_leave"] == 1
    assert snapshot_b["manpower"]["availability"]["on_duty"] == 0


def test_cockpit_snapshot_demo_seed_guard(db_session, monkeypatch):
    amo_demo, _dept, _user = _seed_amo_user(db_session, "DEMO", "user-demo", account_models.AccountRole.QUALITY_MANAGER)
    amo_demo.is_demo = True
    db_session.commit()

    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")
    monkeypatch.setattr(quality_service, "get_dashboard", lambda *_args, **_kwargs: {
        "distributions_pending_ack": 0,
        "audits_open": 0,
        "audits_total": 0,
        "findings_overdue_total": 0,
        "findings_open_total": 0,
        "documents_active": 0,
        "documents_draft": 0,
        "documents_obsolete": 0,
        "change_requests_open": 0,
    })

    snapshot = quality_service.get_cockpit_snapshot(db_session, amo_id=amo_demo.id, department_code="quality")
    assert snapshot["manpower"] is not None
    assert snapshot["manpower"]["availability"] is not None


def test_cockpit_snapshot_demo_seed_not_applied_to_real_tenant(db_session, monkeypatch):
    amo_real, _dept, _user = _seed_amo_user(db_session, "REAL1", "user-real", account_models.AccountRole.QUALITY_MANAGER)
    amo_real.is_demo = False
    db_session.commit()

    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")
    monkeypatch.setattr(quality_service, "get_dashboard", lambda *_args, **_kwargs: {
        "distributions_pending_ack": 0,
        "audits_open": 0,
        "audits_total": 0,
        "findings_overdue_total": 0,
        "findings_open_total": 0,
        "documents_active": 0,
        "documents_draft": 0,
        "documents_obsolete": 0,
        "change_requests_open": 0,
    })

    snapshot = quality_service.get_cockpit_snapshot(db_session, amo_id=amo_real.id, department_code="quality")
    assert snapshot["manpower"]["availability"] is None


def test_cockpit_snapshot_includes_compliance_exception_metrics(db_session, monkeypatch):
    amo, _dept, user = _seed_amo_user(db_session, "QX", "user-qx", account_models.AccountRole.QUALITY_MANAGER)

    monkeypatch.setattr(quality_service, "get_dashboard", lambda *_args, **_kwargs: {
        "distributions_pending_ack": 0,
        "audits_open": 0,
        "audits_total": 0,
        "findings_overdue_total": 0,
        "findings_open_total": 0,
        "documents_active": 0,
        "documents_draft": 0,
        "documents_obsolete": 0,
        "change_requests_open": 0,
    })

    tr_models.AirworthinessWatchlist.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    tr_models.AirworthinessPublication.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    tr_models.AirworthinessPublicationMatch.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    tr_models.ComplianceAction.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    watch = tr_models.AirworthinessWatchlist(amo_id=amo.id, name="Engine", status="Active", criteria_json={}, created_by_user_id=user.id)
    db_session.add(watch)
    db_session.flush()

    pub = tr_models.AirworthinessPublication(
        amo_id=amo.id,
        source="FAA",
        authority="FAA",
        document_type="AD",
        doc_number="AD-1",
        title="Test AD",
        keywords=[],
        raw_metadata_json={},
    )
    db_session.add(pub)
    db_session.flush()

    match = tr_models.AirworthinessPublicationMatch(
        amo_id=amo.id,
        watchlist_id=watch.id,
        publication_id=pub.id,
        classification="Applicable",
        review_status="Matched",
    )
    db_session.add(match)
    db_session.flush()

    action = tr_models.ComplianceAction(
        amo_id=amo.id,
        publication_match_id=match.id,
        decision="IMMEDIATE_ACTION",
        status="Under Review",
        due_date=date.today() - timedelta(days=1),
        created_by_user_id=user.id,
    )
    db_session.add(action)
    db_session.commit()

    snapshot = quality_service.get_cockpit_snapshot(db_session, amo_id=amo.id, department_code="quality")
    assert snapshot["compliance_exceptions_open"] >= 1
    assert snapshot["compliance_overdue"] >= 1
    assert snapshot["compliance_unplanned_applicable"] >= 1
    assert any(item["kind"] == "COMPLIANCE" for item in snapshot["action_queue"])
