from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


path = ROOT / "backend/amodb/apps/reliability/workpack_integration.py"
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "from pydantic import BaseModel, Field, field_validator\n",
    "from pydantic import AliasChoices, BaseModel, Field, field_validator\n",
    "pydantic imports",
)
text = replace_once(
    text,
    "    deferral_expires_at: Optional[datetime] = None\n",
    "    deferred_until: Optional[datetime] = Field(\n        default=None,\n        validation_alias=AliasChoices(\"deferred_until\", \"deferral_expires_at\"),\n    )\n",
    "deferral field",
)

anchor = '''def _sync_cursor(last_success_at: Optional[datetime]) -> datetime:
    """Overlap internal sync windows so records committed near a cutoff cannot be lost."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    resolved = _as_utc(last_success_at)
    return max(resolved - timedelta(minutes=5), epoch) if resolved else epoch


'''
addition = '''def _sync_cursor(last_success_at: Optional[datetime]) -> datetime:
    """Overlap internal sync windows so records committed near a cutoff cannot be lost."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    resolved = _as_utc(last_success_at)
    return max(resolved - timedelta(minutes=5), epoch) if resolved else epoch


def _latest_datetime(*values: Optional[datetime]) -> Optional[datetime]:
    resolved = [_as_utc(value) for value in values if value is not None]
    return max((value for value in resolved if value is not None), default=None)


def _removal_event_type(reason: Optional[str]) -> str:
    normalized = " ".join((reason or "").upper().replace("_", " ").split())
    unscheduled_markers = ("UNSCHEDULED", "UNPLANNED", "PREMATURE", "FAILURE", "DEFECT")
    if any(marker in normalized for marker in unscheduled_markers):
        return "UNSCHEDULED_REMOVAL"
    scheduled_markers = ("SCHEDULED", "PLANNED", "LIFE LIMIT", "TIME EXPIRED", "TBO")
    if any(marker in normalized for marker in scheduled_markers):
        return "SCHEDULED_REMOVAL"
    # Unknown removals remain unscheduled for conservative Reliability treatment.
    return "UNSCHEDULED_REMOVAL"


def _assert_reference_match(label: str, provided: Optional[Any], authoritative: Optional[Any]) -> None:
    if provided is None or authoritative is None:
        return
    if str(provided) != str(authoritative):
        raise HTTPException(
            status_code=422,
            detail=f"{label} conflicts with the selected authoritative workpack record.",
        )


def _advance_internal_source_after_batch(
    source: domain.ReliabilitySource,
    batch: schemas.ReliabilityIngestionBatchRead,
    *,
    now: datetime,
) -> None:
    # A duplicate-only overlap is a successful sync and must advance the cursor.
    if batch.invalid_count == 0:
        source.last_success_at = now
        source.last_failure_at = None
    source.next_poll_at = now + timedelta(minutes=max(source.poll_interval_minutes or 60, 5))


'''
text = replace_once(text, anchor, addition, "review helpers")

old = '''    occurred_at = _as_utc(task.actual_end) or _as_utc(task.actual_start) or _as_utc(task.updated_at) or _as_utc(task.created_at)
    revision_at = _as_utc(task.updated_at) or _as_utc(task.created_at) or occurred_at
'''
new = '''    occurred_at = _as_utc(task.actual_end) or _as_utc(task.actual_start) or _as_utc(task.updated_at) or _as_utc(task.created_at)
    revision_at = _latest_datetime(
        task.updated_at,
        task.created_at,
        getattr(work_order, "updated_at", None),
        getattr(work_order, "created_at", None),
    ) or occurred_at
'''
text = replace_once(text, old, new, "workpack revision timestamp")

old = '''            or_(work_models.TaskCard.updated_at > cursor, work_models.TaskCard.created_at > cursor),
'''
new = '''            or_(
                work_models.TaskCard.updated_at > cursor,
                work_models.TaskCard.created_at > cursor,
                work_models.WorkOrder.updated_at > cursor,
            ),
'''
text = replace_once(text, old, new, "workpack query revision coverage")

old = '''    reason = (removal.removal_reason or "").upper()
    scheduled = any(token in reason for token in ("SCHEDULED", "PLANNED", "LIFE LIMIT", "TIME EXPIRED", "TBO"))
    event_type = "SCHEDULED_REMOVAL" if scheduled else "UNSCHEDULED_REMOVAL"
'''
new = '''    event_type = _removal_event_type(removal.removal_reason)
    scheduled = event_type == "SCHEDULED_REMOVAL"
'''
text = replace_once(text, old, new, "removal classification")

