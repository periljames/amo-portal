from __future__ import annotations

from amodb.database import WriteSessionLocal
from amodb.apps.platform import metrics


def run_once() -> dict:
    db = WriteSessionLocal()
    try:
        return metrics.flush_route_metrics(db)
    finally:
        db.close()


if __name__ == "__main__":
    print(run_once())
