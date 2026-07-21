# AMO Portal DB audit export pack

Use this to produce a clean PostgreSQL database report for stale-table review, index design, and backend/database alignment.

## Preferred command

Copy `export_db_audit_report.py` into `tools/`, then run:

```powershell
cd D:\XLK-Assets-AMO-Portal-and-DB\amo-portal
python tools\export_db_audit_report.py
```

It creates `db_audit_report_YYYYMMDD_HHMMSS.zip`. Upload that zip here.

## What it exports

- table inventory and row estimates
- table/index sizes
- columns
- constraints
- foreign keys
- index definitions
- index usage
- missing foreign-key index candidates
- duplicate/overlapping index candidates
- sequential scan hotspots
- Alembic DB versions
- SQLAlchemy model inventory if import works

It does not export table row data.

## Do not upload

- full database dumps
- personnel/business row exports
- `.env` files
- passwords, JWT secrets, broker passwords, or production credentials
