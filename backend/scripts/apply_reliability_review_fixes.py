from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADVANCED = ROOT / "backend/amodb/apps/reliability/advanced_services.py"
WORKBENCH = ROOT / "backend/amodb/apps/reliability/services.py"
TESTS = ROOT / "backend/amodb/apps/reliability/tests/test_review_regressions.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def function_slice(text: str, name: str, next_name: str) -> tuple[int, int, str]:
    start = text.index(f"def {name}(\n")
    end = text.index(f"\ndef {next_name}(\n", start)
    return start, end, text[start:end]


def patch_advanced_services(text: str) -> str:
    start, end, block = function_slice(text, "_validate_ingestion_record", "_record_external_id")
    insertion = '''    delay_value = payload.get("delay_minutes")
    if delay_value not in (None, ""):
        delay_error = "delay_minutes must be a nonnegative whole number"
        if isinstance(delay_value, bool):
            errors.append(delay_error)
        else:
            try:
                parsed_delay = Decimal(str(delay_value))
            except Exception:
                errors.append(delay_error)
            else:
                if (
                    not parsed_delay.is_finite()
                    or parsed_delay < 0
                    or parsed_delay != parsed_delay.to_integral_value()
                ):
                    errors.append(delay_error)
                else:
                    payload["delay_minutes"] = int(parsed_delay)
'''
    block = replace_once(
        block,
        "    return errors, warnings\n",
        insertion + "    return errors, warnings\n",
        "ingestion validation return",
    )
    text = text[:start] + block + text[end:]

    helper_anchor = "def _rate_with_confidence(\n"
    helpers = '''def _metric_event_contract(
    *,
    method: str,
    configured_event_types: Sequence[str],
) -> Tuple[List[str], Optional[List[str]], Optional[str]]:
    """Resolve numerator and event-denominator semantics for governed metrics."""
    numerator_types = [str(item) for item in configured_event_types]
    if method == "PERCENT":
        return numerator_types, [], "ALL_RELIABILITY_EVENTS"
    if method == "NFF_RATE":
        return ["NO_FAULT_FOUND"], ["UNSCHEDULED_REMOVAL"], "UNSCHEDULED_REMOVALS"
    return numerator_types, None, None


def _advance_metric_schedule(
    metric: domain.ReliabilityMetricDefinition,
    source_cutoff: datetime,
) -> None:
    metric.last_run_at = source_cutoff
    metric.next_run_at = source_cutoff + timedelta(
        minutes=max(int(metric.schedule_interval_minutes or 0), 60)
    )


'''
    if helper_anchor not in text:
        raise RuntimeError("rate helper anchor missing")
    if "def _metric_event_contract(" not in text:
        text = text.replace(helper_anchor, helpers + helper_anchor, 1)

    text = replace_once(
        text,
        '''    if method == "MTBUR":
        value = exposure / Decimal(events) if events else None
        return quantize(value), None, None
    value = Decimal(events) / exposure * multiplier
''',
        '''    if method == "MTBUR":
        value = exposure / Decimal(events) if events else None
        return quantize(value), None, None
    if method in {"PERCENT", "NFF_RATE"}:
        value = Decimal(events) / exposure * multiplier
        return quantize(value), None, None
    value = Decimal(events) / exposure * multiplier
''',
        "method-specific rate calculation",
    )

    start, end, execute = function_slice(text, "execute_metric", "execute_metric_by_id")
    execute = replace_once(
        execute,
        '''    event_types = [str(item) for item in (metric.numerator_event_types or [])]
    query = _scope_event_query(
        db,
        amo_id=amo_id,
        period_start=start,
        period_end=end,
        event_types=event_types,
        scope_type=resolved_scope_type,
        scope_id=resolved_scope_id,
    )
    events = query.count()
    exposure = _exposure(
        db,
        amo_id=amo_id,
        period_start=start,
        period_end=end,
        denominator_type=metric.denominator_type,
        scope_type=resolved_scope_type,
        scope_id=resolved_scope_id,
    )
''',
        '''    configured_event_types = [str(item) for item in (metric.numerator_event_types or [])]
    event_types, denominator_event_types, denominator_source = _metric_event_contract(
        method=metric.method,
        configured_event_types=configured_event_types,
    )
    query = _scope_event_query(
        db,
        amo_id=amo_id,
        period_start=start,
        period_end=end,
        event_types=event_types,
        scope_type=resolved_scope_type,
        scope_id=resolved_scope_id,
    )
    events = query.count()
    if denominator_event_types is None:
        exposure = _exposure(
            db,
            amo_id=amo_id,
            period_start=start,
            period_end=end,
            denominator_type=metric.denominator_type,
            scope_type=resolved_scope_type,
            scope_id=resolved_scope_id,
        )
    else:
        denominator_query = _scope_event_query(
            db,
            amo_id=amo_id,
            period_start=start,
            period_end=end,
            event_types=denominator_event_types,
            scope_type=resolved_scope_type,
            scope_id=resolved_scope_id,
        )
        exposure = Decimal(denominator_query.count())
''',
        "metric numerator and denominator calculation",
    )
    execute = replace_once(
        execute,
        '''        "denominator_type": metric.denominator_type,
        "exposure": str(exposure),
''',
        '''        "denominator_type": denominator_source or metric.denominator_type,
        "configured_denominator_type": metric.denominator_type,
        "denominator_event_types": denominator_event_types,
        "exposure": str(exposure),
''',
        "metric lineage denominator",
    )

    existing_start = execute.index("    existing = (\n")
    alert_start = execute.index("    if alert_severity:\n", existing_start)
    replacement = '''    existing = (
        db.query(domain.ReliabilityCalculationRun)
        .filter(
            domain.ReliabilityCalculationRun.amo_id == amo_id,
            domain.ReliabilityCalculationRun.metric_definition_id == metric.id,
            domain.ReliabilityCalculationRun.scope_type == resolved_scope_type,
            domain.ReliabilityCalculationRun.scope_id == resolved_scope_id,
            domain.ReliabilityCalculationRun.period_start == start,
            domain.ReliabilityCalculationRun.period_end == end,
            domain.ReliabilityCalculationRun.formula_version == metric.formula_version,
        )
        .first()
    )
    if existing:
        run = existing
        run.numerator = Decimal(events)
        run.denominator = exposure
        run.value = value
        run.confidence_lower = lower
        run.confidence_upper = upper
        run.sample_size = events
        run.small_fleet = active_aircraft < 6
        run.status = result_status
        run.source_cutoff_at = source_cutoff
        run.source_lineage_json = lineage
        run.result_hash = result_hash
        run.scheduled = bool(run.scheduled or scheduled)
        if actor_user_id is not None:
            run.run_by_user_id = actor_user_id
        audit_action = "CALCULATION_REFRESHED"
    else:
        run = domain.ReliabilityCalculationRun(
            amo_id=amo_id,
            metric_definition_id=metric.id,
            scope_type=resolved_scope_type,
            scope_id=resolved_scope_id,
            period_start=start,
            period_end=end,
            numerator=Decimal(events),
            denominator=exposure,
            value=value,
            confidence_lower=lower,
            confidence_upper=upper,
            sample_size=events,
            small_fleet=active_aircraft < 6,
            status=result_status,
            formula_version=metric.formula_version,
            source_cutoff_at=source_cutoff,
            source_lineage_json=lineage,
            result_hash=result_hash,
            scheduled=scheduled,
            run_by_user_id=actor_user_id,
        )
        db.add(run)
        audit_action = "CALCULATION_EXECUTED"
    db.flush()
    _advance_metric_schedule(metric, source_cutoff)
'''
    execute = execute[:existing_start] + replacement + execute[alert_start:]
    execute = replace_once(
        execute,
        '''        action="CALCULATION_EXECUTED",
        payload={"metric_id": metric.id, "status": result_status, "result_hash": result_hash, "scheduled": scheduled},
''',
        '''        action=audit_action,
        payload={
            "metric_id": metric.id,
            "status": result_status,
            "result_hash": result_hash,
            "scheduled": scheduled,
            "source_cutoff_at": source_cutoff.isoformat(),
        },
''',
        "calculation audit action",
    )
    text = text[:start] + execute + text[end:]
    return text


