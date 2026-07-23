# Reproduction state

An installation upgraded before the migration-parent rewrite can contain these independent rows in `alembic_version`:

- `workforce_20260721_complete`
- `phase2_14a_20260615`

After the rewrite made `phase2_14a_20260615` an ancestor of the Workforce branch, Alembic rejects those rows as overlapping before executing any migration. The hotfix must reproduce this exact revision table, run `alembic upgrade heads`, and verify convergence without manual stamping or data loss.