old = '''        if records:
            results.append(
                services.ingest_batch(
                    db,
                    amo_id=amo_id,
                    source=source,
                    payload=schemas.ReliabilityBatchIngest(
                        records=records,
                        metadata_json={
                            "adapter": "canonical-internal-v1",
                            "source_code": code,
                            "cursor": cursor.isoformat(),
                            "authoritative_tables": source.configuration_json.get("authoritative_tables", []),
                        },
                    ),
                    actor_user_id=actor_user_id,
                )
            )
'''
new = '''        if records:
            result = services.ingest_batch(
                db,
                amo_id=amo_id,
                source=source,
                payload=schemas.ReliabilityBatchIngest(
                    records=records,
                    metadata_json={
                        "adapter": "canonical-internal-v1",
                        "source_code": code,
                        "cursor": cursor.isoformat(),
                        "authoritative_tables": source.configuration_json.get("authoritative_tables", []),
                    },
                ),
                actor_user_id=actor_user_id,
            )
            _advance_internal_source_after_batch(
                source,
                result.batch,
                now=datetime.now(timezone.utc),
            )
            db.commit()
            results.append(result)
'''
text = replace_once(text, old, new, "duplicate-only sync advancement")

old = '''    if payload.task_card_id:
        task = (
            db.query(work_models.TaskCard)
            .filter(work_models.TaskCard.amo_id == amo_id, work_models.TaskCard.id == payload.task_card_id)
            .first()
        )
        if not task:
            raise HTTPException(status_code=422, detail="The selected task card does not exist in this tenant.")
        if work_order and task.work_order_id != work_order.id:
            raise HTTPException(status_code=422, detail="The task card does not belong to the selected work order.")
        work_order = work_order or task.work_order
        values["work_order_id"] = task.work_order_id
        values["aircraft_serial_number"] = values.get("aircraft_serial_number") or task.aircraft_serial_number
        values["ata_chapter"] = values.get("ata_chapter") or task.ata_chapter
        values["component_id"] = values.get("component_id") or task.aircraft_component_id
        values["reference_code"] = values.get("reference_code") or task.task_code
        values["repeat_key"] = values.get("repeat_key") or f"{task.aircraft_serial_number}:{task.ata_chapter or 'UNK'}:{task.task_code or task.title}"[:255]
    if work_order:
        values["aircraft_serial_number"] = values.get("aircraft_serial_number") or work_order.aircraft_serial_number
        values["work_package_ref"] = work_order.work_package_ref
        values["work_order_number"] = work_order.wo_number
        values["check_type"] = work_order.check_type
    if values.get("aircraft_serial_number"):
'''
new = '''    if payload.task_card_id:
        task = (
            db.query(work_models.TaskCard)
            .filter(work_models.TaskCard.amo_id == amo_id, work_models.TaskCard.id == payload.task_card_id)
            .first()
        )
        if not task:
            raise HTTPException(status_code=422, detail="The selected task card does not exist in this tenant.")
        if work_order and task.work_order_id != work_order.id:
            raise HTTPException(status_code=422, detail="The task card does not belong to the selected work order.")
        _assert_reference_match("Aircraft", values.get("aircraft_serial_number"), task.aircraft_serial_number)
        _assert_reference_match("Component", values.get("component_id"), task.aircraft_component_id)
        work_order = work_order or task.work_order
        values["work_order_id"] = task.work_order_id
        values["aircraft_serial_number"] = task.aircraft_serial_number
        values["ata_chapter"] = values.get("ata_chapter") or task.ata_chapter
        values["component_id"] = task.aircraft_component_id or values.get("component_id")
        values["reference_code"] = values.get("reference_code") or task.task_code
        values["repeat_key"] = values.get("repeat_key") or f"{task.aircraft_serial_number}:{task.ata_chapter or 'UNK'}:{task.task_code or task.title}"[:255]
    if work_order:
        _assert_reference_match("Aircraft", values.get("aircraft_serial_number"), work_order.aircraft_serial_number)
        values["aircraft_serial_number"] = work_order.aircraft_serial_number
        values["work_package_ref"] = work_order.work_package_ref
        values["work_order_number"] = work_order.wo_number
        values["check_type"] = work_order.check_type
    component = None
    if values.get("component_id"):
        component = (
            db.query(fleet_models.AircraftComponent)
            .filter(
                fleet_models.AircraftComponent.amo_id == amo_id,
                fleet_models.AircraftComponent.id == values["component_id"],
            )
            .first()
        )
        if not component:
            raise HTTPException(status_code=422, detail="The selected component does not exist in this tenant.")
        _assert_reference_match("Aircraft", values.get("aircraft_serial_number"), component.aircraft_serial_number)
        _assert_reference_match("Part number", values.get("part_number"), component.part_number)
        _assert_reference_match("Component serial number", values.get("component_serial_number"), component.serial_number)
        values["aircraft_serial_number"] = values.get("aircraft_serial_number") or component.aircraft_serial_number
        values["part_number"] = values.get("part_number") or component.part_number
        values["component_serial_number"] = values.get("component_serial_number") or component.serial_number
    if values.get("aircraft_serial_number"):
'''
text = replace_once(text, old, new, "manual authoritative consistency")

