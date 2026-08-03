from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "backend/amodb/alembic/versions"
REVISION = "rel_20260803_complete_scope"

CAPABILITIES = [
    "reliability.read",
    "reliability.source.manage",
    "reliability.ingest",
    "reliability.data_quality.resolve",
    "reliability.fracas.triage",
    "reliability.fracas.investigate",
    "reliability.fracas.action",
    "reliability.fracas.verify",
    "reliability.programme.manage",
    "reliability.programme.approve",
    "reliability.metric.manage",
    "reliability.metric.execute",
    "reliability.meeting.manage",
    "reliability.change.manage",
    "reliability.change.approve",
    "reliability.handoff.manage",
    "reliability.authority.prepare",
    "reliability.authority.submit",
    "reliability.ai.use",
    "reliability.ai.review",
    "reliability.audit.read",
]

ROLES = {
    "rel-role-viewer": {
        "code": "RELIABILITY_VIEWER",
        "description": "Read-only Reliability evidence and controlled outputs.",
        "capabilities": ["reliability.read"],
    },
    "rel-role-engineer": {
        "code": "RELIABILITY_ENGINEER",
        "description": "Reliability ingestion, technical investigation, calculations and implementation handoffs.",
        "capabilities": [
            "reliability.read",
            "reliability.ingest",
            "reliability.fracas.triage",
            "reliability.fracas.investigate",
            "reliability.fracas.action",
            "reliability.metric.execute",
            "reliability.handoff.manage",
            "reliability.ai.use",
        ],
    },
    "rel-role-manager": {
        "code": "RELIABILITY_MANAGER",
        "description": "Reliability programme manager with governance and approval authority inside the AMO tenant.",
        "capabilities": [cap for cap in CAPABILITIES if cap != "reliability.authority.submit"],
    },
    "rel-role-authority": {
        "code": "RELIABILITY_AUTHORITY_SUBMITTER",
        "description": "Controlled preparation and submission of accepted Reliability authority packages.",
        "capabilities": [
            "reliability.read",
            "reliability.authority.prepare",
            "reliability.authority.submit",
            "reliability.audit.read",
        ],
    },
}


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def helper_block() -> str:
    capability_rows = ",\n        ".join(
        f"({sql_literal(f'rel-cap-{index:03d}')}, {sql_literal(code)}, 'reliability', {sql_literal(code.replace('.', ' ').title())})"
        for index, code in enumerate(CAPABILITIES, start=1)
    )
    role_rows = ",\n        ".join(
        f"({sql_literal(role_id)}, {sql_literal(config['code'])}, 'AMO', {sql_literal(config['description'])}, true)"
        for role_id, config in ROLES.items()
    )
    capability_ids = {code: f"rel-cap-{index:03d}" for index, code in enumerate(CAPABILITIES, start=1)}
    binding_rows = []
    counter = 1
    for role_id, config in ROLES.items():
        for capability in config["capabilities"]:
            binding_rows.append(
                f"({sql_literal(f'rel-bind-{counter:04d}')}, {sql_literal(role_id)}, {sql_literal(capability_ids[capability])}, '{{}}'::json)"
            )
            counter += 1
    bindings = ",\n        ".join(binding_rows)
    protected_tables = [
        "reliability_audit_events",
        "reliability_fracas_evidence",
        "reliability_fracas_stage_events",
        "reliability_calculation_runs",
    ]
    trigger_sql = "\n".join(
        f'''        op.execute("""
        DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};
        CREATE TRIGGER trg_{table}_append_only
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION prevent_reliability_append_only_mutation();
        """)'''
        for table in protected_tables
    )
    drop_trigger_sql = "\n".join(
        f'''        op.execute("DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")'''
        for table in protected_tables
    )
    return f'''

_RELIABILITY_CAPABILITY_CODES = {CAPABILITIES!r}
_RELIABILITY_ROLE_IDS = {list(ROLES)!r}


def _seed_reliability_authorization() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
    INSERT INTO auth_capability_definitions (id, code, module, description)
    VALUES
        {capability_rows}
    ON CONFLICT (code) DO UPDATE SET
        module = EXCLUDED.module,
        description = EXCLUDED.description
    """)
    op.execute("""
    INSERT INTO auth_role_definitions (id, code, scope_type, description, is_system)
    VALUES
        {role_rows}
    ON CONFLICT (code) DO UPDATE SET
        scope_type = EXCLUDED.scope_type,
        description = EXCLUDED.description,
        is_system = true
    """)
    op.execute("""
    INSERT INTO auth_role_capability_bindings (id, role_id, capability_id, constraints_json)
    VALUES
        {bindings}
    ON CONFLICT (role_id, capability_id) DO NOTHING
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || ':' || u.id || ':rel-role-viewer'), u.amo_id, u.id, 'rel-role-viewer', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-viewer'
      )
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || ':' || u.id || ':rel-role-engineer'), u.amo_id, u.id, 'rel-role-engineer', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND CAST(u.role AS TEXT) IN ('PLANNING_ENGINEER', 'PRODUCTION_ENGINEER', 'QUALITY_INSPECTOR', 'AUDITOR')
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-engineer'
      )
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || ':' || u.id || ':rel-role-manager'), u.amo_id, u.id, 'rel-role-manager', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND (u.is_amo_admin = true OR CAST(u.role AS TEXT) IN ('AMO_ADMIN', 'QUALITY_MANAGER', 'SAFETY_MANAGER'))
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-manager'
      )
    """)
    op.execute("""
    INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
    SELECT md5(u.amo_id || ':' || u.id || ':rel-role-authority'), u.amo_id, u.id, 'rel-role-authority', now(), now()
    FROM users u
    WHERE u.amo_id IS NOT NULL AND u.is_active = true
      AND (u.is_amo_admin = true OR CAST(u.role AS TEXT) IN ('AMO_ADMIN', 'QUALITY_MANAGER'))
      AND NOT EXISTS (
        SELECT 1 FROM auth_user_role_assignments a
        WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = 'rel-role-authority'
      )
    """)


def _remove_reliability_authorization() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("DELETE FROM auth_user_role_assignments WHERE role_id = ANY(:role_ids)").bindparams(role_ids=_RELIABILITY_ROLE_IDS))
    op.execute(sa.text("DELETE FROM auth_role_capability_bindings WHERE role_id = ANY(:role_ids)").bindparams(role_ids=_RELIABILITY_ROLE_IDS))
    op.execute(sa.text("DELETE FROM auth_role_definitions WHERE id = ANY(:role_ids)").bindparams(role_ids=_RELIABILITY_ROLE_IDS))
    op.execute(sa.text("DELETE FROM auth_capability_definitions WHERE code = ANY(:codes)").bindparams(codes=_RELIABILITY_CAPABILITY_CODES))


def _install_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_reliability_append_only_mutation()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'Reliability evidence table % is append-only', TG_TABLE_NAME;
    END;
    $$ LANGUAGE plpgsql;
    """)
{trigger_sql}


def _drop_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
{drop_trigger_sql}
    op.execute("DROP FUNCTION IF EXISTS prevent_reliability_append_only_mutation()")
'''


