from __future__ import annotations

from pathlib import Path

from amodb.apps.rostering import notification_resilience_policy


ROOT = Path(__file__).resolve().parents[1]


def test_overlong_roster_notification_correlation_is_compacted_to_db_contract():
    source = (
        "roster-compliance-blocked:ID-70SAG9IR:"
        "8a69f17dc39f0a5b76989fe518dbed3aa8819115d350301af14c5887179d4cff"
    )
    compacted = notification_resilience_policy.compact_correlation_id(source)

    assert len(source) > 64
    assert len(compacted) == 64
    assert compacted == notification_resilience_policy.compact_correlation_id(source)
    assert compacted != source[:64]


def test_short_correlation_id_is_preserved_for_existing_integrations():
    source = "task:1:reminder"
    assert notification_resilience_policy.compact_correlation_id(source) == source


def test_notification_policy_is_installed_before_compliance_email_wrapper():
    source = (ROOT / "application_router.py").read_text(encoding="utf-8")
    resilience = "notification_resilience_policy.install()"
    compliance = "compliance_audit_policy.install()"

    assert resilience in source
    assert compliance in source
    assert source.index(resilience) < source.index(compliance)


def test_roster_notification_delivery_uses_an_independent_database_session():
    source = (ROOT / "notification_resilience_policy.py").read_text(encoding="utf-8")

    assert "db=None" in source
    assert "safe_correlation_id = compact_correlation_id(correlation_id)" in source
    assert "entity_id=safe_correlation_id" in source
    assert "critical=False" in source
