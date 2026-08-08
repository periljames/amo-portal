"""PostgreSQL schema regression for operational and formal Reliability integrity."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


EXPECTED_TABLES = {
    "reliability_flight_operations",
    "reliability_mel_cdl_deferrals",
    "reliability_component_shop_findings",
    "reliability_sms_occurrences",
    "reliability_workbook_imports",
    "reliability_workbook_rows",
    "reliability_source_revision_events",
}

REQUIRED_HOUR_COLUMNS = {
    ("aircraft", "total_hours"),
    ("aircraft_usage", "block_hours"),
    ("aircraft_components", "current_hours"),
}
REQUIRED_COUNT_COLUMNS = {
    ("aircraft", "total_cycles"),
    ("aircraft_usage", "cycles"),
    ("aircraft_components", "current_cycles"),
}
OPTIONAL_HOUR_COLUMNS = {("technical_aircraft_utilisation", "hours")}
OPTIONAL_COUNT_COLUMNS = {("technical_aircraft_utilisation", "cycles")}


def _must_fail(connection, sql: str, params: dict, label: str) -> None:
    savepoint = f"regression_{label.replace('-', '_')}"
    connection.execute(text(f"SAVEPOINT {savepoint}"))
    try:
        connection.execute(text(sql), params)
    except DBAPIError:
        connection.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint}"))
    else:
        raise AssertionError(f"{label} unexpectedly succeeded")


def _exercise_formal_publication_controls(connection) -> None:
    amo_id = "00000000-0000-7000-8000-000000000201"
    other_amo_id = "00000000-0000-7000-8000-000000000202"
    profile_id = "00000000-0000-7000-8000-000000000203"
    report_id = "00000000-0000-7000-8000-000000000204"
    section_id = "00000000-0000-7000-8000-000000000205"
    approval_id = "00000000-0000-7000-8000-000000000206"
    lifecycle_id = "00000000-0000-7000-8000-000000000207"
    inserted_section_id = "00000000-0000-7000-8000-000000000208"

    # Keep the formal report's tenant parent valid when origin-mode FK checks run
    # during the allowed lifecycle update below. The remaining retained-history
    # rows are inserted with user/audit triggers disabled only for fixture setup.
    connection.execute(text("""
        INSERT INTO amos (
            id, amo_code, name, login_slug, is_demo, is_active, created_at, updated_at
        ) VALUES (
            :amo_id, 'RELPGUAT201', 'Reliability PostgreSQL UAT AMO',
            'rel-pg-uat-201', false, true, NOW(), NOW()
        )
    """), {"amo_id": amo_id})
    connection.execute(text("SET LOCAL session_replication_role = replica"))
    connection.execute(text("""
        INSERT INTO reliability_regulatory_profiles (
            id, amo_id, code, version, name, authority, jurisdiction, status,
            derived_from_profiles, required_sections, mandatory_kpis,
            minimum_analysis_periods, statistical_methods, historical_windows,
            commentary_rules, evidence_rules, approval_workflow,
            publication_rules, source_manifest, is_default, created_at, updated_at
        ) VALUES (
            :profile_id, :amo_id, 'OPERATOR', 'uat-1', 'Formal trigger fixture',
            'OPERATOR', 'TEST', 'ACTIVE', '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
            '{}'::jsonb, '[]'::jsonb, '[12]'::jsonb, '{}'::jsonb, '{}'::jsonb,
            jsonb_build_object(
                'approval_roles', jsonb_build_array('QUALITY_MANAGER'),
                'separation_of_duties', false
            ),
            '{}'::jsonb, '[]'::jsonb, false, NOW(), NOW()
        )
    """), {"profile_id": profile_id, "amo_id": amo_id})
    connection.execute(text("""
        INSERT INTO reliability_formal_reports (
            id, amo_id, profile_id, report_number, revision, title, period_type,
            period_start, period_end, status, profile_code_snapshot,
            profile_version_snapshot, regulatory_manifest, effectivity_json,
            source_population_json, formula_revisions_json,
            calculation_snapshots_json, chart_data_json, narrative_json,
            data_quality_json, completeness_json, rendered_html, html_sha256,
            pdf_storage_ref, pdf_sha256, pdf_size_bytes, published_at,
            created_at, updated_at
        ) VALUES (
            :report_id, :amo_id, :profile_id, 'REL-PG-UAT', 0,
            'Published formal Reliability fixture', 'ANNUAL', DATE '2025-01-01',
            DATE '2025-12-31', 'PUBLISHED', 'OPERATOR', 'uat-1', '[]'::jsonb,
            '{"scope":"TENANT_FLEET"}'::jsonb,
            '{"source_identity_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'::jsonb,
            '[{"code":"event_rate_per_100_fh","version":"1.0"}]'::jsonb,
            '{"dashboard":{"summary":[]}}'::jsonb, '{}'::jsonb, '[]'::jsonb,
            '{}'::jsonb, jsonb_build_object('passed', true), '<html>retained</html>',
            'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
            '/tmp/retained.pdf',
            'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
            128, NOW(), NOW(), NOW()
        )
    """), {"report_id": report_id, "amo_id": amo_id, "profile_id": profile_id})
    connection.execute(text("""
        INSERT INTO reliability_formal_report_sections (
            id, amo_id, report_id, section_code, sequence, title, required,
            status, computed_data, commentary, evidence_refs, warnings, updated_at
        ) VALUES (
            :id, :amo_id, :report_id, 'executive_assessment', 1,
            'Executive assessment', true, 'READY', '{}'::jsonb, '[]'::jsonb,
            '[]'::jsonb, '[]'::jsonb, NOW()
        )
    """), {"id": section_id, "amo_id": amo_id, "report_id": report_id})
    connection.execute(text("""
        INSERT INTO reliability_formal_approvals (
            id, amo_id, report_id, stage, decision, role_snapshot,
            report_revision, report_hash, created_at
        ) VALUES (
            :id, :amo_id, :report_id, 'APPROVED', 'PUBLISHED',
            'QUALITY_MANAGER', 0,
            'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', NOW()
        )
    """), {"id": approval_id, "amo_id": amo_id, "report_id": report_id})
    connection.execute(text("""
        INSERT INTO reliability_formal_lifecycle_events (
            id, amo_id, report_id, from_status, to_status, action, payload_json,
            event_hash, role_snapshot, created_at
        ) VALUES (
            :id, :amo_id, :report_id, 'APPROVED', 'PUBLISHED', 'TRANSITION',
            '{}'::jsonb,
            'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
            'QUALITY_MANAGER', NOW()
        )
    """), {"id": lifecycle_id, "amo_id": amo_id, "report_id": report_id})
    connection.execute(text("SET LOCAL session_replication_role = origin"))

    _must_fail(
        connection,
        "UPDATE reliability_formal_reports SET title='mutated' WHERE id=:id",
        {"id": report_id},
        "published-report-content-mutation",
    )
    _must_fail(
        connection,
        "UPDATE reliability_formal_report_sections SET title='mutated' WHERE id=:id",
        {"id": section_id},
        "published-child-mutation",
    )
    _must_fail(
        connection,
        """
        INSERT INTO reliability_formal_report_sections (
            id, amo_id, report_id, section_code, sequence, title, required,
            status, computed_data, commentary, evidence_refs, warnings, updated_at
        ) VALUES (
            :id, :amo_id, :report_id, 'post_publication_probe', 999,
            'Post-publication mutation probe', false, 'READY', '{}'::jsonb,
            '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, NOW()
        )
        """,
        {"id": inserted_section_id, "amo_id": amo_id, "report_id": report_id},
        "published-child-insert",
    )
    _must_fail(
        connection,
        "UPDATE reliability_formal_approvals SET comment='mutated' WHERE id=:id",
        {"id": approval_id},
        "approval-append-only",
    )
    _must_fail(
        connection,
        "DELETE FROM reliability_formal_lifecycle_events WHERE id=:id",
        {"id": lifecycle_id},
        "lifecycle-append-only",
    )

    # Supersession metadata is the controlled exception to content immutability.
    connection.execute(text("""
        UPDATE reliability_formal_reports
        SET status='SUPERSEDED', superseded_at=NOW(), updated_at=NOW()
        WHERE id=:id
    """), {"id": report_id})
    state = connection.execute(text("SELECT status, title FROM reliability_formal_reports WHERE id=:id"), {"id": report_id}).one()
    assert state.status == "SUPERSEDED", state
    assert state.title == "Published formal Reliability fixture", state

    # Application lookup is tenant-scoped even when an attacker knows the UUID.
    from amodb.apps.reliability.formal_reporting import _report

    session = Session(bind=connection)
    try:
        _report(session, other_amo_id, report_id)
    except HTTPException as exc:
        assert exc.status_code == 404, exc
    else:
        raise AssertionError("cross-tenant formal report lookup unexpectedly succeeded")


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        tables = {
            row[0]
            for row in connection.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """))
        }
        missing = EXPECTED_TABLES - tables
        assert not missing, sorted(missing)

        trigger_count = connection.execute(text("""
            SELECT COUNT(*)
            FROM pg_trigger
            WHERE tgname = 'trg_rel_source_revision_append_only'
              AND NOT tgisinternal
        """)).scalar_one()
        assert trigger_count == 1, trigger_count

        target_columns = REQUIRED_HOUR_COLUMNS | REQUIRED_COUNT_COLUMNS | OPTIONAL_HOUR_COLUMNS | OPTIONAL_COUNT_COLUMNS
        columns = {
            (row.table_name, row.column_name): (row.data_type, row.numeric_precision, row.numeric_scale)
            for row in connection.execute(text("""
                SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE (table_name, column_name) IN (
                    ('aircraft', 'total_hours'),
                    ('aircraft', 'total_cycles'),
                    ('aircraft_usage', 'block_hours'),
                    ('aircraft_usage', 'cycles'),
                    ('aircraft_components', 'current_hours'),
                    ('aircraft_components', 'current_cycles'),
                    ('technical_aircraft_utilisation', 'hours'),
                    ('technical_aircraft_utilisation', 'cycles')
                )
            """))
        }
        assert REQUIRED_HOUR_COLUMNS <= columns.keys(), sorted(REQUIRED_HOUR_COLUMNS - columns.keys())
        assert REQUIRED_COUNT_COLUMNS <= columns.keys(), sorted(REQUIRED_COUNT_COLUMNS - columns.keys())
        assert set(columns) <= target_columns, sorted(set(columns) - target_columns)

        for key in REQUIRED_HOUR_COLUMNS | (OPTIONAL_HOUR_COLUMNS & columns.keys()):
            assert columns[key][0] == "numeric", (key, columns[key])
            assert columns[key][2] == 3, (key, columns[key])
        for key in REQUIRED_COUNT_COLUMNS | (OPTIONAL_COUNT_COLUMNS & columns.keys()):
            assert columns[key][0] == "bigint", (key, columns[key])

        revision_id = "00000000-0000-7000-8000-000000000091"
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(text("""
            INSERT INTO reliability_source_revision_events (
                id, amo_id, source_type, source_id, revision, action,
                payload_json, actor_user_id, created_at
            ) VALUES (
                :id, '00000000-0000-7000-8000-000000000001',
                'FLIGHT_OPERATION', '00000000-0000-7000-8000-000000000092',
                1, 'CREATED', CAST('{}' AS jsonb), NULL, NOW()
            )
        """), {"id": revision_id})
        connection.execute(text("SET LOCAL session_replication_role = origin"))

        _must_fail(
            connection,
            "UPDATE reliability_source_revision_events SET action='ALTERED' WHERE id=:id",
            {"id": revision_id},
            "source-revision-append-only",
        )
        action = connection.execute(text("SELECT action FROM reliability_source_revision_events WHERE id=:id"), {"id": revision_id}).scalar_one()
        assert action == "CREATED", action

        # Execute formal long-term aggregation SQL against the real PostgreSQL schema
        # for both whole-fleet and selected-aircraft paths.
        from amodb.apps.reliability.formal_reporting_history import _domain_rows, _event_rows, _utilisation_rows

        session = Session(bind=connection)
        params = {
            "amo_id": "00000000-0000-7000-8000-000000000099",
            "start_date": date(2024, 1, 1),
            "end_date": date(2026, 12, 31),
            "cutoff": datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc),
            "aircraft": [],
            "use_aircraft": False,
        }
        assert _utilisation_rows(session, params) == []
        assert _event_rows(session, params) == []
        assert _domain_rows(session, params) == []
        params["aircraft"] = ["5Y-TEST"]
        params["use_aircraft"] = True
        assert _utilisation_rows(session, params) == []
        assert _event_rows(session, params) == []
        assert _domain_rows(session, params) == []

        _exercise_formal_publication_controls(connection)

    print("PostgreSQL operational/formal Reliability integrity regression passed")


if __name__ == "__main__":
    main()