def _find_generated_migration() -> Path:
    filename_candidates = sorted(VERSIONS.glob(f"{REVISION}_*.py"))
    if len(filename_candidates) == 1:
        return filename_candidates[0]

    revision_pattern = re.compile(
        rf"^revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]{re.escape(REVISION)}['\"]\s*$",
        re.MULTILINE,
    )
    content_candidates = [
        path
        for path in VERSIONS.glob("*.py")
        if revision_pattern.search(path.read_text(encoding="utf-8"))
    ]
    if len(content_candidates) != 1:
        raise RuntimeError(
            "Expected one generated Reliability migration; "
            f"filename matches={len(filename_candidates)}, revision matches={len(content_candidates)}"
        )
    return content_candidates[0]


def main() -> None:
    path = _find_generated_migration()
    text = path.read_text(encoding="utf-8")
    if "_seed_reliability_authorization" in text:
        print(f"Migration {path.name} is already finalized.")
        return
    text = text.replace("\n\ndef upgrade() -> None:\n", helper_block() + "\n\ndef upgrade() -> None:\n", 1)
    text = text.replace(
        "\n\ndef downgrade() -> None:\n",
        "\n    _seed_reliability_authorization()\n    _install_append_only_guards()\n\n\ndef downgrade() -> None:\n    _drop_append_only_guards()\n    _remove_reliability_authorization()\n",
        1,
    )
    path.write_text(text.replace("\n\n\n", "\n\n"), encoding="utf-8")
    print(f"Finalized {path.name} with capability seeding and append-only guards.")


if __name__ == "__main__":
    main()
