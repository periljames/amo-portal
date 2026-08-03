from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / "backend/amodb/alembic/env.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label}, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = ENV_PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from sqlalchemy import inspect, pool, text  # kept for compatibility with typical alembic templates",
        "from sqlalchemy import MetaData, inspect, pool, text  # kept for compatibility with typical alembic templates",
        "SQLAlchemy metadata import",
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


_RELIABILITY_AUTOGENERATE_ENABLED = (
    os.getenv("RELIABILITY_AUTOGENERATE_ONLY", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)

# Target metadata for 'autogenerate'. Application migrations use the full model;
# the Reliability completion migration uses an isolated, dependency-complete graph.
target_metadata = (
    _build_reliability_metadata()
    if _RELIABILITY_AUTOGENERATE_ENABLED
    else Base.metadata
)
'''
    text = replace_once(text, anchor, replacement, "Alembic target_metadata anchor")

    online_anchor = '''            compare_type=True,
            compare_server_default=True,
            # You can add include_object / process_revision_directives here later if needed.
'''
    online_replacement = '''            compare_type=True,
            # PostgreSQL JSON has no equality operator; compare defaults only for
            # ordinary application migrations, not the scoped Reliability graph.
            compare_server_default=not _RELIABILITY_AUTOGENERATE_ENABLED,
            include_object=_reliability_include_object,
'''
    text = replace_once(
        text,
        online_anchor,
        online_replacement,
        "online Reliability include_object configuration",
    )

    offline_anchor = '''        compare_type=True,
        compare_server_default=True,
    )
'''
    if "include_object=_reliability_include_object" not in text.split("def run_migrations_offline", 1)[1].split("def _assert_no_duplicate_revisions", 1)[0]:
        text = replace_once(
            text,
            offline_anchor,
            '''        compare_type=True,
        compare_server_default=not _RELIABILITY_AUTOGENERATE_ENABLED,
        include_object=_reliability_include_object,
    )
''',
            "offline Reliability include_object configuration",
        )
    else:
        offline_section, remainder = text.split("def _assert_no_duplicate_revisions", 1)
        offline_section = offline_section.replace(
            "compare_server_default=True,",
            "compare_server_default=not _RELIABILITY_AUTOGENERATE_ENABLED,",
            1,
        )
        text = offline_section + "def _assert_no_duplicate_revisions" + remainder

    ENV_PATH.write_text(text, encoding="utf-8")
    print("Reliability Alembic autogeneration isolated in offline and online contexts.")


if __name__ == "__main__":
    main()
