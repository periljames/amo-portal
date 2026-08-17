from __future__ import annotations

import argparse
from pathlib import Path

from amodb.database import SessionLocal
from amodb.apps.training.synthetic_recurrent_reconciliation import (
    identify_synthetic_recurrent_records,
    reconcile_synthetic_recurrent_records,
    reconciliation_csv,
    reconciliation_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply reconciliation for legacy auto-seeded recurrent TrainingRecord rows."
    )
    parser.add_argument("--amo-id", required=True, help="Tenant/AMO identifier. Tenant scope is mandatory.")
    parser.add_argument("--apply", action="store_true", help="Supersede deterministic evidence-free synthetic rows. Default is dry-run.")
    parser.add_argument("--actor-user-id", help="Authorized actor recorded on applied changes when the model supports it.")
    parser.add_argument("--json-out", type=Path, help="Optional path for the immutable pre-change JSON report.")
    parser.add_argument("--csv-out", type=Path, help="Optional path for the immutable pre-change CSV candidate report.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        candidates = identify_synthetic_recurrent_records(db, amo_id=args.amo_id)
        preview = {
            "amo_id": args.amo_id,
            "apply": False,
            "candidate_count": len(candidates),
            "candidates": [item.__dict__ for item in candidates],
        }
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(reconciliation_json(preview), encoding="utf-8")
        if args.csv_out:
            args.csv_out.parent.mkdir(parents=True, exist_ok=True)
            args.csv_out.write_text(reconciliation_csv(candidates), encoding="utf-8")

        print(reconciliation_json(preview))
        if not args.apply:
            db.rollback()
            return 0

        report = reconcile_synthetic_recurrent_records(
            db,
            amo_id=args.amo_id,
            apply=True,
            actor_user_id=args.actor_user_id,
        )
        db.commit()
        print(reconciliation_json(report))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
