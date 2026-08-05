"""Remove the retired fleet-import persistence model from active metadata.

The original importer classes remain in the historical fleet module until that
module is split, but their tables are deliberately removed from ``Base.metadata``
so application startup and Alembic autogeneration recognise only the universal
induction domain. No service or route may query these retired mapped classes.
"""

from ...database import Base


RETIRED_IMPORT_TABLES = (
    "aircraft_import_templates",
    "aircraft_import_preview_sessions",
    "aircraft_import_preview_rows",
    "aircraft_import_snapshots",
    "aircraft_import_reconciliation_logs",
)


def remove_retired_import_tables() -> None:
    for table_name in RETIRED_IMPORT_TABLES:
        table = Base.metadata.tables.get(table_name)
        if table is not None:
            Base.metadata.remove(table)


remove_retired_import_tables()
