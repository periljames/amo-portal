from __future__ import annotations

import os
import subprocess
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine, text


TARGET_REVISION = "quality_20260722_schema_integrity"
BASE_REVISION = "workforce_20260721_complete"


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _create_runtime_fallback_baseline(engine: sa.Engine) -> dict[str, str]:
    ids = {
        "amo": str(uuid4()),
        "car": str(uuid4()),
        "audit": str(uuid4()),
        "finding": str(uuid4()),
    }
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        connection.execute(text("CREATE TABLE amos (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE quality_cars (id UUID PRIMARY KEY, amo_id VARCHAR(36) NOT NULL)"))
        connection.execute(text("CREATE TABLE qms_audits (id UUID PRIMARY KEY, amo_id VARCHAR(36), audit_ref VARCHAR(64))"))
        connection.execute(text("CREATE TABLE qms_audit_findings (id UUID PRIMARY KEY, audit_id UUID NOT NULL)"))
        connection.execute(
            text(
                """
                CREATE TABLE quality_car_responses (
                    id UUID,
                    car_id UUID,
                    containment_action TEXT,
                    root_cause TEXT,
                    corrective_action TEXT,
                    preventive_action TEXT,
                    evidence_ref VARCHAR(512),
                    submitted_by_name VARCHAR(255),
                    submitted_by_email VARCHAR(255),
                    submitted_at TIMESTAMPTZ,
                    status VARCHAR(32)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE quality_car_attachments (
                    id UUID,
                    car_id UUID,
                    filename VARCHAR(255),
                    description VARCHAR(500),
                    file_ref VARCHAR(512),
                    content_type VARCHAR(128),
                    size_bytes INTEGER,
                    sha256 VARCHAR(64),
                    uploaded_at TIMESTAMPTZ
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE qms_finding_attachments (
                    id UUID,
                    finding_id UUID,
                    filename VARCHAR(255),
                    description VARCHAR(500),
                    file_ref VARCHAR(512),
                    content_type VARCHAR(128),
                    size_bytes INTEGER,
                    sha256 VARCHAR(64),
                    uploaded_by_user_id VARCHAR(36),
                    uploaded_at TIMESTAMPTZ
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE qms_corrective_actions (
                    id UUID,
                    amo_id VARCHAR(36),
                    finding_id UUID,
                    root_cause TEXT,
                    containment_action TEXT,
                    corrective_action TEXT,
                    preventive_action TEXT,
                    responsible_user_id VARCHAR(36),
                    due_date DATE,
                    evidence_ref VARCHAR(512),
                    verified_at TIMESTAMPTZ,
                    verified_by_user_id VARCHAR(36),
                    status VARCHAR(32),
                    created_by_user_id VARCHAR(36),
                    updated_by_user_id VARCHAR(36),
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ
                )
                """
            )
        )

        connection.execute(text("INSERT INTO amos (id) VALUES (:amo)"), ids)
        connection.execute(text("INSERT INTO quality_cars (id, amo_id) VALUES (CAST(:car AS uuid), :amo)"), ids)
        connection.execute(text("INSERT INTO qms_audits (id, amo_id, audit_ref) VALUES (CAST(:audit AS uuid), :amo, 'QAR/MO/26/0001')"), ids)
        connection.execute(text("INSERT INTO qms_audit_findings (id, audit_id) VALUES (CAST(:finding AS uuid), CAST(:audit AS uuid))"), ids)
        connection.execute(text("INSERT INTO quality_car_responses (car_id) VALUES (CAST(:car AS uuid))"), ids)
        connection.execute(
            text("INSERT INTO quality_car_attachments (car_id, filename, file_ref) VALUES (CAST(:car AS uuid), 'evidence.pdf', 'quality/evidence.pdf')"),
            ids,
        )
        connection.execute(
            text("INSERT INTO qms_finding_attachments (finding_id, filename, file_ref) VALUES (CAST(:finding AS uuid), 'finding.pdf', 'quality/finding.pdf')"),
            ids,
        )
        connection.execute(text("INSERT INTO qms_corrective_actions (finding_id) VALUES (CAST(:finding AS uuid))"), ids)
    return ids


def _constraints(connection, table_name: str) -> dict[str, str]:
    rows = connection.execute(
        text(
            """
            SELECT c.conname, c.contype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = current_schema()
              AND t.relname = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {str(name): str(kind) for name, kind in rows}


def _nullable_columns(connection, table_name: str) -> dict[str, bool]:
    rows = connection.execute(
        text(
            """
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {str(name): nullable == "YES" for name, nullable in rows}


def _assert_foreign_key_rejects_orphan(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("INSERT INTO quality_car_responses (car_id) VALUES (gen_random_uuid())"))
        except sa.exc.IntegrityError:
            transaction.rollback()
            return
        transaction.rollback()
    raise AssertionError("Orphaned CAR response insertion unexpectedly succeeded")


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    ids = _create_runtime_fallback_baseline(engine)
    _run_alembic("stamp", BASE_REVISION)
    _run_alembic("upgrade", TARGET_REVISION)

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == TARGET_REVISION

        expected = {
            "quality_car_responses": {
                "pk_quality_car_responses": "p",
                "fk_quality_car_responses_car": "f",
                "ck_quality_car_responses_status": "c",
            },
            "quality_car_attachments": {
                "pk_quality_car_attachments": "p",
                "fk_quality_car_attachments_car": "f",
            },
            "qms_finding_attachments": {
                "pk_quality_finding_attachments": "p",
                "fk_quality_finding_attachments_finding": "f",
            },
            "qms_corrective_actions": {
                "pk_quality_corrective_actions": "p",
                "fk_quality_corrective_actions_amo": "f",
                "fk_quality_corrective_actions_finding": "f",
                "uq_quality_corrective_actions_finding": "u",
                "ck_quality_corrective_actions_status": "c",
            },
        }
        for table_name, required in expected.items():
            constraints = _constraints(connection, table_name)
            for name, kind in required.items():
                assert constraints.get(name) == kind, (table_name, name, constraints)

        required_not_null = {
            "quality_car_responses": {"id", "car_id", "submitted_at", "status"},
            "quality_car_attachments": {"id", "car_id", "filename", "file_ref", "uploaded_at"},
            "qms_finding_attachments": {"id", "finding_id", "filename", "file_ref", "uploaded_at"},
            "qms_corrective_actions": {"id", "amo_id", "finding_id", "status", "created_at", "updated_at"},
        }
        for table_name, columns in required_not_null.items():
            nullable = _nullable_columns(connection, table_name)
            assert all(nullable.get(column) is False for column in columns), (table_name, nullable)

        response = connection.execute(
            text("SELECT id, submitted_at, status FROM quality_car_responses WHERE car_id = CAST(:car AS uuid)"),
            ids,
        ).one()
        assert response.id is not None
        assert response.submitted_at is not None
        assert response.status == "SUBMITTED"

        cap = connection.execute(
            text("SELECT id, amo_id, status, created_at, updated_at FROM qms_corrective_actions WHERE finding_id = CAST(:finding AS uuid)"),
            ids,
        ).one()
        assert cap.id is not None
        assert cap.amo_id == ids["amo"]
        assert cap.status == "OPEN"
        assert cap.created_at is not None
        assert cap.updated_at is not None

    _assert_foreign_key_rejects_orphan(engine)


if __name__ == "__main__":
    main()
