import os
from datetime import datetime

from sqlalchemy.orm import Session

from amodb.database import SessionLocal
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.apps.finance import services as finance_services

TENANT_ID = os.getenv("AMODB_TENANT_ID")
MODULE_CODE = os.getenv("AMODB_MODULE_CODE", "finance_inventory")
STATUS = os.getenv("AMODB_MODULE_STATUS", "ENABLED")
PLAN_CODE = os.getenv("AMODB_MODULE_PLAN_CODE")
EFFECTIVE_FROM = os.getenv("AMODB_MODULE_EFFECTIVE_FROM")
EFFECTIVE_TO = os.getenv("AMODB_MODULE_EFFECTIVE_TO")
METADATA_JSON = os.getenv("AMODB_MODULE_METADATA_JSON")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def main() -> None:
    if not TENANT_ID:
        raise SystemExit("Set AMODB_TENANT_ID before running.")

    db: Session = SessionLocal()
    try:
        amo = db.query(account_models.AMO).filter(account_models.AMO.id == TENANT_ID).first()
        if not amo:
            raise SystemExit("Tenant not found.")

        status_value = account_models.ModuleSubscriptionStatus[STATUS]
        subscription = (
            db.query(account_models.ModuleSubscription)
            .filter(
                account_models.ModuleSubscription.amo_id == TENANT_ID,
                account_models.ModuleSubscription.module_code == MODULE_CODE,
            )
            .first()
        )
        if not subscription:
            subscription = account_models.ModuleSubscription(
                amo_id=TENANT_ID,
                module_code=MODULE_CODE,
            )
        subscription.status = status_value
        subscription.plan_code = PLAN_CODE
        subscription.effective_from = _parse_dt(EFFECTIVE_FROM)
        subscription.effective_to = _parse_dt(EFFECTIVE_TO)
        subscription.metadata_json = METADATA_JSON
        db.add(subscription)

        account_services.seed_default_departments(db, amo_id=TENANT_ID)
        finance_services.ensure_finance_defaults(db, amo_id=TENANT_ID)

        db.commit()
        print(f"Module {MODULE_CODE} set to {status_value.value} for tenant {TENANT_ID}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
