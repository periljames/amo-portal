from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "foundation_20260805_timestamp_defaults.py"
)


def test_foundation_timestamp_repair_covers_all_server_generated_fields() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    expected_repairs = (
        '_set_timestamp_default("base_stations", "created_at")',
        '_set_timestamp_default("base_stations", "updated_at")',
        '_set_timestamp_default("base_station_aliases", "created_at")',
        '_set_timestamp_default("user_base_assignments", "created_at")',
        '_set_timestamp_default("user_base_assignments", "updated_at")',
        '"user_base_assignments",\n            "effective_from"',
        'server_default=sa.text("CURRENT_DATE")',
        'server_default=sa.text("CURRENT_TIMESTAMP")',
    )

    for expected in expected_repairs:
        assert expected in source


def test_foundation_timestamp_repair_follows_current_foundation_chain() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "foundation_20260805_timestamp_defaults"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "rel_20260804_calc_revisions"' in source
