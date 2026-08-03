from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RELIABILITY = ROOT / "backend/amodb/apps/reliability"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def patch_models() -> None:
    path = RELIABILITY / "models.py"
    text = path.read_text(encoding="utf-8")
    enum_pattern = re.compile(
        r"class ReliabilityEventTypeEnum\(str, Enum\):\n(?:    .*\n)+?\n\nclass ReliabilitySeverityEnum",
        re.MULTILINE,
    )
    enum_replacement = '''class ReliabilityEventTypeEnum(str, Enum):
    DEFECT = "DEFECT"
    REPEAT_DEFECT = "REPEAT_DEFECT"
    PILOT_REPORT = "PILOT_REPORT"
    CABIN_REPORT = "CABIN_REPORT"
    TECHNICAL_DELAY = "TECHNICAL_DELAY"
    TECHNICAL_CANCELLATION = "TECHNICAL_CANCELLATION"
    RETURN_TO_GATE = "RETURN_TO_GATE"
    AIR_TURNBACK = "AIR_TURNBACK"
    DIVERSION = "DIVERSION"
    IN_FLIGHT_SHUTDOWN = "IN_FLIGHT_SHUTDOWN"
    ABORTED_TAKEOFF = "ABORTED_TAKEOFF"
    MEL_DEFERRAL = "MEL_DEFERRAL"
    CDL_DEFERRAL = "CDL_DEFERRAL"
    UNSCHEDULED_REMOVAL = "UNSCHEDULED_REMOVAL"
    SCHEDULED_REMOVAL = "SCHEDULED_REMOVAL"
    REMOVAL = "REMOVAL"
    INSTALLATION = "INSTALLATION"
    SHOP_FINDING = "SHOP_FINDING"
    NO_FAULT_FOUND = "NO_FAULT_FOUND"
    OCTM = "OCTM"
    ECTM = "ECTM"
    EHM_ALERT = "EHM_ALERT"
    FRACAS = "FRACAS"
    MAINTENANCE_ERROR = "MAINTENANCE_ERROR"
    SUPPLIER_ESCAPE = "SUPPLIER_ESCAPE"
    SAFETY_EVENT = "SAFETY_EVENT"
    OTHER = "OTHER"


class ReliabilitySeverityEnum'''
    text, replacements = enum_pattern.subn(enum_replacement, text, count=1)
    if replacements != 1:
        raise RuntimeError("ReliabilityEventTypeEnum block not found")

    old_args = '''    __table_args__ = (
        Index("ix_reliability_events_amo_type", "amo_id", "event_type"),
        Index("ix_reliability_events_aircraft_date", "aircraft_serial_number", "occurred_at"),
    )
'''
    new_args = '''    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "source_system",
            "source_record_id",
            name="uq_reliability_event_source_record",
        ),
        Index("ix_reliability_events_amo_type", "amo_id", "event_type"),
        Index("ix_reliability_events_aircraft_date", "aircraft_serial_number", "occurred_at"),
        Index("ix_reliability_events_repeat_key", "amo_id", "repeat_key"),
        Index("ix_reliability_events_component_identity", "amo_id", "part_number", "component_serial_number"),
        CheckConstraint("delay_minutes IS NULL OR delay_minutes >= 0", name="ck_reliability_event_delay_nonnegative"),
    )
'''
    text = replace_once(text, old_args, new_args, "ReliabilityEvent table args")

    old_columns = '''    reference_code = Column(String(64), nullable=True, index=True)
    source_system = Column(String(64), nullable=True)
    description = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
'''
    new_columns = '''    reference_code = Column(String(64), nullable=True, index=True)
    source_system = Column(String(64), nullable=True, index=True)
    source_record_id = Column(String(255), nullable=True, index=True)
    source_payload_hash = Column(String(64), nullable=True, index=True)
    validation_status = Column(String(24), nullable=False, default="VALID", index=True)
    validation_errors = Column(JSON, nullable=False, default=list)
    provenance_json = Column(JSON, nullable=False, default=dict)

    operation_stage = Column(String(40), nullable=True, index=True)
    flight_number = Column(String(24), nullable=True, index=True)
    origin_station = Column(String(8), nullable=True)
    destination_station = Column(String(8), nullable=True)
    delay_minutes = Column(Integer, nullable=True)
    mel_reference = Column(String(80), nullable=True, index=True)
    cdl_reference = Column(String(80), nullable=True, index=True)
    deferral_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    part_number = Column(String(80), nullable=True, index=True)
    component_serial_number = Column(String(80), nullable=True, index=True)
    confirmed_failure = Column(Boolean, nullable=True)
    repeat_key = Column(String(255), nullable=True, index=True)

    description = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
'''
    text = replace_once(text, old_columns, new_columns, "ReliabilityEvent canonical columns")
    path.write_text(text, encoding="utf-8")


