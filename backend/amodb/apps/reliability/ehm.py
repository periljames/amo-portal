from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from amodb.database import WriteSessionLocal
from amodb.utils.identifiers import generate_uuid7
from . import models

EHM_PARSE_VERSION = "1.0"
DEFAULT_HEADER_SKIP_BYTES = 8

ZLIB_HEADERS = {(0x78, 0x01), (0x78, 0x9C), (0x78, 0xDA)}

HEADER_RE = re.compile(
    r"^(?P<type>[A-Za-z ]+?)(?:\[(?P<index>\d+)])?"
    r"(?:\s*\((?P<detail>[^)]+)\))?"
    r"\s*(?:Data\s*)?at\s*\[(?P<timestamp>[^\]]+)\]:"
)

KEY_VALUE_RE = re.compile(r"^\s*(?P<key>[^:=]+?)\s*[:=]\s*(?P<value>.+?)\s*$")

AIRCRAFT_RE = re.compile(r"(aircraft|tail|registration|a/c)\s*[:=]\s*(?P<value>[A-Za-z0-9\\-]+)", re.IGNORECASE)
ENGINE_POS_RE = re.compile(r"(engine\s*pos|engine\s*position|eng\s*pos)\s*[:=]\s*(?P<value>[A-Za-z0-9\\-]+)", re.IGNORECASE)
ENGINE_SERIAL_RE = re.compile(
    r"(engine\s*serial|engine\s*sn|esn|serial\s*number)\s*[:=]\s*(?P<value>[A-Za-z0-9\\-]+)",
    re.IGNORECASE,
)


@dataclass
class ParsedRecordResult:
    record_type: str
    record_index: Optional[int]
    unit_time: Optional[datetime]
    unit_time_raw: Optional[str]
    payload: dict
    raw_text: str


def decode_ehm_payload(data: bytes, header_skip: int = DEFAULT_HEADER_SKIP_BYTES) -> tuple[str, int]:
    if len(data) <= header_skip:
        raise ValueError("EHM log is too small to contain a payload.")

    payload = _attempt_decompress(data, header_skip)
    if payload is not None:
        return payload.decode("utf-8", errors="replace"), header_skip

    for offset in _scan_for_zlib_header(data):
        payload = _attempt_decompress(data, offset)
        if payload is not None:
            return payload.decode("utf-8", errors="replace"), offset

    raise ValueError("Unable to decompress EHM log payload.")


def _attempt_decompress(data: bytes, offset: int) -> Optional[bytes]:
    try:
        return zlib.decompress(data[offset:])
    except zlib.error:
        return None


def _scan_for_zlib_header(data: bytes) -> Iterable[int]:
    for idx in range(len(data) - 1):
        pair = (data[idx], data[idx + 1])
        if pair in ZLIB_HEADERS:
            yield idx


def parse_ehm_records(text: str) -> list[ParsedRecordResult]:
    records: list[ParsedRecordResult] = []
    current_header = None
    current_lines: list[str] = []
    current_fields: dict = {}
    current_detail = None

    def finalize_current() -> None:
        if not current_header:
            return
        header_line = current_lines[0] if current_lines else ""
        record_type = current_header["type"].strip()
        record_index = int(current_header["index"]) if current_header.get("index") else None
        unit_time_raw = current_header.get("timestamp")
        unit_time = _parse_unit_time(unit_time_raw)
        payload = {
            "header": header_line,
            "detail": current_detail,
            "fields": dict(current_fields),
        }
        records.append(
            ParsedRecordResult(
                record_type=record_type,
                record_index=record_index,
                unit_time=unit_time,
                unit_time_raw=unit_time_raw,
                payload=payload,
                raw_text="\n".join(current_lines).strip(),
            )
        )

    for line in text.splitlines():
        header_match = HEADER_RE.match(line)
        if header_match:
            finalize_current()
            current_header = header_match.groupdict()
            current_lines = [line]
            current_fields = {}
            current_detail = current_header.get("detail")
            continue

        if not current_header:
            continue

        current_lines.append(line)

        if line.strip().startswith("$"):
            finalize_current()
            current_header = None
            current_lines = []
            current_fields = {}
            current_detail = None
            continue

        kv_match = KEY_VALUE_RE.match(line)
        if kv_match:
            key = kv_match.group("key").strip()
            value = kv_match.group("value").strip()
            current_fields[key] = value

    finalize_current()
    return records


def extract_identifiers(text: str) -> dict:
    aircraft = None
    engine_position = None
    engine_serial = None
    for line in text.splitlines():
        if aircraft is None:
            match = AIRCRAFT_RE.search(line)
            if match:
                aircraft = match.group("value").strip()
        if engine_position is None:
            match = ENGINE_POS_RE.search(line)
            if match:
                engine_position = match.group("value").strip()
        if engine_serial is None:
            match = ENGINE_SERIAL_RE.search(line)
            if match:
                engine_serial = match.group("value").strip()
        if aircraft and engine_position and engine_serial:
            break
    return {
        "aircraft_serial_number": aircraft,
        "engine_position": engine_position,
        "engine_serial_number": engine_serial,
    }


