#!/usr/bin/env python3
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from amodb.database import WriteSessionLocal
from amodb.apps.accounts.models import AMO, User
from amodb.apps.fleet.models import Aircraft
from amodb.apps.work.models import WorkOrder, WorkOrderStatusEnum, WorkOrderTypeEnum
from amodb.apps.technical_records import models as tr_models


def run() -> None:
    db = WriteSessionLocal()
    try:
        amo = db.query(AMO).filter(AMO.login_slug != "system").order_by(AMO.created_at.asc()).first()
        if not amo:
            raise RuntimeError("No tenant AMO found. Seed base AMO/users first.")

        user = db.query(User).filter(User.amo_id == amo.id).first()
        if not user:
            raise RuntimeError("No tenant user found.")

        aircraft1 = db.query(Aircraft).filter_by(amo_id=amo.id, serial_number="TR-AC-001").first()
        if not aircraft1:
            aircraft1 = Aircraft(
                amo_id=amo.id,
                serial_number="TR-AC-001",
                registration="5Y-TR1",
                template="B737",
                make="Boeing",
                model="737-800",
                operator="Demo Operator",
                status="ACTIVE",
            )
            db.add(aircraft1)

        aircraft2 = db.query(Aircraft).filter_by(amo_id=amo.id, serial_number="TR-AC-002").first()
        if not aircraft2:
            aircraft2 = Aircraft(
                amo_id=amo.id,
                serial_number="TR-AC-002",
                registration="5Y-TR2",
                template="DHC8",
                make="De Havilland",
                model="Dash 8",
                operator="Demo Operator",
                status="ACTIVE",
            )
            db.add(aircraft2)
        db.flush()

        wo = db.query(WorkOrder).filter_by(amo_id=amo.id, wo_number="WO-TR-001").first()
        if not wo:
            wo = WorkOrder(
                amo_id=amo.id,
                wo_number="WO-TR-001",
                aircraft_serial_number=aircraft1.serial_number,
                description="Technical records seeded maintenance event",
                wo_type=WorkOrderTypeEnum.UNSCHEDULED,
                status=WorkOrderStatusEnum.CLOSED,
                open_date=date.today() - timedelta(days=3),
                closed_date=date.today() - timedelta(days=1),
                created_by_user_id=user.id,
            )
            db.add(wo)
            db.flush()

        util_1 = tr_models.AircraftUtilisation(
            amo_id=amo.id,
            tail_id=aircraft1.serial_number,
            entry_date=date.today() - timedelta(days=2),
            hours=5.2,
            cycles=2,
            source="Manual",
            created_by_user_id=user.id,
        )
        util_conflict = tr_models.AircraftUtilisation(
            amo_id=amo.id,
            tail_id=aircraft1.serial_number,
            entry_date=date.today() - timedelta(days=2),
            hours=5.3,
            cycles=2,
            source="Import",
            conflict_flag=True,
            correction_reason="Imported duplicate for conflict demo",
            created_by_user_id=user.id,
        )
        if db.query(tr_models.AircraftUtilisation).filter_by(amo_id=amo.id, tail_id=aircraft1.serial_number).count() == 0:
            db.add_all([util_1, util_conflict])

        if not db.query(tr_models.Deferral).filter_by(amo_id=amo.id, defect_ref="DEF-TR-001").first():
            db.add(tr_models.Deferral(
                amo_id=amo.id,
                tail_id=aircraft1.serial_number,
                defect_ref="DEF-TR-001",
                deferral_type="MEL",
                deferred_at=datetime.now(UTC) - timedelta(days=1),
                expiry_at=datetime.now(UTC) + timedelta(days=2),
                status="Open",
                linked_wo_id=wo.id,
            ))

        ad = db.query(tr_models.AirworthinessItem).filter_by(amo_id=amo.id, item_type="AD", reference="AD-2024-DEMO").first()
        if not ad:
            ad = tr_models.AirworthinessItem(
                amo_id=amo.id,
                item_type="AD",
                reference="AD-2024-DEMO",
                applicability_json={"tails": [aircraft1.serial_number]},
                status="Complied",
                next_due_date=date.today() + timedelta(days=90),
            )
            db.add(ad)
            db.flush()
            db.add(tr_models.AirworthinessComplianceEvent(
                amo_id=amo.id,
                item_id=ad.id,
                tail_id=aircraft1.serial_number,
                performed_at=datetime.now(UTC) - timedelta(days=1),
                method_text="Inspection + record review",
                linked_wo_id=wo.id,
                evidence_asset_ids=["evidence://ad-demo-1"],
                next_due_date=date.today() + timedelta(days=90),
            ))

        if not db.query(tr_models.MaintenanceRecord).filter_by(amo_id=amo.id, linked_wo_id=wo.id).first():
            db.add(tr_models.MaintenanceRecord(
                amo_id=amo.id,
                tail_id=aircraft1.serial_number,
                performed_at=datetime.now(UTC) - timedelta(days=1),
                description="Close-out maintenance event",
                reference_data_text="AMM 27-10-00 Rev 32",
                certifying_user_id=user.id,
                outcome="Released to service",
                linked_wo_id=wo.id,
                linked_wp_id="WP-TR-001",
                evidence_asset_ids=["evidence://mr-demo-1"],
            ))

        if not db.query(tr_models.ExceptionQueueItem).filter_by(amo_id=amo.id, ex_type="UnmatchedCRS").first():
            db.add(tr_models.ExceptionQueueItem(
                amo_id=amo.id,
                ex_type="UnmatchedCRS",
                object_type="CRS",
                object_id="CRS-UNMATCHED-DEMO",
                summary="CRS exists but task linkage is missing",
                created_by_user_id=user.id,
            ))

        if not db.query(tr_models.ExceptionQueueItem).filter_by(amo_id=amo.id, ex_type="UtilisationConflict").first():
            db.add(tr_models.ExceptionQueueItem(
                amo_id=amo.id,
                ex_type="UtilisationConflict",
                object_type="Aircraft",
                object_id=aircraft1.serial_number,
                summary="Duplicate utilisation posting detected",
                created_by_user_id=user.id,
            ))

        if not db.query(tr_models.TechnicalRecordSetting).filter_by(amo_id=amo.id).first():
            db.add(tr_models.TechnicalRecordSetting(amo_id=amo.id, record_retention_years=5))

        db.commit()
        print(f"Technical records demo data seeded for tenant {amo.login_slug} ({amo.id})")
    finally:
        db.close()


if __name__ == "__main__":
    run()
