from __future__ import annotations

import os
import subprocess

import sqlalchemy as sa
from sqlalchemy import create_engine, text


TARGET_REVISION = "quality_260817_occurrence_frontend_completion"
TABLES = (
    "quality_external_identities",
    "quality_audit_participants",
    "quality_audit_access_grants",
    "quality_audit_access_events",
    "quality_audit_finding_release_events",
    "quality_audit_document_submissions",
    "quality_audit_report_artifacts",
    "quality_audit_fieldwork_mutation_receipts",
    "quality_audit_fieldwork_participant_contributions",
    "quality_audit_output_policy_revisions",
    "quality_audit_signature_attempts",
    "quality_audit_signature_evidence",
    "quality_audit_assurance_artifacts",
    "quality_audit_retention_policy_revisions",
    "quality_audit_archive_manifests",
    "quality_audit_archive_manifest_items",
    "quality_audit_legal_hold_events",
    "quality_audit_disposition_events",
    "quality_audit_webauthn_credentials",
    "quality_audit_webauthn_challenges",
    "quality_audit_closing_acknowledgements",
    "quality_audit_verification_tokens",
    "quality_audit_evidence_artifacts",
    "quality_audit_presence",
    "quality_audit_document_request_metadata",
    "quality_audit_controlled_document_submissions",
    "quality_audit_meetings",
    "quality_audit_closing_narratives",
    "quality_audit_assignment_decisions",
)
APPEND_ONLY_TABLES = (
    "quality_audit_access_events",
    "quality_audit_finding_release_events",
    "quality_audit_document_submissions",
    "quality_audit_report_artifacts",
    "quality_audit_fieldwork_mutation_receipts",
    "quality_audit_fieldwork_participant_contributions",
    "quality_audit_output_policy_revisions",
    "quality_audit_signature_attempts",
    "quality_audit_signature_evidence",
    "quality_audit_assurance_artifacts",
    "quality_audit_retention_policy_revisions",
    "quality_audit_archive_manifests",
    "quality_audit_archive_manifest_items",
    "quality_audit_legal_hold_events",
    "quality_audit_disposition_events",
    "quality_audit_closing_acknowledgements",
)
IMMUTABLE_TABLES = (
    "quality_audit_evidence_artifacts",
)


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _assert_rls(connection: sa.Connection, table_name: str) -> None:
    row = connection.execute(
        text(
            """
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE oid = CAST(:table_name AS regclass)
            """
        ),
        {"table_name": table_name},
    ).one()
    assert row.relrowsecurity is True, (table_name, row)
    assert row.relforcerowsecurity is True, (table_name, row)
    policies = connection.execute(
        text(
            """
            SELECT policyname, qual, with_check
            FROM pg_policies
            WHERE schemaname = current_schema()
              AND tablename = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    assert len(policies) == 1, (table_name, policies)
    policy_text = f"{policies[0].qual} {policies[0].with_check}"
    assert "app.tenant_id" in policy_text, (table_name, policy_text)


def _columns(connection: sa.Connection, table_name: str) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()
    }


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    _run_alembic("upgrade", "heads")

    with engine.begin() as connection:
        versions = {str(row[0]) for row in connection.execute(text("SELECT version_num FROM alembic_version")).all()}
        assert TARGET_REVISION in versions, versions

        existing = {
            str(row[0])
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = ANY(:tables)
                    """
                ),
                {"tables": list(TABLES)},
            ).all()
        }
        assert existing == set(TABLES), existing

        governance_columns = _columns(connection, "quality_audit_checklist_execution_governance")
        assert {"entity_version", "updated_by_participant_id"} <= governance_columns, governance_columns
        event_columns = _columns(connection, "quality_audit_checklist_execution_events")
        assert "actor_participant_id" in event_columns, event_columns
        receipt_columns = _columns(connection, "quality_audit_fieldwork_mutation_receipts")
        assert {"client_timestamp", "actor_participant_id", "actor_user_id"} <= receipt_columns, receipt_columns
        manifest_columns = _columns(connection, "quality_audit_archive_manifests")
        assert {
            "manifest_sha256",
            "package_file_ref",
            "package_filename",
            "package_size_bytes",
            "package_sha256",
        } <= manifest_columns, manifest_columns
        disposition_columns = _columns(connection, "quality_audit_disposition_events")
        assert {"inventory_sha256", "package_sha256", "action_ref"} <= disposition_columns, disposition_columns
        signature_columns = _columns(connection, "quality_audit_signature_evidence")
        assert {
            "credential_id_hash",
            "webauthn_sign_count",
            "webauthn_origin",
            "webauthn_rp_id",
            "ceremony_sha256",
        } <= signature_columns, signature_columns
        credential_columns = _columns(connection, "quality_audit_webauthn_credentials")
        assert {"owner_type", "credential_id", "public_key", "sign_count", "is_active"} <= credential_columns, credential_columns
        verification_columns = _columns(connection, "quality_audit_verification_tokens")
        assert {"token_hash", "expires_at", "revoked_at", "last_verified_at"} <= verification_columns, verification_columns
        evidence_columns = _columns(connection, "quality_audit_evidence_artifacts")
        assert {"sha256", "uploaded_by_user_id", "uploaded_by_participant_id", "client_mutation_id"} <= evidence_columns, evidence_columns
        presence_columns = _columns(connection, "quality_audit_presence")
        assert {"actor_type", "actor_key", "user_id", "participant_id", "last_seen_at"} <= presence_columns, presence_columns
        document_metadata_columns = _columns(connection, "quality_audit_document_request_metadata")
        assert {"source_mode", "controlled_document_id", "controlled_revision_id"} <= document_metadata_columns, document_metadata_columns

        for table_name in TABLES:
            _assert_rls(connection, table_name)

        trigger_tables = list(APPEND_ONLY_TABLES) + list(IMMUTABLE_TABLES)
        triggers = {
            (str(row.table_name), str(row.trigger_name))
            for row in connection.execute(
                text(
                    """
                    SELECT event_object_table AS table_name, trigger_name
                    FROM information_schema.triggers
                    WHERE trigger_schema = current_schema()
                      AND event_object_table = ANY(:tables)
                    """
                ),
                {"tables": trigger_tables},
            ).mappings()
        }
        for table_name in APPEND_ONLY_TABLES:
            assert any(table == table_name and "append_only" in trigger for table, trigger in triggers), (table_name, triggers)
        for table_name in IMMUTABLE_TABLES:
            assert any(table == table_name and "immutable" in trigger for table, trigger in triggers), (table_name, triggers)

    print(
        "Live audit final-head migrations, RLS, WebAuthn/verification, evidence, presence, "
        "package integrity, participant attribution and immutable history verified"
    )


if __name__ == "__main__":
    main()
