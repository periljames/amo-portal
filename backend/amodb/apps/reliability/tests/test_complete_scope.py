from decimal import Decimal

from amodb.apps.reliability import advanced_services as services
from amodb.apps.reliability.models import ReliabilityEventTypeEnum
from amodb.apps.reliability.router import router


def test_canonical_occurrence_taxonomy_is_operationally_complete():
    required = {
        "DEFECT", "REPEAT_DEFECT", "PILOT_REPORT", "TECHNICAL_DELAY",
        "TECHNICAL_CANCELLATION", "RETURN_TO_GATE", "AIR_TURNBACK",
        "DIVERSION", "IN_FLIGHT_SHUTDOWN", "MEL_DEFERRAL", "CDL_DEFERRAL",
        "UNSCHEDULED_REMOVAL", "SHOP_FINDING", "NO_FAULT_FOUND", "EHM_ALERT",
        "MAINTENANCE_ERROR", "SUPPLIER_ESCAPE", "SAFETY_EVENT",
    }
    assert required.issubset({item.value for item in ReliabilityEventTypeEnum})


def test_fracas_transition_graph_requires_closed_loop_sequence():
    assert services.FRACAS_TRANSITIONS["DETECTED"] == {"TRIAGE"}
    assert "ROOT_CAUSE_REVIEW" in services.FRACAS_TRANSITIONS["INVESTIGATION"]
    assert services.FRACAS_TRANSITIONS["IMPLEMENTATION"] == {"EFFECTIVENESS"}
    assert "CLOSED" not in services.FRACAS_TRANSITIONS["IMPLEMENTATION"]
    assert "REOPENED" in services.FRACAS_TRANSITIONS["CLOSED"]


def test_zero_event_confidence_uses_rule_of_three():
    value, lower, upper = services._rate_with_confidence(
        events=0,
        exposure=Decimal("100"),
        multiplier=Decimal("100"),
        method="RATE",
    )
    assert value == Decimal("0E-8")
    assert lower == Decimal("0E-8")
    assert upper == Decimal("3.00000000")


def test_complete_scope_routes_live_on_single_canonical_prefix():
    paths = {route.path for route in router.routes}
    required = {
        "/reliability/sources",
        "/reliability/sources/{source_id}/ingest",
        "/reliability/fracas/cases/{case_id:int}/transition",
        "/reliability/calculation-runs/execute",
        "/reliability/analytics",
        "/reliability/programmes",
        "/reliability/meetings",
        "/reliability/changes",
        "/reliability/handoffs",
        "/reliability/authority-submissions",
        "/reliability/ai-reviews",
        "/reliability/compliance",
    }
    assert required.issubset(paths)
    assert all("/v2" not in path for path in paths)


def test_ai_and_authority_capabilities_are_separate():
    assert "reliability.ai.use" in services.ALL_CAPABILITIES
    assert "reliability.ai.review" in services.ALL_CAPABILITIES
    assert "reliability.authority.submit" in services.ALL_CAPABILITIES
    assert len(services.ALL_CAPABILITIES) == len(set(services.ALL_CAPABILITIES))
