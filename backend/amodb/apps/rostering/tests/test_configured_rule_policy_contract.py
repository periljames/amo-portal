from __future__ import annotations

from pathlib import Path

from amodb.apps.rostering import configured_rule_policy


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_default_rule_seed_hook_never_queries_or_mutates_database():
    class ExplodingDatabase:
        def __getattribute__(self, name):
            if name in {"query", "add", "flush"}:
                raise AssertionError(f"legacy seed touched database through {name}")
            return super().__getattribute__(name)

    assert configured_rule_policy._configured_rules_only(
        ExplodingDatabase(),
        amo_id="ID-TEST-AMO",
        actor_user_id="ID-TEST-USER",
    ) is None


def test_application_installs_configured_rule_policy_before_validation_wrappers():
    source = (ROOT / "application_router.py").read_text(encoding="utf-8")
    configured_install = "configured_rule_policy.install_service_policy(rostering_route_module.services)"
    compliance_install = "compliance_policy.install_validation_policy()"
    statutory_install = "statutory_rule_policy.install()"

    assert configured_install in source
    assert source.index(configured_install) < source.index(compliance_install)
    assert source.index(configured_install) < source.index(statutory_install)


def test_policy_does_not_reintroduce_removed_default_rule_set_helper():
    source = (ROOT / "configured_rule_policy.py").read_text(encoding="utf-8")
    assert "governance.seed_default_rule_set(" not in source
    assert "validation.seed_default_rules = _configured_rules_only" in source
    assert "validation.active_rules = _configured_active_rules" in source


def test_active_validation_requires_active_effective_parent_rule_set():
    source = (ROOT / "configured_rule_policy.py").read_text(encoding="utf-8")
    expected = [
        ".join(models.RosterRuleSet, models.RosterRule.rule_set_id == models.RosterRuleSet.id)",
        "models.RosterRuleSet.amo_id == amo_id",
        "models.RosterRuleSet.is_active.is_(True)",
        "models.RosterRuleSet.effective_from <= on_date",
        "models.RosterRuleSet.effective_to >= on_date",
        "models.RosterRule.is_active.is_(True)",
        "models.RosterRule.effective_from <= on_date",
        "models.RosterRule.effective_to >= on_date",
    ]
    for fragment in expected:
        assert fragment in source