def _parse_unit_time(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw.strip(), fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_log_in_background(log_id: str) -> None:
    db = WriteSessionLocal()
    try:
        log = db.query(models.EhmRawLog).filter(models.EhmRawLog.id == log_id).first()
        if not log:
            return
        if log.parse_status == models.EhmParseStatusEnum.PARSED and log.parsed_record_count:
            return
        _parse_log(db, log)
    finally:
        db.close()


def parse_log_now(db: Session, log: models.EhmRawLog) -> None:
    _parse_log(db, log)


def _parse_log(db: Session, log: models.EhmRawLog) -> None:
    try:
        data = Path(log.storage_path).read_bytes()
        text, offset = decode_ehm_payload(data)
        identifiers = extract_identifiers(text)
        records = parse_ehm_records(text)
        db.query(models.EhmParsedRecord).filter(models.EhmParsedRecord.raw_log_id == log.id).delete()
        log.raw_text = text
        log.decode_offset = offset
        log.unit_identifiers = identifiers
        log.parse_status = models.EhmParseStatusEnum.PARSED
        log.parse_version = EHM_PARSE_VERSION
        log.parse_error = None
        log.parsed_at = datetime.now(timezone.utc)
        log.parsed_record_count = len(records)
        for record in records:
            db.add(
                models.EhmParsedRecord(
                    id=generate_uuid7(),
                    amo_id=log.amo_id,
                    raw_log_id=log.id,
                    record_type=record.record_type,
                    record_index=record.record_index,
                    unit_time=record.unit_time,
                    unit_time_raw=record.unit_time_raw,
                    payload_json=record.payload,
                    raw_text=record.raw_text,
                    parse_version=EHM_PARSE_VERSION,
                )
            )
        db.commit()
    except Exception as exc:
        log.parse_status = models.EhmParseStatusEnum.FAILED
        log.parse_error = str(exc)
        db.commit()


def ensure_raw_text(db: Session, log: models.EhmRawLog) -> str:
    if log.raw_text:
        return log.raw_text
    data = Path(log.storage_path).read_bytes()
    text, offset = decode_ehm_payload(data)
    log.unit_identifiers = extract_identifiers(text)
    log.raw_text = text
    log.decode_offset = offset
    db.commit()
    return text


def build_snapshot_window(at: Optional[datetime], start: Optional[datetime], end: Optional[datetime]) -> tuple[Optional[datetime], Optional[datetime]]:
    if at:
        window_start = at - timedelta(hours=12)
        window_end = at + timedelta(hours=12)
        return window_start, window_end
    return start, end


def build_snapshot(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    engine_position: str,
    window_start: Optional[datetime],
    window_end: Optional[datetime],
) -> dict:
    query = db.query(models.EhmParsedRecord).join(models.EhmRawLog).filter(
        models.EhmRawLog.amo_id == amo_id,
        models.EhmRawLog.aircraft_serial_number == aircraft_serial_number,
        models.EhmRawLog.engine_position == engine_position,
    )
    if window_start:
        query = query.filter(models.EhmParsedRecord.unit_time >= window_start)
    if window_end:
        query = query.filter(models.EhmParsedRecord.unit_time <= window_end)
    records = query.order_by(models.EhmParsedRecord.unit_time.asc().nulls_last()).all()

    fault_records = [r for r in records if "fault" in r.record_type.lower()]
    sensor_records = [r for r in records if "sensor" in r.record_type.lower()]
    event_records = [r for r in records if "event" in r.record_type.lower()]
    trend_records = [r for r in records if "autotrend" in r.record_type.lower()]
    run_records = [r for r in records if "engine run" in r.record_type.lower()]

    reasons = []
    status = "GOOD"
    if fault_records:
        status = "BAD"
        reasons.append("Fault records present")
    if sensor_records:
        status = "BAD"
        reasons.append("Sensor failure records present")
    if status == "GOOD" and event_records:
        status = "SUSPECT"
        reasons.append("Event detected records present")
    if status == "GOOD":
        for record in records:
            if record.raw_text and ("data loss" in record.raw_text.lower() or "bus power" in record.raw_text.lower()):
                status = "SUSPECT"
                reasons.append("Data loss or bus power interruption noted")
                break

    latest_trend = None
    if trend_records:
        latest_trend = max(trend_records, key=lambda r: r.unit_time or datetime.min.replace(tzinfo=timezone.utc))

    unit_time_start = records[0].unit_time if records else window_start
    unit_time_end = records[-1].unit_time if records else window_end

    return {
        "identity": {
            "aircraft_serial_number": aircraft_serial_number,
            "engine_position": engine_position,
            "unit_time_start": unit_time_start,
            "unit_time_end": unit_time_end,
        },
        "data_quality": {
            "status": status,
            "reasons": reasons,
        },
        "latest_trend": {
            "record_id": latest_trend.id if latest_trend else None,
            "unit_time": latest_trend.unit_time if latest_trend else None,
            "fields": (latest_trend.payload_json or {}).get("fields") if latest_trend else None,
        },
        "engine_runs": [
            {
                "record_id": r.id,
                "unit_time": r.unit_time,
                "fields": (r.payload_json or {}).get("fields"),
            }
            for r in run_records
        ],
        "faults": [
            {
                "record_id": r.id,
                "unit_time": r.unit_time,
                "fields": (r.payload_json or {}).get("fields"),
            }
            for r in fault_records
        ],
        "sensor_failures": [
            {
                "record_id": r.id,
                "unit_time": r.unit_time,
                "fields": (r.payload_json or {}).get("fields"),
            }
            for r in sensor_records
        ],
        "derived_interpretation": {
            "trend_shift_detected": None,
            "trend_shift_reason": "insufficient baseline",
            "candidate_causes": [],
        },
        "evidence": {
            "log_ids": sorted({r.raw_log_id for r in records}),
            "record_ids": [r.id for r in records],
        },
    }
