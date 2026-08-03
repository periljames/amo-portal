from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / "backend/amodb/alembic/env.py"


def main() -> None:
    text = ENV_PATH.read_text(encoding="utf-8")
    text = text.replace(
        "from sqlalchemy import inspect, pool, text  # kept for compatibility with typical alembic templates",
        "from sqlalchemy import MetaData, inspect, pool, text  # kept for compatibility with typical alembic templates",
        1,
    )
    anchor = "# Target metadata for 'autogenerate'\ntarget_metadata = Base.metadata\n"
    replacement = '''def _build_reliability_metadata() -> MetaData:
    """Return only Reliability tables and their direct FK dependency graph.

    Global metadata currently contains optional module tables whose foreign-key
    targets are not registered in every deployment. Reliability-only
    autogeneration must not resolve or compare those unrelated tables.
    """
    required = set(_RELIABILITY_TABLES)
    pending = list(required)
    while pending:
        table_name = pending.pop()
        table = Base.metadata.tables.get(table_name)
        if table is None:
            raise RuntimeError(f"Reliability autogenerate table is not registered: {table_name}")
        for foreign_key in table.foreign_keys:
            target = str(foreign_key._colspec).rsplit(".", 1)[0]
            if target not in required:
                if target not in Base.metadata.tables:
                    raise RuntimeError(
                        f"Reliability table {table_name} references unregistered table {target}"
                    )
                required.add(target)
                pending.append(target)

    metadata = MetaData()
    for table_name in sorted(required):
        Base.metadata.tables[table_name].to_metadata(metadata)
    return metadata


# Target metadata for 'autogenerate'. Application migrations use the full model;
# the Reliability completion migration uses an isolated, dependency-complete graph.
target_metadata = (
    _build_reliability_metadata()
    if os.getenv("RELIABILITY_AUTOGENERATE_ONLY", "0").strip().lower()
    in {"1", "true", "yes", "on"}
    else Base.metadata
)
'''
    if anchor not in text:
        raise RuntimeError("Alembic target_metadata anchor not found")
    text = text.replace(anchor, replacement, 1)
    ENV_PATH.write_text(text, encoding="utf-8")
    print("Reliability Alembic autogeneration isolated from unrelated metadata.")


if __name__ == "__main__":
    main()
