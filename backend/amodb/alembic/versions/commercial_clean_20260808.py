"""Materialize canonical commercial module state and retire compatibility keys.

Revision ID: commercial_clean_20260808
Revises: docgov_rel_20260807_merge
Create Date: 2026-08-08

Historical invoices, ledger entries and audit records are intentionally untouched.
This migration changes only live commercial configuration/entitlement state so the
application no longer needs runtime aliases for earlier module names.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "commercial_clean_20260808"
down_revision = "docgov_rel_20260807_merge"
branch_labels = None
depends_on = None


def _postgres_upgrade() -> None:
    # Preserve the Document Control access historically implied by a Quality
    # subscription by materializing an explicit independent module subscription.
    op.execute(sa.text("""
        INSERT INTO module_subscriptions
            (id, amo_id, module_code, status, effective_from, effective_to,
             plan_code, metadata_json, created_at, updated_at)
        SELECT
            'dc-' || substr(md5(q.amo_id || ':' || q.id), 1, 33),
            q.amo_id,
            'document_control',
            q.status,
            q.effective_from,
            q.effective_to,
            q.plan_code,
            jsonb_set(
                COALESCE(NULLIF(q.metadata_json, '')::jsonb, '{}'::jsonb),
                '{contract_module_code}',
                to_jsonb('document_control'::text),
                true
            )::text,
            q.created_at,
            q.updated_at
        FROM module_subscriptions q
        WHERE q.module_code = 'quality'
          AND NOT EXISTS (
              SELECT 1 FROM module_subscriptions d
              WHERE d.amo_id = q.amo_id AND d.module_code = 'document_control'
          )
    """))

    # Materialize the three enforceable capabilities previously hidden behind
    # finance_inventory before renaming the commercial parent contract.
    for module_code in ("finance", "inventory", "procurement"):
        op.execute(sa.text(f"""
            INSERT INTO module_subscriptions
                (id, amo_id, module_code, status, effective_from, effective_to,
                 plan_code, metadata_json, created_at, updated_at)
            SELECT
                '{module_code[:3]}-' || substr(md5(s.amo_id || ':' || s.id || ':' || '{module_code}'), 1, 32),
                s.amo_id,
                '{module_code}',
                s.status,
                s.effective_from,
                s.effective_to,
                s.plan_code,
                jsonb_set(
                    jsonb_set(
                        COALESCE(NULLIF(s.metadata_json, '')::jsonb, '{{}}'::jsonb),
                        '{{contract_module_code}}',
                        to_jsonb('supply_chain_finance_suite'::text),
                        true
                    ),
                    '{{bundle_parent}}',
                    to_jsonb('supply_chain_finance_suite'::text),
                    true
                )::text,
                s.created_at,
                s.updated_at
            FROM module_subscriptions s
            WHERE s.module_code = 'finance_inventory'
              AND NOT EXISTS (
                  SELECT 1 FROM module_subscriptions c
                  WHERE c.amo_id = s.amo_id AND c.module_code = '{module_code}'
              )
        """))

    # If a canonical suite row already exists, it wins and the stale parent is
    # removed. Otherwise rename the existing parent in place to retain its id.
    op.execute(sa.text("""
        DELETE FROM module_subscriptions old
        WHERE old.module_code = 'finance_inventory'
          AND EXISTS (
              SELECT 1 FROM module_subscriptions new
              WHERE new.amo_id = old.amo_id
                AND new.module_code = 'supply_chain_finance_suite'
          )
    """))
    op.execute(sa.text("""
        UPDATE module_subscriptions
        SET module_code = 'supply_chain_finance_suite',
            metadata_json = replace(
                COALESCE(metadata_json, '{}'),
                'finance_inventory',
                'supply_chain_finance_suite'
            )
        WHERE module_code = 'finance_inventory'
    """))

    # Base-license entitlements are historical contract state still used by the
    # supported base-account contract model. Materialize narrower entitlement
    # keys, then delete the obsolete aggregate key.
    op.execute(sa.text("""
        INSERT INTO license_entitlements
            (id, license_id, key, "limit", is_unlimited, description, created_at)
        SELECT
            'dc-' || substr(md5(e.license_id || ':' || e.id), 1, 33),
            e.license_id,
            'document_control',
            e."limit",
            e.is_unlimited,
            'Document Control entitlement materialized from the former Quality bundle',
            e.created_at
        FROM license_entitlements e
        WHERE e.key = 'quality'
          AND NOT EXISTS (
              SELECT 1 FROM license_entitlements x
              WHERE x.license_id = e.license_id AND x.key = 'document_control'
          )
    """))
    for key in ("finance", "inventory", "procurement"):
        op.execute(sa.text(f"""
            INSERT INTO license_entitlements
                (id, license_id, key, "limit", is_unlimited, description, created_at)
            SELECT
                '{key[:3]}-' || substr(md5(e.license_id || ':' || e.id || ':' || '{key}'), 1, 32),
                e.license_id,
                '{key}',
                e."limit",
                e.is_unlimited,
                'Entitlement materialized from the retired finance_inventory aggregate key',
                e.created_at
            FROM license_entitlements e
            WHERE e.key = 'finance_inventory'
              AND NOT EXISTS (
                  SELECT 1 FROM license_entitlements x
                  WHERE x.license_id = e.license_id AND x.key = '{key}'
              )
        """))
    op.execute(sa.text("DELETE FROM license_entitlements WHERE key = 'finance_inventory'"))

    # Move live module pricing to the canonical suite. If an equivalent canonical
    # price already exists, keep it and remove the conflicting stale row.
    op.execute(sa.text("""
        DELETE FROM saas_module_prices old
        WHERE old.module_code = 'finance_inventory'
          AND EXISTS (
              SELECT 1 FROM saas_module_prices new
              WHERE new.module_code = 'supply_chain_finance_suite'
                AND new.plan_code = old.plan_code
                AND new.billing_term = old.billing_term
                AND new.currency = old.currency
          )
    """))
    op.execute(sa.text("""
        UPDATE saas_module_prices
        SET module_code = 'supply_chain_finance_suite'
        WHERE module_code = 'finance_inventory'
    """))

    # Current billing-account metadata is mutable provider state, not immutable
    # financial history. Normalize module keys so future provider events resolve
    # the canonical contract name.
    op.execute(sa.text("""
        UPDATE saas_billing_accounts
        SET metadata_json = replace(
            COALESCE(metadata_json::text, '{}'),
            'finance_inventory',
            'supply_chain_finance_suite'
        )::json
        WHERE metadata_json::text LIKE '%finance_inventory%'
    """))

    # Normalize live commercial feature-flag keys. Avoid unique-key conflicts by
    # deleting a stale duplicate when the canonical replacement already exists.
    op.execute(sa.text("""
        DELETE FROM platform_feature_flags old
        WHERE old.key LIKE '%finance_inventory%'
          AND EXISTS (
              SELECT 1 FROM platform_feature_flags new
              WHERE new.scope = old.scope
                AND COALESCE(new.tenant_id, '') = COALESCE(old.tenant_id, '')
                AND new.key = replace(old.key, 'finance_inventory', 'supply_chain_finance_suite')
          )
    """))
    op.execute(sa.text("""
        UPDATE platform_feature_flags
        SET key = replace(key, 'finance_inventory', 'supply_chain_finance_suite'),
            name = replace(COALESCE(name, ''), 'finance_inventory', 'supply_chain_finance_suite'),
            description = replace(COALESCE(description, ''), 'finance_inventory', 'supply_chain_finance_suite')
        WHERE key LIKE '%finance_inventory%'
    """))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("commercial_clean_20260808 requires PostgreSQL")
    _postgres_upgrade()


def downgrade() -> None:
    # Deliberately non-destructive. Reintroducing implicit entitlements would
    # erase the explicit commercial state created by this migration and could
    # silently broaden or remove contracted access.
    pass
