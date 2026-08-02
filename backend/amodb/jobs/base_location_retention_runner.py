from __future__ import annotations

from amodb.database import WriteSessionLocal
from amodb.apps.foundations import services


def run_retention_cycle() -> int:
    """Permanently remove expired raw base-location observations."""
    db = WriteSessionLocal()
    try:
        deleted = services.prune_location_observations(db)
        db.commit()
        return int(deleted or 0)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    count = run_retention_cycle()
    print(f"Base-location retention runner deleted {count} expired observations")
