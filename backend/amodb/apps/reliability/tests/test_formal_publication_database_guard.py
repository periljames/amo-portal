from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


TRIGGERS = {
    "trg_rel_formal_section_guard": "reliability_formal_report_sections",
    "trg_rel_formal_req_guard": "reliability_formal_requirement_assessments",
    "trg_rel_formal_source_guard": "reliability_formal_report_sources",
    "trg_rel_formal_override_guard": "reliability_formal_completeness_overrides",
}


def _postgres_engine():
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL formal publication trigger regression requires DATABASE_URL.")
    return create_engine(url)


def test_published_child_guards_include_insert_on_postgresql():
    engine = _postgres_engine()
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT tgname, pg_get_triggerdef(oid) AS definition
            FROM pg_trigger
            WHERE tgname = ANY(:names)
              AND NOT tgisinternal
        """), {"names": list(TRIGGERS)}).mappings().all()
    definitions = {row["tgname"]: row["definition"] for row in rows}
    assert definitions.keys() == TRIGGERS.keys()
    for trigger, table in TRIGGERS.items():
        definition = definitions[trigger]
        assert f"ON public.{table}" in definition or f"ON {table}" in definition
        assert "INSERT" in definition
        assert "UPDATE" in definition
        assert "DELETE" in definition


def test_published_section_insert_is_rejected_on_postgresql():
    engine = _postgres_engine()
    with engine.begin() as connection:
        report = connection.execute(text("""
            SELECT id, amo_id
            FROM reliability_formal_reports
            WHERE published_at IS NOT NULL
            ORDER BY published_at DESC
            LIMIT 1
        """)).mappings().first()
        if not report:
            pytest.skip("No published formal Reliability fixture exists in this database.")

        savepoint = connection.begin_nested()
        try:
            with pytest.raises(DBAPIError):
                connection.execute(text("""
                    INSERT INTO reliability_formal_report_sections (
                        id, amo_id, report_id, section_code, sequence, title,
                        required, status, computed_data, commentary,
                        evidence_refs, warnings, updated_at
                    ) VALUES (
                        :id, :amo_id, :report_id, :section_code, 999,
                        'Post-publication mutation probe', false, 'READY',
                        '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NOW()
                    )
                """), {
                    "id": str(uuid.uuid4()),
                    "amo_id": report["amo_id"],
                    "report_id": report["id"],
                    "section_code": f"mutation_probe_{uuid.uuid4().hex[:8]}",
                })
        finally:
            savepoint.rollback()
