from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "backend/amodb/apps/reliability/advanced_services.py"


def main() -> None:
    text = SERVICES.read_text(encoding="utf-8")
    import_anchor = "from . import models as legacy\n"
    import_replacement = "from . import models as legacy\nfrom . import internal_collectors\n"
    if import_replacement not in text:
        if import_anchor not in text:
            raise RuntimeError("Reliability internal collector import anchor is missing")
        text = text.replace(import_anchor, import_replacement, 1)

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
    SERVICES.write_text(text[:start] + replacement + text[end + 1 :], encoding="utf-8")
    print("Authoritative internal Reliability collectors wired.")


if __name__ == "__main__":
    main()