path.write_text(text, encoding="utf-8")

# Expand the UI to the complete canonical event taxonomy and align the deferral field name.
view_path = ROOT / "frontend/src/pages/reliability/ReliabilityAdvancedViews.tsx"
view = view_path.read_text(encoding="utf-8")
old_events = '''const EVENT_TYPES = [
  "DEFECT",
  "REPEAT_DEFECT",
  "PILOT_REPORT",
  "TECHNICAL_DELAY",
  "TECHNICAL_CANCELLATION",
  "RETURN_TO_GATE",
  "AIR_TURNBACK",
  "DIVERSION",
  "IN_FLIGHT_SHUTDOWN",
  "MEL_DEFERRAL",
  "CDL_DEFERRAL",
  "UNSCHEDULED_REMOVAL",
  "SHOP_FINDING",
  "NO_FAULT_FOUND",
  "EHM_ALERT",
  "MAINTENANCE_ERROR",
  "SUPPLIER_ESCAPE",
  "SAFETY_EVENT",
];
'''
new_events = '''const EVENT_TYPES = [
  "DEFECT",
  "REPEAT_DEFECT",
  "PILOT_REPORT",
  "CABIN_REPORT",
  "TECHNICAL_DELAY",
  "TECHNICAL_CANCELLATION",
  "RETURN_TO_GATE",
  "AIR_TURNBACK",
  "DIVERSION",
  "IN_FLIGHT_SHUTDOWN",
  "ABORTED_TAKEOFF",
  "MEL_DEFERRAL",
  "CDL_DEFERRAL",
  "UNSCHEDULED_REMOVAL",
  "SCHEDULED_REMOVAL",
  "INSTALLATION",
  "SHOP_FINDING",
  "NO_FAULT_FOUND",
  "OCTM",
  "ECTM",
  "EHM_ALERT",
  "FRACAS",
  "MAINTENANCE_ERROR",
  "SUPPLIER_ESCAPE",
  "SAFETY_EVENT",
  "OTHER",
];
'''
view = replace_once(view, old_events, new_events, "frontend event taxonomy")
view_path.write_text(view, encoding="utf-8")

service_path = ROOT / "frontend/src/services/reliability.ts"
service = service_path.read_text(encoding="utf-8")
service = replace_once(
    service,
    "  deferral_expires_at?: string | null; part_number?: string | null;\n",
    "  deferred_until?: string | null; part_number?: string | null;\n",
    "frontend deferral field",
)
service_path.write_text(service, encoding="utf-8")

# Add focused regression coverage.
test_path = ROOT / "backend/amodb/apps/reliability/tests/test_workpack_integration.py"
test = test_path.read_text(encoding="utf-8")
test += '''\n\ndef test_unscheduled_reason_cannot_be_misclassified_as_scheduled():\n    assert integration._removal_event_type("UNSCHEDULED FAILURE") == "UNSCHEDULED_REMOVAL"\n    assert integration._removal_event_type("Planned TBO change") == "SCHEDULED_REMOVAL"\n    assert integration._removal_event_type(None) == "UNSCHEDULED_REMOVAL"\n\n\ndef test_authoritative_reference_conflicts_are_rejected():\n    with pytest.raises(Exception) as caught:\n        integration._assert_reference_match("Aircraft", "AC-1", "AC-2")\n    assert getattr(caught.value, "status_code", None) == 422\n\n\ndef test_duplicate_only_batch_advances_internal_source_cursor():\n    source = SimpleNamespace(\n        last_success_at=None,\n        last_failure_at=datetime.now(timezone.utc),\n        next_poll_at=None,\n        poll_interval_minutes=60,\n    )\n    batch = SimpleNamespace(invalid_count=0, valid_count=0, duplicate_count=3)\n    now = datetime.now(timezone.utc)\n    integration._advance_internal_source_after_batch(source, batch, now=now)\n    assert source.last_success_at == now\n    assert source.last_failure_at is None\n    assert source.next_poll_at == now + timedelta(minutes=60)\n'''
test_path.write_text(test, encoding="utf-8")

# Remove this one-shot patch machinery from the resulting branch.
(ROOT / "scripts/review_harden_reliability_workpack.py").unlink(missing_ok=True)
(ROOT / ".github/workflows/reliability-workpack-review-hardening.yml").unlink(missing_ok=True)
