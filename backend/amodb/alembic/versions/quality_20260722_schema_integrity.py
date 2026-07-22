"""Harden Quality tables previously created by runtime compatibility guards.

Revision ID: quality_20260722_schema_integrity
Revises: workforce_20260721_complete
Create Date: 2026-07-22

The Quality API historically created a few missing tables at request time so an
out-of-date database did not take down the cockpit. Those emergency tables did
not include the primary keys, foreign keys, defaults and nullability represented
by the ORM. This revision makes the database authoritative again and allows a
standalone QMS deployment to fail during migration instead of failing later in a
user workflow.
"""
from __future__ import annotations

from typing import Iterable

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "quality_20260722_schema_integrity"
down_revision = "workforce_20260721_complete"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    return bool(
        bind.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = current_schema()
                  AND t.relname = :table_name
                  AND c.conname = :constraint_name
                """
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).first()
    )


def _has_primary_key(bind, table_name: str) -> bool:
    return bool(
        bind.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = current_schema()
                  AND t.relname = :table_name
                  AND c.contype = 'p'
                """
            ),
            {"table_name": table_name},
        ).first()
    )


def _assert_no_rows(bind, sql: str, message: str) -> None:
    count = int(bind.execute(text(sql)).scalar() or 0)
    if count:
        raise RuntimeError(f"{message} ({count} row(s)). Repair the data before rerunning Alembic.")


def _set_not_null(table_name: str, columns: Iterable[str]) -> None:
    for column_name in columns:
        op.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" SET NOT NULL'))


