# Alembic legacy-head convergence hotfix

The merged migration graph temporarily rewrote the parentage of `workforce_20260721_precreate` so that `phase2_14a_20260615` became an ancestor of `workforce_20260721_complete`.

Existing databases created under the previously released graph may legitimately contain both revisions as independent rows in `alembic_version`. Alembic rejects that state as overlapping after the ancestry rewrite and aborts before any upgrade migration can execute.

This hotfix restores compatibility with those databases, converges the branches through a new revision instead of rewriting released history, and adds PostgreSQL coverage for both fresh databases and legacy multi-head revision states.
