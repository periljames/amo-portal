from __future__ import annotations

from datetime import datetime, timezone
import zlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.database import Base
from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.reliability import ehm as ehm_services
from amodb.apps.reliability import models as reliability_models


def _sample_payload() -> bytes:
    text = """AutoTrend[0] Data at [03/10/2025 12:30:45.12]:
Regime: Cruise
Avg N1: 95.2
Max ITT: 800
$376B
Engine Run[0] at [03/10/2025 12:35:45.12]:
Run Duration: 00:05:00
Min Battery: 24.1
Max ITT: 820
$376B
Fault (Xcptn: 123) at [03/10/2025 12:40:45.12]:
Code: F123
Description: Overtemp
$376B
Sensor failure at [03/10/2025 12:45:45.12]:
Sensor: T5
$376B
Event detected at [03/10/2025 12:50:45.12]:
Event: Data Loss
$376B
"""
    payload = zlib.compress(text.encode("utf-8"))
    return b"\x00" * 8 + payload


def test_decode_ehm_payload():
    data = _sample_payload()
    text, offset = ehm_services.decode_ehm_payload(data)
    assert "AutoTrend[0]" in text
    assert "Engine Run[0]" in text
    assert offset == 8


def test_parse_ehm_records():
    data = _sample_payload()
    text, _ = ehm_services.decode_ehm_payload(data)
    records = ehm_services.parse_ehm_records(text)
    record_types = [record.record_type for record in records]
    assert record_types == [
        "AutoTrend",
        "Engine Run",
        "Fault",
        "Sensor failure",
        "Event detected",
    ]
    assert records[0].unit_time is not None


def test_snapshot_data_quality_flags_faults():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            account_models.AMO.__table__,
            fleet_models.Aircraft.__table__,
            reliability_models.EhmRawLog.__table__,
            reliability_models.EhmParsedRecord.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        amo = account_models.AMO(
            amo_code="AMO-TEST",
            name="Test AMO",
            login_slug="test-amo",
        )
        session.add(amo)
        session.flush()
        aircraft = fleet_models.Aircraft(
            serial_number="AC-1",
            registration="5Y-AC1",
            amo_id=amo.id,
        )
        session.add(aircraft)
        session.flush()

        log = reliability_models.EhmRawLog(
            id="log-1",
            amo_id=amo.id,
            aircraft_serial_number=aircraft.serial_number,
            engine_position="LH",
            storage_path="/tmp/ehm.log",
            size_bytes=123,
            sha256_hash="abc",
            parse_status=reliability_models.EhmParseStatusEnum.PARSED,
        )
        session.add(log)
        session.flush()
        session.add(
            reliability_models.EhmParsedRecord(
                id="rec-1",
                amo_id=amo.id,
                raw_log_id=log.id,
                record_type="Fault",
                unit_time=datetime(2025, 3, 10, 12, 40, tzinfo=timezone.utc),
                payload_json={"fields": {"Code": "F123"}},
                raw_text="Fault (Xcptn: 123) at [03/10/2025 12:40:45.12]:",
            )
        )
        session.commit()

        snapshot = ehm_services.build_snapshot(
            session,
            amo_id=amo.id,
            aircraft_serial_number=aircraft.serial_number,
            engine_position="LH",
            window_start=None,
            window_end=None,
        )

        assert snapshot["data_quality"]["status"] == "BAD"
        assert snapshot["faults"]
    finally:
        session.close()
