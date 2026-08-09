from types import SimpleNamespace

from amodb.apps.quality.audit_risk_planning_router import (
    _global_factors,
    _is_safety_occurrence_reference,
    _item_context,
    _scope_values,
)


def _universe(**overrides):
    values = {
        "id": "universe-1",
        "display_label": "Quality system surveillance",
        "entity_type": "QUALITY_SYSTEM",
        "source_owner_module": "quality",
        "source_type": "AUDIT_DOMAIN",
        "source_id": "quality-domain-1",
        "source_route": "/quality/audits",
        "mandatory_surveillance": False,
        "risk_classification": "MEDIUM",
        "regulatory_criticality": "MEDIUM",
        "surveillance_interval_days": 365,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_safety_occurrence_contract_is_exact_and_does_not_relabel_generic_risk() -> None:
    assert _is_safety_occurrence_reference({
        "source_owner_module": "safety",
        "source_type": "SAFETY_OCCURRENCE",
        "source_id": "occ-1",
    }) is True
    assert _is_safety_occurrence_reference({
        "source_owner_module": "risk",
        "source_type": "SAFETY_OCCURRENCE",
        "source_id": "risk-1",
    }) is False
    assert _is_safety_occurrence_reference({
        "source_owner_module": "safety",
        "source_type": "RISK",
        "source_id": "risk-2",
    }) is False


def test_aircraft_scope_contract_requires_explicit_governed_keys() -> None:
    assert _scope_values({"aircraft_type": "DHC-8-400"}, ("aircraft_type", "aircraft_types")) == ["DHC-8-400"]
    assert _scope_values({"aircraft_types": [{"id": "Q400"}, {"name": "DHC-8-100"}]}, ("aircraft_type", "aircraft_types")) == ["Q400", "DHC-8-100"]
    assert _scope_values({"title": "Add DHC-8-400 capability"}, ("aircraft_type", "aircraft_types")) == []


def test_global_factor_contract_includes_ineffective_safety_capability_and_aircraft_sources() -> None:
    factors = _global_factors(
        metrics={},
        reliability={},
        effectiveness={"ineffective_corrective_actions": 2},
        safety={"open_linked_occurrences": 3},
        mission_change={"open_capability_missions": 2, "open_aircraft_type_missions": 1},
    )
    by_code = {factor["code"]: factor for factor in factors}
    assert by_code["INEFFECTIVE_CORRECTIVE_ACTIONS"]["source"] == "effectiveness"
    assert by_code["INEFFECTIVE_CORRECTIVE_ACTIONS"]["value"] == 2
    assert by_code["SAFETY_OCCURRENCES"]["source"] == "safety-occurrence"
    assert by_code["SAFETY_OCCURRENCES"]["value"] == 3
    assert by_code["NEW_CAPABILITIES"]["source"] == "mission-capability"
    assert by_code["NEW_CAPABILITIES"]["value"] == 2
    assert by_code["NEW_AIRCRAFT_TYPES"]["source"] == "mission-aircraft-type"
    assert by_code["NEW_AIRCRAFT_TYPES"]["value"] == 1
    for factor in by_code.values():
        assert factor["source_record"]
        assert factor["source_date"]
        assert factor["rationale"]


def test_item_context_exposes_time_history_recurrence_and_direct_source_links() -> None:
    item = _universe()
    context = _item_context(
        item,
        states=["SCHEDULED", "DEFERRED"],
        global_factors=[],
        history={
            "schedule_titles": ["quality system surveillance"],
            "last_audit_at": "2025-01-01T00:00:00+00:00",
            "days_since_last_audit": 500,
            "finding_count": 7,
            "repeat_requirement_count": 2,
            "repeat_occurrence_count": 3,
        },
        effectiveness={"by_source_id": {"quality-domain-1": 1}},
        safety={"by_universe_source_id": {"quality-domain-1": 1}},
        mission_change={
            "latest_change_at": "2026-08-01T00:00:00+00:00",
            "by_universe_source_id": {"quality-domain-1": {"capability": 1, "aircraft_type": 1}},
        },
    )
    factors = {factor["code"]: factor for factor in context["factors"]}
    assert {
        "REPEATED_DEFERRAL_PRESSURE",
        "TIME_SINCE_LAST_AUDIT",
        "AUDIT_FINDING_HISTORY",
        "REPEAT_AUDIT_FINDINGS",
        "DIRECT_INEFFECTIVE_CORRECTIVE_ACTION",
        "DIRECT_SAFETY_OCCURRENCE",
        "DIRECT_NEW_CAPABILITY",
        "DIRECT_NEW_AIRCRAFT_TYPE",
    }.issubset(factors)
    assert context["audit_history"]["days_since_last_audit"] == 500
    assert factors["TIME_SINCE_LAST_AUDIT"]["source_date"] == "2025-01-01T00:00:00+00:00"
    assert factors["DIRECT_NEW_CAPABILITY"]["source_record"].endswith("quality-domain-1")
    assert context["planning_order"] > 0


def test_item_context_flags_missing_completed_history_without_inventing_a_date() -> None:
    context = _item_context(
        _universe(),
        states=["PLANNED"],
        global_factors=[],
        history={"schedule_titles": ["quality system surveillance"], "days_since_last_audit": None},
    )
    factors = {factor["code"]: factor for factor in context["factors"]}
    assert factors["NO_COMPLETED_AUDIT_HISTORY"]["source"] == "audit-history"
    assert factors["NO_COMPLETED_AUDIT_HISTORY"]["source_date"] is None
    assert "TIME_SINCE_LAST_AUDIT" not in factors
