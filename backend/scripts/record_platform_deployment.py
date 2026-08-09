#!/usr/bin/env python3
from __future__ import annotations

import argparse

from amodb.apps.platform.change_markers import record_deployment_marker
from amodb.database import WriteSessionLocal, close_session_safely


def _parse_details(values: list[str]) -> dict[str, str]:
    details: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError(f"invalid --detail value {value!r}; expected key=value")
        details[key] = item.strip()
    return details


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record an automation-owned Platform deployment change marker."
    )
    parser.add_argument("--reference", required=True, help="Idempotency reference for this deployment execution")
    parser.add_argument("--title", default=None, help="Optional human-readable deployment title")
    parser.add_argument(
        "--detail",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Bounded scalar deployment metadata; may be supplied more than once",
    )
    args = parser.parse_args()

    details = _parse_details(args.detail)
    db = WriteSessionLocal()
    try:
        marker = record_deployment_marker(
            db,
            reference=args.reference,
            title=args.title,
            details=details,
        )
        print(f"Recorded Platform deployment marker {marker.id} ({marker.reference})")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        close_session_safely(db)


if __name__ == "__main__":
    raise SystemExit(main())