def _add_constraint(bind, table_name: str, constraint_name: str, ddl: str) -> None:
    if not _constraint_exists(bind, table_name, constraint_name):
        op.execute(text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" {ddl}'))


def _harden_car_responses(bind) -> None:
    table_name = "quality_car_responses"
    if not _table_exists(bind, table_name):
        return

    op.execute(text("UPDATE quality_car_responses SET id = gen_random_uuid() WHERE id IS NULL"))
    op.execute(text("UPDATE quality_car_responses SET submitted_at = CURRENT_TIMESTAMP WHERE submitted_at IS NULL"))
    op.execute(text("UPDATE quality_car_responses SET status = 'SUBMITTED' WHERE status IS NULL OR btrim(status) = ''"))
    _assert_no_rows(bind, "SELECT count(*) FROM quality_car_responses WHERE car_id IS NULL", "Quality CAR responses contain rows without a CAR")
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM quality_car_responses r LEFT JOIN quality_cars c ON c.id = r.car_id WHERE c.id IS NULL",
        "Quality CAR responses contain orphaned CAR references",
    )
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM (SELECT id FROM quality_car_responses GROUP BY id HAVING count(*) > 1) duplicates",
        "Quality CAR responses contain duplicate IDs",
    )

    op.execute(text("ALTER TABLE quality_car_responses ALTER COLUMN id SET DEFAULT gen_random_uuid()"))
    op.execute(text("ALTER TABLE quality_car_responses ALTER COLUMN submitted_at SET DEFAULT CURRENT_TIMESTAMP"))
    op.execute(text("ALTER TABLE quality_car_responses ALTER COLUMN status SET DEFAULT 'SUBMITTED'"))
    _set_not_null(table_name, ("id", "car_id", "submitted_at", "status"))

    if not _has_primary_key(bind, table_name):
        _add_constraint(bind, table_name, "pk_quality_car_responses", "PRIMARY KEY (id)")
    _add_constraint(
        bind,
        table_name,
        "fk_quality_car_responses_car",
        "FOREIGN KEY (car_id) REFERENCES quality_cars(id) ON DELETE CASCADE",
    )
    _add_constraint(
        bind,
        table_name,
        "ck_quality_car_responses_status",
        "CHECK (status IN ('SUBMITTED','ROOT_CAUSE_ACCEPTED','ROOT_CAUSE_REJECTED','CAP_REJECTED','CAP_ACCEPTED'))",
    )
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_car_id ON quality_car_responses (car_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_submitted_at ON quality_car_responses (submitted_at)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_responses_status ON quality_car_responses (status)"))


def _harden_car_attachments(bind) -> None:
    table_name = "quality_car_attachments"
    if not _table_exists(bind, table_name):
        return

    op.execute(text("UPDATE quality_car_attachments SET id = gen_random_uuid() WHERE id IS NULL"))
    op.execute(text("UPDATE quality_car_attachments SET uploaded_at = CURRENT_TIMESTAMP WHERE uploaded_at IS NULL"))
    _assert_no_rows(bind, "SELECT count(*) FROM quality_car_attachments WHERE car_id IS NULL", "Quality CAR attachments contain rows without a CAR")
    _assert_no_rows(bind, "SELECT count(*) FROM quality_car_attachments WHERE filename IS NULL OR btrim(filename) = ''", "Quality CAR attachments contain blank filenames")
    _assert_no_rows(bind, "SELECT count(*) FROM quality_car_attachments WHERE file_ref IS NULL OR btrim(file_ref) = ''", "Quality CAR attachments contain blank file references")
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM quality_car_attachments a LEFT JOIN quality_cars c ON c.id = a.car_id WHERE c.id IS NULL",
        "Quality CAR attachments contain orphaned CAR references",
    )
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM (SELECT id FROM quality_car_attachments GROUP BY id HAVING count(*) > 1) duplicates",
        "Quality CAR attachments contain duplicate IDs",
    )

    op.execute(text("ALTER TABLE quality_car_attachments ALTER COLUMN id SET DEFAULT gen_random_uuid()"))
    op.execute(text("ALTER TABLE quality_car_attachments ALTER COLUMN uploaded_at SET DEFAULT CURRENT_TIMESTAMP"))
    _set_not_null(table_name, ("id", "car_id", "filename", "file_ref", "uploaded_at"))
    if not _has_primary_key(bind, table_name):
        _add_constraint(bind, table_name, "pk_quality_car_attachments", "PRIMARY KEY (id)")
    _add_constraint(
        bind,
        table_name,
        "fk_quality_car_attachments_car",
        "FOREIGN KEY (car_id) REFERENCES quality_cars(id) ON DELETE CASCADE",
    )
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_car_id ON quality_car_attachments (car_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_sha256 ON quality_car_attachments (sha256)"))


def _harden_finding_attachments(bind) -> None:
    table_name = "qms_finding_attachments"
    if not _table_exists(bind, table_name):
        return

    op.execute(text("UPDATE qms_finding_attachments SET id = gen_random_uuid() WHERE id IS NULL"))
    op.execute(text("UPDATE qms_finding_attachments SET uploaded_at = CURRENT_TIMESTAMP WHERE uploaded_at IS NULL"))
    _assert_no_rows(bind, "SELECT count(*) FROM qms_finding_attachments WHERE finding_id IS NULL", "Finding attachments contain rows without a finding")
    _assert_no_rows(bind, "SELECT count(*) FROM qms_finding_attachments WHERE filename IS NULL OR btrim(filename) = ''", "Finding attachments contain blank filenames")
    _assert_no_rows(bind, "SELECT count(*) FROM qms_finding_attachments WHERE file_ref IS NULL OR btrim(file_ref) = ''", "Finding attachments contain blank file references")
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM qms_finding_attachments a LEFT JOIN qms_audit_findings f ON f.id = a.finding_id WHERE f.id IS NULL",
        "Finding attachments contain orphaned finding references",
    )
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM (SELECT id FROM qms_finding_attachments GROUP BY id HAVING count(*) > 1) duplicates",
        "Finding attachments contain duplicate IDs",
    )

    op.execute(text("ALTER TABLE qms_finding_attachments ALTER COLUMN id SET DEFAULT gen_random_uuid()"))
    op.execute(text("ALTER TABLE qms_finding_attachments ALTER COLUMN uploaded_at SET DEFAULT CURRENT_TIMESTAMP"))
    _set_not_null(table_name, ("id", "finding_id", "filename", "file_ref", "uploaded_at"))
    if not _has_primary_key(bind, table_name):
        _add_constraint(bind, table_name, "pk_quality_finding_attachments", "PRIMARY KEY (id)")
    _add_constraint(
        bind,
        table_name,
        "fk_quality_finding_attachments_finding",
        "FOREIGN KEY (finding_id) REFERENCES qms_audit_findings(id) ON DELETE CASCADE",
    )
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_finding_id ON qms_finding_attachments (finding_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_uploaded_at ON qms_finding_attachments (uploaded_at)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_sha256 ON qms_finding_attachments (sha256)"))


def _harden_corrective_actions(bind) -> None:
    table_name = "qms_corrective_actions"
    if not _table_exists(bind, table_name):
        return

    op.execute(text("UPDATE qms_corrective_actions SET id = gen_random_uuid() WHERE id IS NULL"))
    op.execute(
        text(
            """
            UPDATE qms_corrective_actions ca
            SET amo_id = a.amo_id
            FROM qms_audit_findings f
            JOIN qms_audits a ON a.id = f.audit_id
            WHERE ca.finding_id = f.id
              AND (ca.amo_id IS NULL OR btrim(ca.amo_id) = '')
            """
        )
    )
    op.execute(text("UPDATE qms_corrective_actions SET status = 'OPEN' WHERE status IS NULL OR btrim(status) = ''"))
    op.execute(text("UPDATE qms_corrective_actions SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    op.execute(text("UPDATE qms_corrective_actions SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) WHERE updated_at IS NULL"))
    _assert_no_rows(bind, "SELECT count(*) FROM qms_corrective_actions WHERE finding_id IS NULL", "Corrective actions contain rows without a finding")
    _assert_no_rows(bind, "SELECT count(*) FROM qms_corrective_actions WHERE amo_id IS NULL OR btrim(amo_id) = ''", "Corrective actions contain rows without an AMO")
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM qms_corrective_actions ca LEFT JOIN qms_audit_findings f ON f.id = ca.finding_id WHERE f.id IS NULL",
        "Corrective actions contain orphaned finding references",
    )
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM qms_corrective_actions ca LEFT JOIN amos a ON a.id = ca.amo_id WHERE a.id IS NULL",
        "Corrective actions contain orphaned AMO references",
    )
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM (SELECT id FROM qms_corrective_actions GROUP BY id HAVING count(*) > 1) duplicates",
        "Corrective actions contain duplicate IDs",
    )
    _assert_no_rows(
        bind,
        "SELECT count(*) FROM (SELECT finding_id FROM qms_corrective_actions GROUP BY finding_id HAVING count(*) > 1) duplicates",
        "More than one corrective action is linked to the same finding",
    )

    op.execute(text("ALTER TABLE qms_corrective_actions ALTER COLUMN id SET DEFAULT gen_random_uuid()"))
    op.execute(text("ALTER TABLE qms_corrective_actions ALTER COLUMN status SET DEFAULT 'OPEN'"))
    op.execute(text("ALTER TABLE qms_corrective_actions ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP"))
    op.execute(text("ALTER TABLE qms_corrective_actions ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP"))
    _set_not_null(table_name, ("id", "amo_id", "finding_id", "status", "created_at", "updated_at"))
    if not _has_primary_key(bind, table_name):
        _add_constraint(bind, table_name, "pk_quality_corrective_actions", "PRIMARY KEY (id)")
    _add_constraint(
        bind,
        table_name,
        "fk_quality_corrective_actions_amo",
        "FOREIGN KEY (amo_id) REFERENCES amos(id) ON DELETE CASCADE",
    )
    _add_constraint(
        bind,
        table_name,
        "fk_quality_corrective_actions_finding",
        "FOREIGN KEY (finding_id) REFERENCES qms_audit_findings(id) ON DELETE CASCADE",
    )
    _add_constraint(bind, table_name, "uq_quality_corrective_actions_finding", "UNIQUE (finding_id)")
    _add_constraint(
        bind,
        table_name,
        "ck_quality_corrective_actions_status",
        "CHECK (status IN ('OPEN','IN_PROGRESS','CLOSED','REJECTED'))",
    )
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_corrective_actions_amo_id ON qms_corrective_actions (amo_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_qms_corrective_actions_status_due ON qms_corrective_actions (status, due_date)"))


def upgrade() -> None:
    bind = op.get_bind()
    _harden_car_responses(bind)
    _harden_car_attachments(bind)
    _harden_finding_attachments(bind)
    _harden_corrective_actions(bind)


def downgrade() -> None:
    bind = op.get_bind()
    constraints = (
        ("qms_corrective_actions", "ck_quality_corrective_actions_status"),
        ("qms_corrective_actions", "uq_quality_corrective_actions_finding"),
        ("qms_corrective_actions", "fk_quality_corrective_actions_finding"),
        ("qms_corrective_actions", "fk_quality_corrective_actions_amo"),
        ("qms_corrective_actions", "pk_quality_corrective_actions"),
        ("qms_finding_attachments", "fk_quality_finding_attachments_finding"),
        ("qms_finding_attachments", "pk_quality_finding_attachments"),
        ("quality_car_attachments", "fk_quality_car_attachments_car"),
        ("quality_car_attachments", "pk_quality_car_attachments"),
        ("quality_car_responses", "ck_quality_car_responses_status"),
        ("quality_car_responses", "fk_quality_car_responses_car"),
        ("quality_car_responses", "pk_quality_car_responses"),
    )
    for table_name, constraint_name in constraints:
        if _table_exists(bind, table_name) and _constraint_exists(bind, table_name, constraint_name):
            op.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{constraint_name}"'))