def patch_schemas() -> None:
    path = RELIABILITY / "schemas.py"
    text = path.read_text(encoding="utf-8")
    if "from typing import Any, Dict, Literal" not in text:
        text = text.replace(
            "from typing import Literal, Optional, List",
            "from typing import Any, Dict, Literal, Optional, List",
            1,
        )
    old = '''class ReliabilityEventCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    engine_position: Optional[str] = None
    component_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: ReliabilityEventTypeEnum
    severity: Optional[ReliabilitySeverityEnum] = None
    ata_chapter: Optional[str] = None
    reference_code: Optional[str] = None
    source_system: Optional[str] = None
    description: Optional[str] = None
    operator_event_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
'''
    new = '''class ReliabilityEventCreate(BaseModel):
    aircraft_serial_number: Optional[str] = None
    engine_position: Optional[str] = None
    component_id: Optional[int] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    event_type: ReliabilityEventTypeEnum
    severity: Optional[ReliabilitySeverityEnum] = None
    ata_chapter: Optional[str] = None
    reference_code: Optional[str] = None
    source_system: Optional[str] = None
    source_record_id: Optional[str] = None
    source_payload_hash: Optional[str] = None
    validation_status: str = "VALID"
    validation_errors: List[Dict[str, Any]] = Field(default_factory=list)
    provenance_json: Dict[str, Any] = Field(default_factory=dict)
    operation_stage: Optional[str] = None
    flight_number: Optional[str] = None
    origin_station: Optional[str] = None
    destination_station: Optional[str] = None
    delay_minutes: Optional[int] = Field(default=None, ge=0)
    mel_reference: Optional[str] = None
    cdl_reference: Optional[str] = None
    deferral_expires_at: Optional[datetime] = None
    part_number: Optional[str] = None
    component_serial_number: Optional[str] = None
    confirmed_failure: Optional[bool] = None
    repeat_key: Optional[str] = None
    description: Optional[str] = None
    operator_event_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
'''
    text = replace_once(text, old, new, "ReliabilityEventCreate")
    path.write_text(text, encoding="utf-8")


def patch_router() -> None:
    path = RELIABILITY / "router.py"
    text = path.read_text(encoding="utf-8")
    marker = "# Canonical advanced Reliability routes"
    if marker not in text:
        text = text.rstrip() + '''


# Canonical advanced Reliability routes
from .advanced_router import router as advanced_reliability_router  # noqa: E402

router.include_router(advanced_reliability_router)
'''
    path.write_text(text, encoding="utf-8")


def patch_package() -> None:
    path = RELIABILITY / "__init__.py"
    text = path.read_text(encoding="utf-8")
    if "advanced_models" not in text:
        text = text.rstrip() + "\nfrom . import advanced_models  # noqa: E402,F401\n"
    path.write_text(text, encoding="utf-8")


def patch_alembic_env() -> None:
    path = ROOT / "backend/amodb/alembic/env.py"
    text = path.read_text(encoding="utf-8")
    anchor = "from amodb.apps.reliability import models as reliability_models  # noqa: F401, E402\n"
    addition = anchor + "from amodb.apps.reliability import advanced_models as reliability_advanced_models  # noqa: F401, E402\n"
    if "reliability_advanced_models" not in text:
        text = replace_once(text, anchor, addition, "Alembic Reliability model import")

    if "def _reliability_include_object" not in text:
        include_helper = '''

_RELIABILITY_TABLES = {
    "reliability_events",
    "reliability_sources",
    "reliability_ingestion_batches",
    "reliability_ingestion_records",
    "reliability_data_quality_issues",
    "reliability_operational_interruptions",
    "reliability_fracas_lifecycles",
    "reliability_fracas_evidence",
    "reliability_fracas_stage_events",
    "reliability_effectiveness_reviews",
    "reliability_programmes",
    "reliability_programme_versions",
    "reliability_metric_definitions",
    "reliability_threshold_versions",
    "reliability_calculation_runs",
    "reliability_review_meetings",
    "reliability_meeting_decisions",
    "reliability_change_proposals",
    "reliability_handoffs",
    "reliability_authority_submissions",
    "reliability_audit_events",
    "reliability_ai_reviews",
}


def _reliability_include_object(obj, name, type_, reflected, compare_to):
    if os.getenv("RELIABILITY_AUTOGENERATE_ONLY", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return True
    if type_ == "table":
        return name in _RELIABILITY_TABLES
    table = getattr(obj, "table", None) or getattr(compare_to, "table", None)
    return table is not None and table.name in _RELIABILITY_TABLES
'''
        text = text.replace("# Target metadata for 'autogenerate'\ntarget_metadata = Base.metadata\n", include_helper + "\n# Target metadata for 'autogenerate'\ntarget_metadata = Base.metadata\n", 1)

    text = text.replace(
        "        compare_server_default=True,\n    )",
        "        compare_server_default=True,\n        include_object=_reliability_include_object,\n    )",
    )
    path.write_text(text, encoding="utf-8")


