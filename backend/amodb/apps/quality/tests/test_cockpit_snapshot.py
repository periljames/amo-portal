from __future__ import annotations

from datetime import date, timedelta

from amodb.apps.quality import models as quality_models
from amodb.apps.quality import service as quality_service


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
        "documents_obsolete": 1,
    })

    snapshot = quality_service.get_cockpit_snapshot(db_session)

    assert snapshot["generated_at"] is not None
    assert snapshot["pending_acknowledgements"] >= 0
    assert snapshot["audits_open"] >= 0
    assert snapshot["documents_active"] >= 0
    assert len(snapshot["action_queue"]) == 25
    assert snapshot["action_queue"][0]["kind"] == "CAR"
