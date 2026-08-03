from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "backend/amodb/apps/reliability/advanced_services.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = SERVICES.read_text(encoding="utf-8")
    import_anchor = "from . import models as legacy\n"
    import_replacement = "from . import models as legacy\nfrom . import internal_collectors\n"
    if import_replacement not in text:
        text = replace_once(
            text,
            import_anchor,
            import_replacement,
            "internal collector import anchor",
        )

    start = text.index("def harvest_internal_sources(\n")
    end = text.index("\ndef ensure_fracas_lifecycle(\n", start)
    replacement = '''def harvest_internal_sources(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str] = None,
) -> List[schemas.ReliabilityIngestionResult]:
    results: List[schemas.ReliabilityIngestionResult] = []
    supported_internal_types = {
        "TECH_LOG",
        "MAINTENANCE",
        "TECH_RECORDS",
        "EHM",
        "QMS",
        "PROCUREMENT",
    }
    sources = (
        db.query(domain.ReliabilitySource)
        .filter(
            domain.ReliabilitySource.amo_id == amo_id,
            domain.ReliabilitySource.status == "ACTIVE",
            domain.ReliabilitySource.transport == "INTERNAL",
        )
        .all()
    )
    for source in sources:
        cursor = source.last_success_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        records = internal_collectors.collect_internal_records(
            db,
            source_type=source.source_type,
            amo_id=amo_id,
            cursor=cursor,
            limit=2000,
        )
        if source.source_type == "EHM":
            shifts = (
                db.query(legacy.EngineTrendStatus)
                .filter(
                    legacy.EngineTrendStatus.amo_id == amo_id,
                    legacy.EngineTrendStatus.current_status == legacy.EngineTrendStatusEnum.SHIFT,
                    legacy.EngineTrendStatus.updated_at > cursor,
                )
                .order_by(legacy.EngineTrendStatus.updated_at.asc())
                .limit(2000)
                .all()
            )
            records.extend(
                {
                    "external_id": f"ENGINE_SHIFT:{shift.id}:{shift.updated_at.isoformat()}",
                    "event_type": "EHM_ALERT",
                    "occurred_at": shift.updated_at.isoformat(),
                    "aircraft_serial_number": shift.aircraft_serial_number,
                    "engine_position": shift.engine_position,
                    "severity": "HIGH",
                    "description": f"Engine trend shift for {shift.engine_position}",
                }
                for shift in shifts
            )

        if records:
            results.append(
                ingest_batch(
                    db,
                    amo_id=amo_id,
                    source=source,
                    payload=schemas.ReliabilityBatchIngest(
                        records=records,
                        metadata_json={
                            "adapter": "internal-authoritative",
                            "source_type": source.source_type,
                            "cursor": cursor.isoformat(),
                        },
                    ),
                    actor_user_id=actor_user_id,
                )
            )
            continue

        now = utcnow()
        if source.source_type in supported_internal_types:
            source.last_success_at = now
        else:
            source.last_failure_at = now
            existing_issue = (
                db.query(domain.ReliabilityDataQualityIssue)
                .filter(
                    domain.ReliabilityDataQualityIssue.amo_id == amo_id,
                    domain.ReliabilityDataQualityIssue.source_id == source.id,
                    domain.ReliabilityDataQualityIssue.issue_code == "INTERNAL_ADAPTER_NOT_CONFIGURED",
                    domain.ReliabilityDataQualityIssue.status.in_(["OPEN", "REOPENED"]),
                )
                .first()
            )
            if not existing_issue:
                _create_data_issue(
                    db,
                    amo_id=amo_id,
                    source_id=source.id,
                    batch_id=None,
                    record_id=None,
                    code="INTERNAL_ADAPTER_NOT_CONFIGURED",
                    severity="HIGH",
                    message=(
                        f"{source.source_type} has no authoritative internal adapter; "
                        "configure a PUSH/POLL connector instead of reporting healthy data."
                    ),
                    details={"source_type": source.source_type, "transport": source.transport},
                )
        if source.poll_interval_minutes:
            source.next_poll_at = now + timedelta(minutes=source.poll_interval_minutes)
        db.commit()
    return results

'''
    text = text[:start] + replacement + text[end + 1 :]

    old_data_sources = '''            data_sources_json=[
                {"type": "TECH_LOG", "required": True},
                {"type": "FLIGHT_OPERATIONS", "required": True},
                {"type": "MAINTENANCE", "required": True},
                {"type": "EHM", "required": False},
            ],'''
    new_data_sources = '''            data_sources_json=[
                {"type": "TECH_LOG", "transport": "INTERNAL", "required": True},
                {"type": "MAINTENANCE", "transport": "INTERNAL", "required": True},
                {"type": "TECH_RECORDS", "transport": "INTERNAL", "required": True},
                {"type": "FLIGHT_OPERATIONS", "transport": "PUSH", "required": True},
                {"type": "MEL_CDL", "transport": "PUSH", "required": False},
                {"type": "EHM", "transport": "INTERNAL", "required": False},
                {"type": "QMS", "transport": "INTERNAL", "required": False},
                {"type": "PROCUREMENT", "transport": "INTERNAL", "required": False},
                {"type": "COMPONENT_SHOP", "transport": "PUSH", "required": False},
                {"type": "SMS", "transport": "PUSH", "required": False},
            ],'''
    text = replace_once(
        text,
        old_data_sources,
        new_data_sources,
        "programme data-source contract",
    )

    old_specs = '''    source_specs = [
        ("TECHLOG-INTERNAL", "Maintenance defect task cards", "TECH_LOG", "INTERNAL", 60),
        ("OPS-PUSH", "Flight operations interruptions", "FLIGHT_OPERATIONS", "PUSH", None),
        ("MEL-CDL-PUSH", "MEL and CDL deferrals", "MEL_CDL", "PUSH", None),
        ("EHM-INTERNAL", "Engine trend shifts", "EHM", "INTERNAL", 60),
        ("SHOP-PUSH", "Component shop findings", "COMPONENT_SHOP", "PUSH", None),
        ("QMS-PUSH", "Quality findings and supplier escapes", "QMS", "PUSH", None),
        ("SMS-PUSH", "Safety occurrence linkage", "SMS", "PUSH", None),
        ("PROCUREMENT-PUSH", "Supplier and batch performance", "PROCUREMENT", "PUSH", None),
    ]'''
    new_specs = '''    source_specs = [
        ("TECHLOG-INTERNAL", "Authoritative technical-log defect reports", "TECH_LOG", "INTERNAL", 60),
        ("MAINT-INTERNAL", "Maintenance defect, non-routine and deferred task cards", "MAINTENANCE", "INTERNAL", 60),
        ("TECHRECORDS-INTERNAL", "Aircraft component configuration events", "TECH_RECORDS", "INTERNAL", 60),
        ("OPS-PUSH", "Flight operations interruptions", "FLIGHT_OPERATIONS", "PUSH", None),
        ("MEL-CDL-PUSH", "External MEL and CDL control feed", "MEL_CDL", "PUSH", None),
        ("EHM-INTERNAL", "Engine trend shifts", "EHM", "INTERNAL", 60),
        ("QMS-INTERNAL", "Reliability corrective-action records", "QMS", "INTERNAL", 60),
        ("PROCUREMENT-INTERNAL", "Receiving inspection escapes and quality holds", "PROCUREMENT", "INTERNAL", 60),
        ("SHOP-PUSH", "Component shop findings", "COMPONENT_SHOP", "PUSH", None),
        ("SMS-PUSH", "Safety occurrence linkage", "SMS", "PUSH", None),
    ]'''
    text = replace_once(text, old_specs, new_specs, "Reliability bootstrap source specifications")

    SERVICES.write_text(text, encoding="utf-8")
    print("Authoritative internal Reliability collectors and bootstrap contracts wired.")


if __name__ == "__main__":
    main()
