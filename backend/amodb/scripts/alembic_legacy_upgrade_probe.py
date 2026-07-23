from __future__ import annotations

"""PostgreSQL probe for released Alembic multi-head upgrade compatibility.

The full implementation is completed by the migration hotfix. This module is
kept import-safe so CI can validate the exact historical state without loading
application modules during graph discovery.
"""

LEGACY_WORKFORCE_HEAD = "workforce_20260721_complete"
LEGACY_PHASE2_HEAD = "phase2_14a_20260615"


def main() -> None:
    raise RuntimeError("Alembic legacy upgrade probe implementation is not complete")


if __name__ == "__main__":
    main()
