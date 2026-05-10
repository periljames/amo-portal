# QMS Developer Handoff

## What changed in this pass

- Fixed the failed Phase 3 migration that referenced a non-existent `user_active_contexts` table.
- Hardened the parallel global-superuser migration to avoid the same table-assumption fault.
- Added a Phase 4 migration for activity/file access logging columns.
- Added backend QMS route-map endpoint.
- Added backend workflow action endpoint for audits, CAR/CAPA, and controlled documents.
- Corrected generic route view resolution so routes like `/cars/overdue` and `/cars/{id}/root-cause` load the correct tenant-scoped table.
- Corrected document table mappings to the tables created by the canonical QMS migration.
- Updated frontend QMS canonical page so nested routes call the matching backend nested endpoint instead of only loading the module root.

## Immediate local verification

```bash
alembic -c backend/amodb/alembic.ini upgrade heads
python -m pytest backend/amodb/apps/qms/tests/test_qms_security.py
cd frontend
npm install
npm run build
```

## No deletion required

The current uploaded codebase did not contain the earlier ghost backup files. No files are listed for deletion in this pass.