def patch_main() -> None:
    path = ROOT / "backend/amodb/main.py"
    text = path.read_text(encoding="utf-8")
    import_anchor = "from .apps.reliability.router import router as reliability_router\n"
    if "advanced_scheduler" not in text:
        text = replace_once(
            text,
            import_anchor,
            import_anchor + "from .apps.reliability import advanced_scheduler as reliability_scheduler\n",
            "main Reliability scheduler import",
        )
    startup_anchor = '''def _schema_preflight() -> None:
    app.state.is_shutting_down = False
    _enforce_schema_head_sync_if_configured()
    realtime_gateway.connect()
'''
    startup_replacement = '''def _schema_preflight() -> None:
    app.state.is_shutting_down = False
    _enforce_schema_head_sync_if_configured()
    realtime_gateway.connect()
    reliability_scheduler.start_reliability_scheduler()
'''
    if "start_reliability_scheduler()" not in text:
        text = replace_once(text, startup_anchor, startup_replacement, "Reliability scheduler startup")
    shutdown_anchor = '''    _run_shutdown_step("realtime-disconnect", realtime_gateway.disconnect, timeout_seconds)

    if os.getenv("API_USAGE_FLUSH_ON_SHUTDOWN", "false").lower() in {"1", "true", "yes", "on"}:
'''
    shutdown_replacement = '''    _run_shutdown_step("reliability-scheduler", reliability_scheduler.stop_reliability_scheduler, timeout_seconds)
    _run_shutdown_step("realtime-disconnect", realtime_gateway.disconnect, timeout_seconds)

    if os.getenv("API_USAGE_FLUSH_ON_SHUTDOWN", "false").lower() in {"1", "true", "yes", "on"}:
'''
    if '"reliability-scheduler"' not in text:
        text = replace_once(text, shutdown_anchor, shutdown_replacement, "Reliability scheduler shutdown")
    path.write_text(text, encoding="utf-8")


def patch_advanced_services() -> None:
    path = RELIABILITY / "advanced_services.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '''        return [str(item) for item in db.query(fleet_models.Aircraft.serial_number).filter(
            fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True)
        ).scalars().all()]''',
        '''        return [
            str(row[0])
            for row in db.query(fleet_models.Aircraft.serial_number)
            .filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True))
            .all()
        ]''',
    )
    text = text.replace(
        '''    return [str(item) for item in db.query(column).filter(
        legacy.ReliabilityEvent.amo_id == amo_id, column.isnot(None)
    ).distinct().scalars().all()]''',
        '''    return [
        str(row[0])
        for row in db.query(column)
        .filter(legacy.ReliabilityEvent.amo_id == amo_id, column.isnot(None))
        .distinct()
        .all()
    ]''',
    )
    text = text.replace(
        '''        scope_ids = [str(item) for item in db.query(fleet_models.Aircraft.serial_number).filter(
            fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True)
        ).scalars().all()]''',
        '''        scope_ids = [
            str(row[0])
            for row in db.query(fleet_models.Aircraft.serial_number)
            .filter(fleet_models.Aircraft.amo_id == amo_id, fleet_models.Aircraft.is_active.is_(True))
            .all()
        ]''',
    )
    text = text.replace(
        '''        scope_ids = [str(item) for item in db.query(column).filter(
            legacy.ReliabilityEvent.amo_id == amo_id, column.isnot(None)
        ).distinct().scalars().all()]''',
        '''        scope_ids = [
            str(row[0])
            for row in db.query(column)
            .filter(legacy.ReliabilityEvent.amo_id == amo_id, column.isnot(None))
            .distinct()
            .all()
        ]''',
    )
    path.write_text(text, encoding="utf-8")


def write_tests() -> None:
    path = RELIABILITY / "tests/test_complete_scope.py"
    path.write_text('''from decimal import Decimal

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
''', encoding="utf-8")


def main() -> None:
    patch_models()
    patch_schemas()
    patch_router()
    patch_package()
    patch_alembic_env()
    patch_main()
    patch_advanced_services()
    write_tests()
    print("Canonical Reliability backend completion patch applied.")


if __name__ == "__main__":
    main()