def patch_workbench(text: str) -> str:
    anchor = '''    engine_shifts = list_engine_trend_statuses(
        db,
        amo_id=amo_id,
        current_status=models.EngineTrendStatusEnum.SHIFT,
        limit=limit,
    )
'''
    count_query = anchor + '''    engine_shift_count = (
        db.query(func.count(models.EngineTrendStatus.id))
        .filter(
            models.EngineTrendStatus.amo_id == amo_id,
            models.EngineTrendStatus.current_status == models.EngineTrendStatusEnum.SHIFT,
        )
        .scalar()
        or 0
    )
'''
    text = replace_once(text, anchor, count_query, "workbench engine shift list")
    return replace_once(
        text,
        "            engine_shifts=len(engine_shifts),\n",
        "            engine_shifts=engine_shift_count,\n",
        "workbench engine shift summary",
    )


def write_tests() -> None:
    TESTS.write_text(
        '''from datetime import datetime, timezone
from decimal import Decimal
from inspect import getsource
from types import SimpleNamespace

from amodb.apps.reliability import advanced_services
from amodb.apps.reliability import services as workbench_services


def test_negative_delay_is_rejected_before_orm_insertion():
    payload = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ100",
        "delay_minutes": -1,
    }
    errors, _ = advanced_services._validate_ingestion_record(payload)
    assert "delay_minutes must be a nonnegative whole number" in errors


def test_valid_delay_is_normalized_to_an_integer():
    payload = {
        "event_type": "TECHNICAL_DELAY",
        "occurred_at": "2026-08-04T00:00:00Z",
        "flight_number": "KQ100",
        "delay_minutes": "15.0",
    }
    errors, _ = advanced_services._validate_ingestion_record(payload)
    assert not errors
    assert payload["delay_minutes"] == 15


def test_percentage_metric_contract_uses_all_scoped_events_as_denominator():
    numerator, denominator, label = advanced_services._metric_event_contract(
        method="PERCENT",
        configured_event_types=["TECHNICAL_DELAY"],
    )
    assert numerator == ["TECHNICAL_DELAY"]
    assert denominator == []
    assert label == "ALL_RELIABILITY_EVENTS"


def test_nff_metric_contract_uses_unscheduled_removals_as_denominator():
    numerator, denominator, label = advanced_services._metric_event_contract(
        method="NFF_RATE",
        configured_event_types=["DEFECT"],
    )
    assert numerator == ["NO_FAULT_FOUND"]
    assert denominator == ["UNSCHEDULED_REMOVAL"]
    assert label == "UNSCHEDULED_REMOVALS"
    value, lower, upper = advanced_services._rate_with_confidence(
        events=2,
        exposure=Decimal("8"),
        multiplier=Decimal("100"),
        method="NFF_RATE",
    )
    assert value == Decimal("25.00000000")
    assert lower is None
    assert upper is None


def test_subdaily_schedule_advances_after_each_execution():
    metric = SimpleNamespace(schedule_interval_minutes=60, last_run_at=None, next_run_at=None)
    cutoff = datetime(2026, 8, 4, 5, 0, tzinfo=timezone.utc)
    advanced_services._advance_metric_schedule(metric, cutoff)
    assert metric.last_run_at == cutoff
    assert metric.next_run_at == datetime(2026, 8, 4, 6, 0, tzinfo=timezone.utc)


def test_existing_period_result_is_refreshed_instead_of_returned_early():
    source = getsource(advanced_services.execute_metric)
    assert "if existing:" in source
    assert "run.source_cutoff_at = source_cutoff" in source
    assert 'audit_action = "CALCULATION_REFRESHED"' in source
    assert "if existing:\n        return existing" not in source


def test_workbench_total_engine_shift_count_is_not_page_limited():
    source = getsource(workbench_services.build_reliability_workbench)
    assert "engine_shift_count = (" in source
    assert "func.count(models.EngineTrendStatus.id)" in source
    assert "engine_shifts=engine_shift_count" in source
    assert "engine_shifts=len(engine_shifts)" not in source
''',
        encoding="utf-8",
    )


def main() -> None:
    ADVANCED.write_text(
        patch_advanced_services(ADVANCED.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    WORKBENCH.write_text(
        patch_workbench(WORKBENCH.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    write_tests()
    print("Reliability review corrections applied.")


if __name__ == "__main__":
    main()
